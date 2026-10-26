"""LAT-9 paso 2 (26-oct): el banco de la pregunta de la reserva escrita por el escritor, con el formato de
`scripts/banco_fallos.py`.

Turnos de rondas ya hechas en los que el bot acababa de hacer una pregunta de la reserva y el cliente contesta:
- `sin_dato`: sin «?» y el bot repitió la misma pregunta (con o sin «¡Perfecto! 🙌»): da las gracias, comenta algo,
  da un dato que no se entendió. Con el paso 2 contesta el escritor (decisión de Gadea del 26-oct) y el acuse solo sale
  si contestó lo preguntado.
- `pregunta`: con «?»: lo contesta el escritor, que ahora cierra él con la pregunta de la reserva. Si el mensaje
  también contestaba el dato, la pregunta cambia: aquí se ven las dos variantes (el código la corrige o el escritor
  espera al extractor).

    python -m scripts.banco_lat9p2 construir --rondas 2026-10-26-integra4-B,2026-10-26-integra3-B
    ENV_FILE=.env.dev python -m scripts.banco_fallos medir --banco docs/robustness/lat/banco-lat9p2.json \\
        --etiqueta lat9p2-A --codigo-local --reps 2

Solo del golden visible y de las tandas rotativas: NUNCA del examen oculto. Lo que se mide es el mismo criterio para
todos los casos (`PEDIA`), no el del golden. Sin API: solo lee los ficheros de las rondas.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "docs/robustness/synthetic-runs"
GOLDEN = ROOT / "docs/robustness/golden-set/golden-dialogues.json"
BANCO = ROOT / "docs/robustness/lat/banco-lat9p2.json"

PEDIA = ("La respuesta contesta a lo que dice el cliente en su último mensaje (si pregunta algo, lo contesta; si da las "
         "gracias, comenta algo o da un dato, lo reconoce sin ignorarlo) y termina con UNA sola pregunta de la reserva, "
         "la que toca: no vuelve a preguntar un dato que el cliente acaba de dar ni hace dos preguntas seguidas, y no "
         "pone «¡Perfecto!» o similar delante si el cliente no contestó lo que se le preguntó.")
MOTIVO = {
    "sin_dato": "En la ronda el bot no contestó a lo que dijo el cliente y repitió la misma pregunta de la reserva.",
    "pregunta": ("Riesgo en este turno: la respuesta a la pregunta y la pregunta de la reserva pegadas (dos preguntas "
                 "seguidas, o una pregunta por un dato que el cliente acaba de dar)."),
}
# Las preguntas de la reserva (`ask_slot`), por un trozo que no cambia: solo para construir el banco.
_DE_LA_RESERVA = ("desde dónde saldrías", "buzo certificado", "buzos certificados", "más de 2 años", "nacionalidad",
                  "cuántas personas", "cuántos son", "con cuál te animas", "en qué hotel", "refresher", "qué edad",
                  "where would you", "certified diver", "more than 2 years", "colombian", "how many", "which one",
                  "which hotel", "how old", "te animas", "shall we")


def _ultima_pregunta(texto: str) -> str:
    lineas = [ln.strip() for ln in (texto or "").strip().splitlines() if ln.strip()]
    return next((ln for ln in reversed(lineas) if "?" in ln), "")


def _de_la_reserva(pregunta: str) -> bool:
    return any(t in pregunta.lower() for t in _DE_LA_RESERVA)


def _casos_de(ronda: str, ocultos: set[str]) -> list[dict]:
    filas = [json.loads(ln) for ln in (RUNS / f"{ronda}.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    por_conv = collections.defaultdict(list)
    for f in filas:
        por_conv[f["conv"]].append(f)
    casos = []
    for turnos in por_conv.values():
        turnos.sort(key=lambda f: f["turn"])
        if turnos[0]["tag"] in ocultos:
            continue
        for i in range(1, len(turnos)):
            antes, ahora = turnos[i - 1], turnos[i]
            pregunta_antes = _ultima_pregunta(antes["reply"])
            if not _de_la_reserva(pregunta_antes) or (ahora["reply"] or "").startswith("ERROR"):
                continue
            if "?" in ahora["msg"]:
                tipo = "pregunta"
            elif _ultima_pregunta(ahora["reply"]) == pregunta_antes:
                tipo = "sin_dato"
            else:
                continue
            historial = []
            for previo in turnos[:i]:
                historial += [{"role": "user", "content": previo["msg"]},
                              {"role": "assistant", "content": previo["reply"] or ""}]
            casos.append({
                "dialogo": ahora["tag"], "criterio": f"lat9p2:{tipo}", "pedia": PEDIA, "veredicto": "no_cumple",
                "motivo_juez": MOTIVO[tipo], "turno": str(ahora["turn"]), "pieza": tipo,
                "mensaje_cliente": ahora["msg"], "respuesta_ronda": ahora["reply"], "historial": historial,
                "ronda": ronda, "tarea": "LAT-9",
            })
    return casos


def construir(rondas: list[str], por_tipo: int) -> list[dict]:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8-sig"))
    ocultos = {d["id"] for d in golden["dialogues"] if d.get("suite") == "oculto"}
    vistos, por_clase = set(), collections.defaultdict(list)
    for ronda in rondas:
        for caso in _casos_de(ronda, ocultos):
            # Un caso por diálogo y tipo: que el banco mire muchas conversaciones, no la misma pregunta repetida.
            clave = (caso["dialogo"], caso["pieza"])
            if clave not in vistos:
                vistos.add(clave)
                por_clase[caso["pieza"]].append(caso)
    elegidos = [c for tipo in ("sin_dato", "pregunta") for c in por_clase[tipo][:por_tipo]]
    for i, caso in enumerate(elegidos, 1):
        caso["id"] = f"l9p2-{i:02d}"
    return elegidos


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("accion", choices=["construir"])
    ap.add_argument("--rondas", required=True, help="rondas, separadas por comas")
    ap.add_argument("--por-tipo", type=int, default=20)
    args = ap.parse_args()
    casos = construir(args.rondas.split(","), args.por_tipo)
    BANCO.parent.mkdir(parents=True, exist_ok=True)
    BANCO.write_text(json.dumps({
        "about": __doc__.split("\n\n")[0], "rondas": args.rondas.split(","), "fallos": casos,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(casos)} casos → {BANCO.relative_to(ROOT)}: "
          + ", ".join(f"{k} {v}" for k, v in collections.Counter(c["pieza"] for c in casos).most_common()))


if __name__ == "__main__":
    main()
