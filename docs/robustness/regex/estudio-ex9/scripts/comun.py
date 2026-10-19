"""Comun del estudio ex-9: corpus visible (sin oculto) y entorno sin red.

Se ejecuta con cwd = raiz del repo. Nunca lee el examen G9 ni usa diálogos del oculto.
"""
import json
import os
import socket
import sys
import tempfile
from pathlib import Path

# El repo: estas piezas viven en docs/robustness/regex/estudio-ex9/scripts/ (o en otra carpeta con ESTUDIO_REPO).
REPO = Path(os.environ.get("ESTUDIO_REPO") or Path(__file__).resolve().parents[5])
# Salidas intermedias (los replays pesan ~0,5 MB cada uno): fuera del repo.
OUT = Path(os.environ.get("ESTUDIO_OUT") or Path(tempfile.gettempdir()) / "estudio-ex9")
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(REPO))
os.chdir(REPO)

# Config de PRE = valores por defecto + Jev encendido. Sin fichero .env (ENV_FILE a uno que no existe) y sin claves.
os.environ["ENV_FILE"] = str(OUT / "no-existe.env")
os.environ["OPENAI_API_KEY"] = "sk-test-sin-red"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["JEV_ROUTER_ENABLED"] = "true"
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""
os.environ["CHATWOOT_API_TOKEN"] = ""
os.environ["CHATWOOT_BASE_URL"] = "http://127.0.0.1:9"
os.environ["CHATWOOT_API_BASE_URL"] = "http://127.0.0.1:9"


class SinRed(RuntimeError):
    pass


def bloquear_red() -> None:
    """Cualquier conexión de red falla al momento (salvo localhost, que tampoco se usa)."""
    original = socket.socket.connect

    def _connect(self, address):  # noqa: ANN001
        host = address[0] if isinstance(address, tuple) else address
        if host in ("127.0.0.1", "::1", "localhost"):
            return original(self, address)
        raise SinRed(f"red bloqueada en el estudio: {address!r}")

    socket.socket.connect = _connect
    _orig_gai = socket.getaddrinfo

    def _gai(host, *a, **k):  # noqa: ANN001
        if host in ("127.0.0.1", "::1", "localhost", None):
            return _orig_gai(host, *a, **k)
        raise SinRed(f"DNS bloqueado en el estudio: {host!r}")

    socket.getaddrinfo = _gai


def ids_ocultos() -> set[str]:
    """Solo para EXCLUIR: nunca se imprimen ni se guardan."""
    g = json.loads((REPO / "docs/robustness/golden-set/golden-dialogues.json").read_text(encoding="utf-8"))
    return {d["id"] for d in g["dialogues"] if d.get("suite") == "oculto"}


def corpus() -> list[dict]:
    """(dialogo, turno, msg) de los diálogos VISIBLES del golden (los turnos de las rondas 2026-10-1* son estos
    mismos mensajes: se comprobó que no añaden texto nuevo)."""
    from scripts.replay_golden_local import dialogues  # ya salta el oculto

    ocultos = ids_ocultos()
    filas = []
    for did, turns in dialogues():
        assert did not in ocultos
        for i, msg in enumerate(turns, 1):
            filas.append({"dialogo": did, "turno": i, "msg": msg})
    return filas


def pesos_rondas() -> dict[str, int]:
    """Cuántas veces aparece cada mensaje en las rondas 2026-10-1* (filas visibles; las del oculto se descartan)."""
    import glob
    from collections import Counter

    ocultos = ids_ocultos()
    c = Counter()
    for f in sorted(glob.glob(str(REPO / "docs/robustness/synthetic-runs/2026-10-1*.jsonl"))):
        for x in open(f, encoding="utf-8"):
            r = json.loads(x)
            if r.get("tag") in ocultos:
                continue
            c[r.get("msg")] += 1
    return dict(c)
