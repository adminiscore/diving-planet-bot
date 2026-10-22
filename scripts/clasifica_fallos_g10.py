"""Clasifica los fallos de un G10 (o G9) por quién escribió el turno que cita el juez: redactor, RAG, flujo o pase.

Solo diagnóstico (arq-4, 22-oct): los bancos de arreglo se escriben con frases nuestras, nunca con las del examen.
Cruza la cita del bot de cada criterio que falla con el turno de la ronda y mira qué piezas llamaron a un modelo en ese
turno ([TURN_METRICS]). «redactor->RAG» = el redactor contestó y la respuesta adelantada del RAG también se calculó.

    ENV_FILE=.env.ci python scripts/clasifica_fallos_g10.py 2026-10-22-g10-arq1 [--desfasados <lista.json>]
"""
import argparse
import collections
import json

RESULTADOS = "docs/robustness/golden-set/results/{}__gpt-5-mini-medium.json"
RONDAS = "docs/robustness/synthetic-runs/{}.{}"


def _jsonl(fichero: str) -> list[dict]:
    with open(fichero, encoding="utf-8") as f:
        return [json.loads(linea) for linea in f]


def _quien(metrica: dict) -> str:
    piezas = [c["p"] for c in metrica.get("llamadas", [])]
    if "redactor_hechos" in piezas:
        return "redactor" if "rag_escritor" not in piezas else "redactor->RAG"
    if "rag_escritor" in piezas or "rag_respaldo" in piezas:
        return "RAG"
    return f"sin RAG ({metrica.get('route')})"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ronda")
    ap.add_argument("--desfasados", default="docs/robustness/golden-set/g10-criterios-desfasados.json")
    args = ap.parse_args()
    with open(RESULTADOS.format(args.ronda), encoding="utf-8") as f:
        resultado = json.load(f)
    with open(args.desfasados, encoding="utf-8") as f:
        lista = json.load(f).get("desfasados", [])
    desfasados = {(d.get("dialogo"), d.get("criterio")) for d in lista if isinstance(d, dict)}
    turnos = collections.defaultdict(list)
    for r in _jsonl(RONDAS.format(args.ronda, "jsonl")):
        turnos[r["tag"]].append(r)
    por_conv = collections.defaultdict(list)
    for m in sorted(_jsonl(RONDAS.format(args.ronda, "metricas")), key=lambda m: m["start"]):
        por_conv[str(m["conv"])].append(m)
    cuenta, ejemplos = collections.Counter(), collections.defaultdict(list)
    for dialogo in resultado["dialogues"]:
        for c in dialogo["criteria"]:
            if c["verdict"] != "no_cumple" or (dialogo["id"], c["id"]) in desfasados:
                continue
            cita = (c.get("evidencia_bot") or "")[:40].strip()
            turno = next((r for r in sorted(turnos[dialogo["id"]], key=lambda r: r["turn"])
                          if cita and cita in (r["reply"] or "")), None)
            if turno is None:
                clase = "sin cita del bot"
            else:
                metricas = por_conv.get(str(turno["conv"]), [])
                clase = _quien(metricas[turno["turn"] - 1]) if len(metricas) >= turno["turn"] else "?"
            cuenta[clase] += 1
            ejemplos[clase].append(f"{dialogo['id']} {c['id']}: {c['reason'][:150]}")
    print(f"{sum(cuenta.values())} fallos:", dict(cuenta.most_common()))
    for clase, lineas in ejemplos.items():
        print(f"\n== {clase} ({len(lineas)})")
        for linea in lineas:
            print("  -", linea)


if __name__ == "__main__":
    main()
