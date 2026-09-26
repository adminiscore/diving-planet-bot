"""Comprueba que un push a `pre_*` SÍ se desplegó, y que PRE sirve lo que dice el repo (r6-3).

Por qué: un CI rojo se salta el job de deploy SIN avisar. Del 24-sep 23:04 al 25-sep 21:30 PRE sirvió
código viejo y nadie lo vio (HISTORY 0.29.27). Tras cada push a una rama `pre_*`:

    python -m scripts.check_deploy              # rama y commit actuales; espera a que termine
    python -m scripts.check_deploy --no-wait    # solo mira cómo está ahora

Comprueba, en orden, y sale con error en el primer fallo:
1. El run de GitHub Actions de ese commit (API pública: sin `gh` ni permisos de admin) terminó en verde.
   Si falló, dice qué paso falló.
2. PRE (por SSH) sirve ESE commit y ESA rama, y el contenedor está `healthy`.
3. Cada interruptor y modelo que `docker-compose.vps.yml` fija para `dp-pre-bot` es el que tiene de verdad
   el bot (`src.config.settings` dentro del contenedor). Lo que dice el repo y lo que corre PRE no pueden
   separarse sin que se vea.

Salida: 0 bien · 1 fallo · 2 no terminó a tiempo. SSH: `scripts/pre_access.py`.
"""

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import yaml

from scripts.pre_access import pre_ssh

ROOT = Path(__file__).resolve().parent.parent
REPO_DIR_EN_PRE = "/opt/diving-planet-bot"
CONTENEDOR = "dp-pre-bot"
API = "https://api.github.com/repos/{slug}/actions/{path}"


# ── Lo que dice el repo ──────────────────────────────────────────────────────────────────────────
def expected_from_compose(path: Path = ROOT / "docker-compose.vps.yml") -> dict:
    """Interruptores y modelos que el compose fija para PRE, como ajustes de `settings`.

    Se quedan fuera los valores con variables (`${...}`) o URLs: llevan contraseñas o dependen del
    servidor, y no son "conducta" que comparar."""
    env = yaml.safe_load(path.read_text(encoding="utf-8"))["services"][CONTENEDOR]["environment"]
    return {k.lower(): as_setting(str(v)) for k, v in env.items() if "${" not in str(v) and "://" not in str(v)}


def as_setting(raw: str):
    low = raw.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    if re.fullmatch(r"-?\d+", low):
        return int(low)
    if re.fullmatch(r"-?\d+\.\d*", low):
        return float(low)
    return raw.strip()


def compare(expected: dict, actual: dict) -> list[str]:
    """Diferencias entre lo que fija el compose y lo que tiene el bot en PRE."""
    diffs = []
    for k, want in expected.items():
        if k not in actual:
            diffs.append(f"{k}: el bot no tiene este ajuste")
            continue
        got = actual[k]
        same = abs(float(got) - float(want)) < 1e-9 if isinstance(want, float) else got == want
        if not same:
            diffs.append(f"{k}: repo={want!r} PRE={got!r}")
    return diffs


# ── GitHub Actions ───────────────────────────────────────────────────────────────────────────────
def slug_from_url(url: str) -> str:
    """`owner/repo` a partir de la URL del remoto (https o ssh)."""
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?/?$", url.strip())
    if not m:
        raise SystemExit(f"No reconozco el remoto de GitHub: {url}")
    return m.group(1)


def repo_slug() -> str:
    return slug_from_url(subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=True).stdout)


