"""Reproduccion de los hallazgos antiguos de la tarea 7 (2026-09-15).

Conversaciones completas con `route_message` y el LLM real. RAG va mockeado (sin BD
local), lo que no afecta a estos casos. El driver contesta el slot que el bot pide
(`core_pending_slot`), sin suponer un orden. Detalle y causas en
docs/robustness/progress-log.md ("Tarea 7").

    ENV_FILE=.env.dev python -m scripts.repro_old_findings [repeticiones] [casos]

casos: lista separada por comas de drip,correccion,correccion_antes,f01,f01_conversacion,h_total,g_numeros,tour
(por defecto todos).
"""

import asyncio
import logging
import sys
from unittest.mock import AsyncMock, patch

from scripts import battery_group_allocation_gate as bg
from src.agents.supervisor import route_message
from src.flows.state import ConversationState

ANSWERS = {
    "activity": "buceo", "certification": "sí, estamos certificados", "location": "desde cartagena",
    "hotel": "no tenemos hotel todavía", "safety": "no, buceamos hace 6 meses", "refresher": "no gracias",
    "qty": "somos 2", "ages": "somos adultos", "nationality": "somos colombianos",
    "companion_qty": "uno", "companion_activity_choice": "snorkel", "course_level": "open water",
    "cert_or_course": "ya la tenemos", "confirm_correction": "sí",
}


def _snap(st):
    return (f"pend={st.core_pending_slot} act={st.detected_activity} gs={st.detected_group_size} "
            f"alloc={st.detected_group_allocation} col={st.is_colombian} cert={st.is_certified} "
            f"loc={st.location} cur={st.mixed_display_currency} "
            f"cart={[(i.get('type'), i.get('qty') or i.get('quantity')) for i in st.mixed_cart]}")


async def _say(st, msg, log):
    reply = await route_message(st, msg)
    log.append(f"  >>> {msg}\n  <<< {reply[:260]!r}\n      {_snap(st)}")
    return reply


def _priced(reply, st):
    return ("COP" in reply or "USD" in reply) and st.core_pending_slot is None


async def _autopilot(st, log, max_turns=8, stop=lambda reply, st: False):
    for _ in range(max_turns):
        slot = st.core_pending_slot
        if slot not in ANSWERS:
            return
        if stop(await _say(st, ANSWERS[slot], log), st):
            return


def _new(cid):
    st = ConversationState(conversation_id=cid)
    st.language = "es"
    return st


async def drip(rep):
    """7a: la actividad del acompanante llega en un turno posterior, con otro slot pendiente."""
    st, log = _new(f"drip-{rep}"), []
    await _say(st, "hola, quiero bucear con mi amigo, yo soy certificado", log)
    await _autopilot(st, log, max_turns=2)
    await _say(st, "él quiere hacer snorkel", log)
    await _autopilot(st, log, stop=_priced)
    return log


async def correccion(rep):
    """7b: correccion de nacionalidad despues de mostrar el precio."""
    st, log = _new(f"corr-{rep}"), []
    await _say(st, "hola, somos 2 buzos certificados y queremos bucear", log)
    await _autopilot(st, log, max_turns=9, stop=_priced)
    await _say(st, "espera, en realidad no somos colombianos", log)
    return log


async def correccion_antes(rep):
    """7b: correcciones antes del precio (certificacion y ubicacion)."""
    log = []
    for opening, correction in (
        ("hola, somos 2 buzos certificados y queremos bucear", "perdón, en realidad no estamos certificados"),
        ("hola, somos 2 buzos certificados, salimos desde cartagena", "mejor desde las islas, estamos en isla grande"),
    ):
        st = _new(f"corr-antes-{rep}")
        await _say(st, opening, log)
        await _say(st, correction, log)
    return log


async def f01(rep):
    """7c: cambio legitimo del reparto ya guardado (escenario f01 de la bateria de grupo)."""
    spec = next(s for s in bg.SCENARIOS if s["id"].startswith("f01"))
    got = await bg._run(spec, True, True)
    return [f"  {spec['message']!r} estado_inicial={spec['state']} -> {got}"]


async def f01_conversacion(rep):
    """7c: el mismo cambio de reparto en una conversacion cerrada, confirmando con "sí".
    La apertura dice las cifras ("2 buceamos y 1 hace snorkel") para no caer en el
    hallazgo H, que corrompe el total antes de llegar a la correccion."""
    st, log = _new(f"f01-conv-{rep}"), []
    await _say(st, "hola, somos 3: 2 buceamos certificados y mi suegra hace snorkel", log)
    await _autopilot(st, log, stop=_priced)
    await _say(st, "al final mi suegra tambien bucea, no hace snorkel", log)
    await _autopilot(st, log, max_turns=2, stop=_priced)
    return log


async def h_total(rep):
    """H: los tramos que se preguntan de un grupo con total sabido no suman encima."""
    log = []
    for opening in (
        "hola, vamos 3, mi pareja y yo buceamos y mi suegra hace snorkel, estamos certificados",
        "hola, vamos 5, mis amigos bucean y mis primos hacen snorkel, estamos certificados",
    ):
        st = _new(f"h-{rep}")
        await _say(st, opening, log)
        await _autopilot(st, log, stop=_priced)
    return log


async def g_numeros(rep):
    """G: con "¿para cuantas personas?" pendiente, un numero de otra magnitud no es el total."""
    st, log = _new(f"g-{rep}"), []
    # Plural sin cantidad: "soy certificado" se lee como una sola persona y nunca pregunta el total.
    await _say(st, "hola, queremos bucear, estamos certificados, salimos desde cartagena", log)
    for msg in ("mi hijo tiene 9 años", "llegamos el 12", "2 inmersiones", "somos 3"):
        if st.core_pending_slot != "qty":
            break
        await _say(st, msg, log)
    return log


async def tour(rep):
    """7d: peticion de informacion sin "?" ni palabra-pregunta al principio."""
    st, log = _new(f"tour-{rep}"), []
    await _say(st, "hola, quiero bucear, somos 2 certificados", log)
    await _say(st, "primero dime qué incluye el tour", log)
    return log


CASES = {"drip": drip, "correccion": correccion, "correccion_antes": correccion_antes, "f01": f01,
         "f01_conversacion": f01_conversacion, "h_total": h_total, "g_numeros": g_numeros, "tour": tour}


async def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    wanted = sys.argv[2].split(",") if len(sys.argv) > 2 else list(CASES)
    rag = AsyncMock(return_value="RAG_MARCADOR")
    with patch("src.agents.supervisor.rag_answer", new=rag), patch("src.agents.rag_agent.rag_answer", new=rag):
        for name in wanted:
            for rep in range(reps):
                rag.reset_mock()
                log = await CASES[name](rep)
                print(f"\n=== {name} rep{rep} (RAG llamado {rag.await_count} veces)\n" + "\n".join(log))


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
