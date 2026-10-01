"""J2: lista para LEER A MANO cada respuesta que la segunda opinión de Jev rescató.

El relevo del 1-oct pide leer a mano cada rescate de J2 en la ronda core, porque ninguno puede ser un invento: J2
deja pasar respuestas que el juez de grounding había rechazado. Pero la línea `[RAG][GROUNDING][JEV] pasa: ...` del
registro de PRE solo trae las frases rechazadas CORTADAS a 60 caracteres, sin la pregunta del cliente ni la respuesta
entera, y sin el número de conversación. Así no se puede juzgar si lo rescatado afirmaba algo del negocio.

Esto empareja cada línea del juez con su turno. Las líneas no llevan conversación, pero cada turno termina con una
línea `[TURN_METRICS] {"conv": ...}` que sí, y la ronda va estrictamente de uno en uno (`run_synthetic_pre`): cada
línea del juez pertenece al `[TURN_METRICS]` que cierra justo después. Con la conversación y el orden, el JSONL de la
ronda da el mensaje del cliente y la respuesta entera.

    python -m scripts.j2_rescates 2026-10-01-juez-B

Lee `docs/robustness/logs-pre-<ronda>.txt` y `docs/robustness/synthetic-runs/<ronda>.jsonl`.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_JEV = re.compile(r"\[RAG\]\[GROUNDING\]\[JEV\] (pasa|se mantiene|sin segunda opinión)")
_RECHAZO = re.compile(r"\[RAG\]\[GROUNDING\] attempt \d+ rejected")
_METRICS = re.compile(r"\[TURN_METRICS\] (\{.*\})")
_FRASE = re.compile(r"(None|[\d.]+) '((?:[^'\\]|\\.)*)'")


def turnos_con_juez(log: Path) -> list[dict]:
    """[{conv, orden, lineas}] — las líneas del juez de cada turno, en el orden en que pasaron."""
    turnos, buffer, orden = [], [], defaultdict(int)
    for linea in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if _JEV.search(linea) or _RECHAZO.search(linea):
            buffer.append(linea.split("[RAG]", 1)[1].strip())
            continue
        m = _METRICS.search(linea)
        if not m:
            continue
        try:
            conv = str(json.loads(m.group(1)).get("conv"))
        except json.JSONDecodeError:
            continue
        orden[conv] += 1
        if buffer:
            turnos.append({"conv": conv, "orden": orden[conv], "lineas": buffer})
        buffer = []
    return turnos


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("uso: python -m scripts.j2_rescates <ronda>   (p. ej. 2026-10-01-juez-B)")
    ronda = sys.argv[1]
    log = Path("docs/robustness") / f"logs-pre-{ronda}.txt"
    run = Path("docs/robustness/synthetic-runs") / f"{ronda}.jsonl"
    filas = [json.loads(x) for x in run.read_text(encoding="utf-8").splitlines() if x.strip()]
    por_conv = defaultdict(list)
    for f in filas:
        por_conv[str(f["conv"])].append(f)
    for v in por_conv.values():
        v.sort(key=lambda f: f["turn"])

    turnos = turnos_con_juez(log)
    rescates = [t for t in turnos if any("[JEV] pasa" in x for x in t["lineas"])]
    mantenidos = [t for t in turnos if any("[JEV] se mantiene" in x for x in t["lineas"])]
    sin_op = [t for t in turnos if any("sin segunda opinión" in x for x in t["lineas"])]
    rechazos = sum(1 for t in turnos for x in t["lineas"] if "rejected" in x)
    print(f"ronda {ronda}: {len(filas)} turnos · rechazos del juez {rechazos} · turnos con J2: "
          f"rescata {len(rescates)} · mantiene {len(mantenidos)} · sin opinión (Jev no contestó) {len(sin_op)}\n")

    for i, t in enumerate(rescates, 1):
        turnos_conv = por_conv.get(t["conv"], [])
        fila = turnos_conv[t["orden"] - 1] if 0 < t["orden"] <= len(turnos_conv) else None
        print("=" * 100)
        print(f"RESCATE {i} · conv {t['conv']} · turno {t['orden']}"
              + (f" · {fila['tag']}" if fila else " · (turno no encontrado en el JSONL)"))
        if fila:
            print(f"\nCLIENTE: {fila['msg']}")
        for x in t["lineas"]:
            if "[JEV] pasa" in x:
                print("\nFRASES QUE EL JUEZ RECHAZÓ Y JEV DEJÓ PASAR (p = probabilidad de que afirmen algo del negocio):")
                for p, frase in _FRASE.findall(x):
                    print(f"   p={p:<5} {frase}")
        if fila:
            print(f"\nRESPUESTA QUE RECIBIÓ EL CLIENTE:\n{fila['reply']}\n")
    if not rescates:
        print("Ningún rescate de J2 en esta ronda.")


if __name__ == "__main__":
    main()
