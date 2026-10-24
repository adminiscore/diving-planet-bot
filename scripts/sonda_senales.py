"""CAL-E/CAL-C: ver, DENTRO de PRE, qué SEÑALES y qué idioma salen en cada turno de un caso del banco.

Reproduce los turnos del caso (los mismos que usa `banco_fallos medir`, sin juez: no gasta el verificador) y, turno a
turno, imprime lo que decidieron las piezas que mandan en el camino del mensaje:

- las SEÑALES del enrutador (Jev o el LLM de respaldo) tal como las ve el núcleo;
- el IDIOMA que fija el estado y el que dijo el extractor;
- la traza de las líneas que deciden ([ROUTER], [EXTRACT], [CORE][IDIOMA], [SUPERVISOR]);
- la respuesta.

Sirve para saber si un arreglo no mueve el caso porque la señal no salta o porque salta y el turno va por otro camino.

    ENV_FILE=.env.dev python -m scripts.sonda_senales --ids cal-12,cal-29,cal-33 --codigo-local \\
        --flag <flag> [--flag <otro>]

Coste: una conversación por caso (céntimos). La cuenta de OpenAI/OpenRouter es la de PRE.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANCO = ROOT / "docs/robustness/cal/banco-fallos.json"

_REMOTO = r'''
import asyncio, json, logging
from src.agents import escalation, supervisor
from src.config import settings
from src.flows.state import ConversationState
CASOS = json.loads(CASOS_JSON)
for _f in FLAGS:  # "no:X" APAGA X solo en este proceso (17-oct: medir con PRE en la rama de otro)
    setattr(settings, _f.removeprefix("no:"), not _f.startswith("no:"))

senales = []
_orig = escalation.detect_routing_signals
async def _spy(message, **kw):
    out = await _orig(message, **kw)
    senales.append({"mensaje": message[:120], "senales": {k: v for k, v in (out or {}).items()}})
    return out
escalation.detect_routing_signals = _spy
supervisor.detect_routing_signals = _spy

traza = []
class _Traza(logging.Handler):
    def emit(self, rec):
        m = rec.getMessage()
        if any(t in m for t in ("[ROUTER]", "[EXTRACT]", "[CORE][IDIOMA]", "[SUPERVISOR]", "[AVISOS]",
                                "[RAG][REWRITE]", "[RAG][GROUNDING]", "[RAG][COMPLETITUD]", "[RAG][CANONICAL", "[RAG][AVISO_FINAL]")):
            traza.append(m[:300])
logging.getLogger().addHandler(_Traza())
logging.getLogger().setLevel(logging.INFO)

async def main():
    for caso in CASOS:
        st = ConversationState(conversation_id="sonda-senales-" + caso["id"])
        for i, msg in enumerate(caso["turnos"], 1):
            senales.clear(); traza.clear()
            try:
                reply = await supervisor.route_message(st, msg)
            except Exception as exc:  # noqa: BLE001
                reply = "ERROR %s: %s" % (type(exc).__name__, exc)
            print(json.dumps({"id": caso["id"], "turno": i, "ultimo": i == len(caso["turnos"]), "msg": msg,
                              "senales": list(senales), "traza": list(traza), "reply": reply,
                              "idioma": st.language, "idioma_detectado": st.detected_language},
                             ensure_ascii=False, default=str), flush=True)

asyncio.run(main())
'''


def casos_del_banco(ids: list[str] | None, tarea: str | None) -> list[dict]:
    datos = json.loads(BANCO.read_text(encoding="utf-8"))
    casos = []
    for f in datos["fallos"]:
        if not f["turno"] or (ids and f["id"] not in ids) or (tarea and f.get("tarea") != tarea):
            continue
        turnos = [h["content"] for h in f["historial"] if h["role"] == "user"] + [f["mensaje_cliente"]]
        casos.append({"id": f["id"], "criterio": f["criterio"], "turnos": turnos})
    return casos


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ids", help="solo estos casos (cal-12,cal-29…)")
    ap.add_argument("--tarea", help="solo los casos de esta tarea (CAL-E…)")
    ap.add_argument("--flag", action="append", default=[], help="interruptor encendido solo en ese proceso")
    ap.add_argument("--codigo-local", action="store_true", help="con el código local (sin desplegar)")
    ap.add_argument("--solo-ultimo", action="store_true", help="imprime solo el turno que mide el banco")
    ap.add_argument("--out", help="JSON de salida")
    args = ap.parse_args()

    casos = casos_del_banco(args.ids.split(",") if args.ids else None, args.tarea)
    if not casos:
        raise SystemExit("ningún caso con turno para esos filtros")
    print(f"{len(casos)} casos: {', '.join(c['id'] for c in casos)} · flags: {args.flag or 'ninguno'}")

    from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

    codigo = subir_codigo_local() if args.codigo_local else None
    script = f"CASOS_JSON = {json.dumps(casos, ensure_ascii=False)!r}\nFLAGS = {args.flag!r}\n{_REMOTO}"
    r = pre_ssh(docker_python({}, codigo_local=codigo), input_text=script,
                timeout=240 + 60 * sum(len(c["turnos"]) for c in casos))
    filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
    if not filas:
        raise SystemExit(f"sin salida: {(r.stderr or r.stdout)[-800:]}")
    for fila in filas:
        if args.solo_ultimo and not fila["ultimo"]:
            continue
        marca = " ← el turno que mide el banco" if fila["ultimo"] else ""
        print("=" * 110)
        print(f"[{fila['id']}] turno {fila['turno']}{marca}: {fila['msg'][:140]}")
        print(f"  idioma: {fila['idioma']} (detectado {fila['idioma_detectado']})")
        for s in fila["senales"]:
            print(f"  señales: {s['senales'] or '(ninguna)'}")
        for t in fila["traza"]:
            print(f"    · {t}")
        print(f"  respuesta: {fila['reply'][:300]}")
    if args.out:
        Path(args.out).write_text(json.dumps(filas, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\n→ {args.out}")


if __name__ == "__main__":
    main()
