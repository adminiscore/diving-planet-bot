"""El presupuesto de complejidad (Álvaro, 28-oct; acordado por Coral #2307-#2309): en cada ronda, junto a la calidad y
la latencia, cuatro cifras que no deberían crecer sin motivo. Regla: toda pieza nueva dice qué quita, o por qué no.

    python scripts/complejidad.py                                   # el árbol de trabajo
    python scripts/complejidad.py --ref origin/feature/caln-gadea   # una rama o un commit
    python scripts/complejidad.py --contra <ref>                    # y la diferencia con otra
    python scripts/complejidad.py --metricas <ronda>.metricas       # + llamadas por turno y p50/p95 de una ronda

- Líneas y ficheros .py de `src/` (y los tres más grandes).
- Interruptores: los `bool` de `src/config.py`.
- Campos del estado: los de `ConversationState` (`src/flows/state.py`), donde se acumula lo que el bot recuerda.
- Llamadas por turno y latencia: de las [TURN_METRICS] de una ronda (`.metricas`, una por línea) o de una medida de
  `reproducir_juez_pre` (su campo «metricas»).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_BOOL = re.compile(r"^\s+[a-z_0-9]+: bool = ", re.M)
_CAMPO = re.compile(r"^    [a-z_0-9]+: [^=\n]+ = ", re.M)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout


def _ficheros(ref: str | None) -> dict[str, str]:
    """{ruta: texto} de los .py de src, del árbol de trabajo (ref None) o de un commit."""
    if ref is None:
        return {str(p.relative_to(ROOT)).replace("\\", "/"): p.read_text(encoding="utf-8")
                for p in sorted((ROOT / "src").rglob("*.py"))}
    rutas = [r for r in _git("ls-tree", "-r", "--name-only", ref, "src").split() if r.endswith(".py")]
    return {r: _git("show", f"{ref}:{r}") for r in rutas}


def campos_del_estado(texto: str) -> int:
    """Los campos de la clase `ConversationState` (hasta la siguiente clase o definición de primer nivel)."""
    inicio = texto.find("class ConversationState")
    if inicio < 0:
        return 0
    cuerpo = texto[inicio:]
    fin = re.search(r"^(class |def |[A-Za-z_][A-Za-z_0-9]* = )", cuerpo[1:], re.M)
    return len(_CAMPO.findall(cuerpo[: fin.start() + 1] if fin else cuerpo))


def medir(ref: str | None) -> dict:
    fs = _ficheros(ref)
    lineas = {r: t.count("\n") for r, t in fs.items()}
    return {
        "lineas_src": sum(lineas.values()),
        "ficheros_src": len(fs),
        "interruptores": len(_BOOL.findall(fs.get("src/config.py", ""))),
        "campos_del_estado": campos_del_estado(fs.get("src/flows/state.py", "")),
        "mayores": sorted(lineas.items(), key=lambda kv: -kv[1])[:3],
    }


def _p(vals: list[float], q: float) -> float | None:
    vals = sorted(vals)
    return round(vals[min(len(vals) - 1, int(q * len(vals)))], 2) if vals else None


def de_la_ronda(ruta: str) -> dict:
    """Llamadas al modelo por turno y latencia p50/p95 de una ronda."""
    turnos = []
    for ln in Path(ruta).read_text(encoding="utf-8").splitlines():
        if not ln.strip().startswith("{"):
            continue
        fila = json.loads(ln)
        turnos += fila.get("metricas") or ([fila] if "llm_calls" in fila else [])
    llamadas = [t["llm_calls"] for t in turnos if isinstance(t.get("llm_calls"), int)]
    latencias = [t["latency"] for t in turnos if isinstance(t.get("latency"), (int, float))]
    return {"turnos": len(turnos),
            "llamadas_por_turno": round(sum(llamadas) / len(llamadas), 2) if llamadas else None,
            "p50_s": _p(latencias, .5), "p95_s": _p(latencias, .95)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ref", help="rama o commit (por defecto, el árbol de trabajo)")
    ap.add_argument("--contra", help="otra rama o commit para la diferencia")
    ap.add_argument("--metricas", help="las [TURN_METRICS] de una ronda (.metricas) o una medida de reproducir_juez_pre")
    args = ap.parse_args()
    hoy = medir(args.ref)
    antes = medir(args.contra) if args.contra else None
    nombre = args.ref or "árbol de trabajo"
    print(f"{'':<20} {nombre:>22}" + (f" {args.contra:>22} {'Δ':>8}" if antes else ""))
    for k in ("lineas_src", "ficheros_src", "interruptores", "campos_del_estado"):
        fila = f"{k:<20} {hoy[k]:>22}"
        if antes:
            fila += f" {antes[k]:>22} {hoy[k] - antes[k]:>+8}"
        print(fila)
    print("mayores:", ", ".join(f"{r} {n}" for r, n in hoy["mayores"]))
    if args.metricas:
        print("ronda:", json.dumps(de_la_ronda(args.metricas), ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
