"""s4-31 (8-oct): cada fallo del juez del golden, con el TURNO que lo causó y la PIEZA que escribió ese turno.

El juez dice qué criterio falla y cita lo que dijo el bot (`evidencia_bot`). Este script busca esa cita en las
respuestas de la ronda y mira en `[TURN_METRICS]` qué tipo de turno era: `rag` (la respuesta la escribió el RAG:
causa candidata de prompt o de búsqueda) o `reserva` / `cambios` / … (texto fijo del flujo). Sin cita encontrada, el
fallo queda como `sin_cita` (criterios globales sobre toda la conversación, o una cita que el juez parafraseó).

Es el primer paso de "agrupar los fallos por causa": separa lo que es del RAG de lo que no, para leer a mano solo lo
que toca. Salida: lista JSON con el formato de `docs/robustness/fallos-por-causa-*.json` más `turno`, `tipo` y
`respuesta`, y la columna `causa` vacía para rellenarla leyendo.

    python -m scripts.fallos_por_turno <ronda>      # p. ej. 2026-10-08-luna-visible
    python -m scripts.fallos_por_turno <ronda> --out docs/robustness/fallos-por-causa-<ronda>.json

Solo lee ficheros de la ronda (sin API).
"""
import argparse
import collections
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "docs/robustness/synthetic-runs"
RESULTS = ROOT / "docs/robustness/golden-set/results"
LOGS = ROOT / "docs/robustness"


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def _turnos_por_conv(log: str) -> dict[str, list[dict]]:
    por_conv = collections.defaultdict(list)
    for linea in log.splitlines():
        if "[TURN_METRICS] " in linea:
            m = json.loads(linea.split("[TURN_METRICS] ", 1)[1])
            por_conv[str(m.get("conv"))].append(m)
    return por_conv


def _turno_de_la_cita(cita: str, turnos: list[dict]) -> dict | None:
    """El turno cuya respuesta contiene la cita (normalizada); si la cita es larga, basta con su comienzo."""
    c = _norm(cita)
    if not c:
        return None
    for trozo in (c, c[:80], c[:40]):
        for t in turnos:
            if trozo and trozo in _norm(t["reply"]):
                return t
    return None


def fallos(ronda: str) -> list[dict]:
    run = [json.loads(ln) for ln in (RUNS / f"{ronda}.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    res = json.loads((RESULTS / f"{ronda}__gpt-5-mini-medium.json").read_text(encoding="utf-8"))
    metricas = _turnos_por_conv((LOGS / f"logs-pre-{ronda}.txt").read_text(encoding="utf-8"))
    por_tag = collections.defaultdict(list)
    for r in run:
        por_tag[r["tag"]].append(r)
    salida = []
    for d in res["dialogues"]:
        turnos = sorted(por_tag.get(d["id"], []), key=lambda r: r["turn"])
        mets = metricas.get(str(turnos[0]["conv"]), []) if turnos else []
        for c in d["criteria"]:
            if c["verdict"] not in ("no_cumple", "revisar"):
                continue
            t = _turno_de_la_cita(c.get("evidencia_bot") or "", turnos)
            m = mets[t["turn"] - 1] if t and t["turn"] - 1 < len(mets) else {}
            salida.append({
                "dialogo": d["id"], "criterio": c["id"], "veredicto": c["verdict"], "causa": "",
                "turno": t["turn"] if t else None,
                "tipo": m.get("turn_type") or ("sin_cita" if not t else "?"),
                "motivo": (c.get("reason") or "")[:400],
                "cita": (c.get("evidencia_bot") or "")[:300],
                "mensaje_cliente": (t["msg"][:200] if t else ""),
                "respuesta": (t["reply"][:700] if t else ""),
            })
    return salida


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ronda")
    ap.add_argument("--out")
    args = ap.parse_args()
    filas = fallos(args.ronda)
    print(f"{len(filas)} fallos (no_cumple + revisar) por tipo de turno:",
          dict(collections.Counter(f["tipo"] for f in filas)))
    for f in filas:
        print(f"  [{f['tipo']:9s}] {f['dialogo']} · {f['criterio']} (turno {f['turno']}): {f['motivo'][:150]}")
    if args.out:
        Path(args.out).write_text(json.dumps(filas, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"→ {args.out}")


if __name__ == "__main__":
    main()