def _get(slug: str, path: str) -> dict:
    req = urllib.request.Request(API.format(slug=slug, path=path), headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def find_run(runs: list[dict], sha: str) -> dict | None:
    """El run más reciente de ese commit (acepta el SHA corto)."""
    for r in runs:
        if r.get("head_sha", "").startswith(sha):
            return r
    return None


def failing_steps(slug: str, run_id: int) -> list[str]:
    out = []
    for job in _get(slug, f"runs/{run_id}/jobs").get("jobs", []):
        for s in job.get("steps", []):
            if s.get("conclusion") not in ("success", "skipped", None):
                out.append(f"{job['name']} / {s['name']}: {s['conclusion']}")
    return out


# ── PRE ──────────────────────────────────────────────────────────────────────────────────────────
_LEER_AJUSTES = """
import json, sys
from src.config import settings
print(json.dumps({k: getattr(settings, k, None) for k in json.loads(sys.stdin.readline())}, default=str))
"""


def pre_state(keys: list[str]) -> dict:
    cmd = (
        f"cd {REPO_DIR_EN_PRE} && git rev-parse HEAD && git rev-parse --abbrev-ref HEAD && "
        f"docker inspect --format '{{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{end}}}}' {CONTENEDOR} && "
        f"docker exec -i {CONTENEDOR} python -c '{_LEER_AJUSTES.strip()}'"
    )
    out = pre_ssh(cmd, input_text=json.dumps(keys) + "\n")
    lines = out.stdout.strip().splitlines()
    if out.returncode != 0 or len(lines) < 4:
        raise RuntimeError(f"SSH a PRE falló (código {out.returncode}): {out.stderr.strip()[:300]}")
    return {"sha": lines[0], "branch": lines[1], "health": lines[2], "settings": json.loads(lines[-1])}


# ── Principal ────────────────────────────────────────────────────────────────────────────────────
def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--branch", help="rama desplegada (por defecto, la actual)")
    parser.add_argument("--sha", help="commit esperado (por defecto, HEAD)")
    parser.add_argument("--no-wait", action="store_true", help="no esperar a que termine el run")
    parser.add_argument("--timeout", type=int, default=1200, help="segundos máximos de espera (20 min)")
    args = parser.parse_args(argv)
    # Que el progreso salga linea a linea aunque la salida no sea una terminal (tareas de fondo, CI).
    sys.stdout.reconfigure(line_buffering=True)

    branch = args.branch or _git("rev-parse", "--abbrev-ref", "HEAD")
    sha = args.sha or _git("rev-parse", "HEAD")
    slug = repo_slug()
    print(f"Comprobando el deploy de {branch} @ {sha[:7]} ({slug})")

    # 1. CI
    t0 = time.monotonic()
    while True:
        run = find_run(_get(slug, f"runs?branch={branch}&per_page=20").get("workflow_runs", []), sha)
        estado = "sin run todavía" if run is None else f"{run['status']} / {run['conclusion']}"
        if run and run["status"] == "completed":
            break
        if args.no_wait or time.monotonic() - t0 > args.timeout:
            print(f"✗ CI no ha terminado ({estado})")
            return 2
        print(f"  CI: {estado} … espero")
        time.sleep(30)
    if run["conclusion"] != "success":
        print(f"✗ CI terminó en {run['conclusion']}: el deploy NO se hizo. {run['html_url']}")
        for s in failing_steps(slug, run["id"]):
            print(f"    paso que falla: {s}")
        return 1
    print(f"✓ CI en verde ({run['html_url']})")

    # 2 y 3. PRE
    expected = expected_from_compose()
    while True:
        state = pre_state(sorted(expected))
        if state["sha"].startswith(sha) and state["health"] == "healthy":
            break
        if args.no_wait or time.monotonic() - t0 > args.timeout:
            print(f"✗ PRE sirve {state['sha'][:7]} ({state['branch']}, {state['health'] or 'sin healthcheck'}), no {sha[:7]}")
            return 2
        print(f"  PRE: {state['sha'][:7]} {state['health']} … espero")
        time.sleep(20)
    if state["branch"] != branch:
        print(f"✗ PRE está en la rama {state['branch']}, no en {branch}")
        return 1
    print(f"✓ PRE sirve {sha[:7]} desde {branch} y está healthy")
    diffs = compare(expected, state["settings"])
    if diffs:
        print("✗ PRE NO tiene lo que fija el compose:")
        for d in diffs:
            print(f"    {d}")
        return 1
    print(f"✓ Los {len(expected)} ajustes que fija el compose coinciden en PRE (interruptores y modelos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
