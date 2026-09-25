"""Sonda FIEL: los dialogos afectados pasados por el NUCLEO de verdad (mismo camino que
`replay_golden_local`: historial real, lista de campos real), con el matiz de la hipotesis
apagado y encendido. La sonda de frases sueltas no valia: sin historial el LLM ya se
abstenia en 2 de los 3 casos, y en el replay real no.
"""
import asyncio
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import scripts.replay_golden_local as replay  # noqa: E402 — fija el entorno de PRE e importa todo
from src.agents import conversational_core as core  # noqa: E402
from src.agents import escalation, supervisor  # noqa: E402
from src.config import settings  # noqa: E402
from src.flows.state import ConversationState  # noqa: E402
from src.prompts import booking  # noqa: E402

MATIZ_EN = (
    " A place, product, course, nationality or price named INSIDE a question or a "
    "hypothesis is what the customer is ASKING ABOUT, not something they state about "
    "themselves: 'do you recommend hotels on the island?', 'what if I stayed in Rosario?', "
    "'in case I did the Open Water course', 'is the price for Colombians?' — omit the field."
)
MATIZ_ES = (
    " Un lugar, producto, curso, nacionalidad o precio nombrado DENTRO de una pregunta o de "
    "una hipótesis es lo que el cliente PREGUNTA, no algo que afirme de sí mismo: «¿me "
    "recomiendas hoteles en la isla?», «¿y si me quedo en Rosario?», «por si hiciera el curso "
    "Open Water», «¿el precio es para colombianos?» — omite el campo."
)
FOOT_EN, FOOT_ES = booking._VERIFICATION_FOOTER_EN, booking._VERIFICATION_FOOTER_ES

DIALOGOS = [
    "curso-open-water-transporte-y-regreso-otro-dia",   # location inventado (hipotesis)
    "referral-mas-refresher-hotel-y-domingo-pascua",    # location inventado (pregunta)
    "acompanante-madre-desde-cartagena",                # location inventado (la isla de la madre)
    "recogida-ubuntu-comida-y-certificacion",           # actividad pisada por una pregunta
    # controles: datos buenos que NO se pueden perder
    "paquete-5-inmersiones",
    "colombianos-precio-minicurso-dos-inmersiones",
    "nino-7-familia",
    "desde-islas-buzo-certificado",
]
CAMPOS = ("detected_activity", "is_certified", "location", "detected_location", "is_colombian",
          "detected_group_size", "hotel")


async def pasada(dialogos, activo):
    booking._VERIFICATION_FOOTER_EN = FOOT_EN + (MATIZ_EN if activo else "")
    booking._VERIFICATION_FOOTER_ES = FOOT_ES + (MATIZ_ES if activo else "")
    out = {}
    for did, turns in dialogos:
        st = ConversationState(conversation_id=f"sonda-{did}-{activo}")
        for i, msg in enumerate(turns, 1):
            try:
                await supervisor.route_message(st, msg)
            except Exception as exc:  # noqa: BLE001
                print(f"  ERROR {did}#{i}: {type(exc).__name__}: {exc}")
            out[(did, i)] = {f: getattr(st, f, None) for f in CAMPOS}
    return out


async def main():
    settings.answer_and_continue = True
    supervisor.rag_answer = replay._rag
    core.compose_acknowledgement = lambda *a, **k: asyncio.sleep(0, result="")
    core.extract_notes = lambda *a, **k: asyncio.sleep(0, result=[])
    escalation.escalate_to_human = replay._noop
    supervisor.escalate_to_human = replay._noop

    todos = dict(replay.dialogues())
    ds = [(d, todos[d]) for d in DIALOGOS if d in todos]
    print(f"dialogos: {len(ds)} | turnos: {sum(len(t) for _, t in ds)}\n")

    off = await pasada(ds, False)
    on = await pasada(ds, True)

    for did, turns in ds:
        print(f"\n### {did}")
        for i, msg in enumerate(turns, 1):
            a = {f: v for f, v in off[(did, i)].items() if v not in (None, [], {})}
            b = {f: v for f, v in on[(did, i)].items() if v not in (None, [], {})}
            marca = "  <<< CAMBIA" if a != b else ""
            print(f"  #{i} {msg[:100]!r}{marca}")
            if a != b:
                print(f"     sin matiz: {a}")
                print(f"     con matiz: {b}")

asyncio.run(main())
