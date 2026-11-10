"""Bloque 4R (C3, Plan Gadea): el pintor de la entrega. Lo que se le da al cliente en el momento de reservar lo decide
`como_reserva.entrega` y lo pinta el código, aquí, a la salida de la respuesta del escritor (el RAG o el redactor de hechos), antes
del pase del supervisor. El escritor ya no recibe enlaces de reserva (`rag_agent`, C2) ni la orden de ofrecer el pase en la reserva
(C4). Diseño: `docs/robustness/caln/diseno-bloque4r.md`.

- `ENLACE`: el enlace de su plan, del origen sabido, y la línea de quien es colombiano si no se sabe la nacionalidad (Gadea, #3741).
- `ORIGEN_PRIMERO` y quiere reservar: el origen, una vez y con el motivo; si sigue sin decirlo, pasa con un asesor (P1b, #3742).
- Un plan por el asesor (colombiano, grupo, una parte sin enlace, recogida por confirmar, o un plan que no tiene enlace): si quiere
  reservar o pagar, pasa con un asesor; si no, se le dice una vez por qué lo reserva un asesor, sin preguntarle (P3, #3741).
No pinta nada con la tarjeta en el turno (la pinta `_finalize`), en una conversación ya pasada, a quien ya reservó ni sobre la respuesta
segura. Los textos no llevan «te paso» ni «¿quieres que…?»: si no, un «ok» detrás contaría como aceptar el pase
(`supervisor.acepta_la_oferta_del_asesor`).
Cada caso deja `[CORE][4R]` en el registro; el turno que pedía el enlace y se queda sin él, `enlace_que_faltaba` en [TURN_METRICS].
"""
from __future__ import annotations

import logging
import re

from src.flows.como_reserva import (
    ASESOR,
    ENLACE,
    GRUPO,
    ORIGEN_PRIMERO,
    PARTE_SIN_ENLACE,
    POR_EL_ASESOR,
    RECOGIDA_POR_CONFIRMAR,
    clave_de_idioma_y_grupo,
    entrega,
    por_que_el_asesor,
)
from src.flows.state import ConversationState, Step

logger = logging.getLogger(__name__)

PLAN_SIN_ENLACE = "plan_sin_enlace"  # el plan no se reserva por la web (Divemaster, las 4 diurnas, el privado…): s03g
_PIDE_ENLACE = frozenset({"enlace", "pago", "disponibilidad"})  # «¿me pasas el link?», «¿cómo pago?», «¿hay sitio el sábado?»
_QUIERE_RESERVAR = frozenset({"enlace", "pago"})

_PARA_RESERVAR = {"es_uno": "👉 Para reservar: {url}", "es_grupo": "👉 Para reservar: {url}", "en": "👉 To book: {url}"}
_PARA_RESERVAR_CADA = {"es_uno": "👉 *{nombre}*: {url}", "es_grupo": "👉 *{nombre}*: {url}", "en": "👉 *{nombre}*: {url}"}
# pago-y-reserva: un grupo mixto paga en USD con el enlace; solo si TODOS son colombianos o residentes, el pago en pesos con un asesor.
_SI_ERES_COLOMBIANO = {
    "es_uno": "Si eres de nacionalidad colombiana o tienes cédula de extranjería, dímelo antes de pagar: el pago en pesos lo coordina un "
              "asesor.",
    "es_grupo": "Si todos son de nacionalidad colombiana o tienen cédula de extranjería, díganmelo antes de pagar: el pago en pesos lo "
                "coordina un asesor.",
    "en": "If you're Colombian or hold a Colombian foreigner ID (cédula de extranjería), let me know before paying: an advisor arranges "
          "payment in pesos.",
}
_ORIGEN_PARA_RESERVAR = {
    "es_uno": "Para darte el enlace necesito saber desde dónde sales: ¿desde Cartagena o ya estás en las Islas del Rosario?",
    "es_grupo": "Para darles el enlace necesito saber desde dónde salen: ¿desde Cartagena o ya están en las Islas del Rosario?",
    "en": "To give you the link I need to know where you're leaving from: Cartagena, or are you already on the Rosario Islands?",
}
_TE_PASO = {
    "es_uno": "Te paso con un asesor para que te ayude a reservar; enseguida se pone en contacto contigo. 🌊",
    "es_grupo": "Les paso con un asesor para que les ayude a reservar; enseguida se pone en contacto con ustedes. 🌊",
    "en": "I'm passing you to an advisor to help you book; they'll be in touch shortly. 🌊",
}
_CUANDO_QUIERAS = {
    "es_uno": "Cuando quieras reservar, dímelo.",
    "es_grupo": "Cuando quieran reservar, díganmelo.",
    "en": "Whenever you want to book, just let me know.",
}
_POR_QUE = {  # los que `por_que_el_asesor` no tiene (GRUPO y PARTE_SIN_ENLACE salen de allí, con las cifras de discounts.json)
    ASESOR: {
        "es_uno": "Como pagas en pesos, la reserva te la cierra un asesor por este chat, con un enlace bancario, QR o Llave.",
        "es_grupo": "Como pagan en pesos, la reserva se la cierra un asesor por este chat, con un enlace bancario, QR o Llave.",
        "en": "Since you pay in pesos, an advisor closes the booking with you in this chat, with a bank link, QR or Llave.",
    },
    RECOGIDA_POR_CONFIRMAR: {
        "es_uno": "Como te alojas fuera de nuestros puntos de recogida, un asesor te confirma la recogida antes de reservar.",
        "es_grupo": "Como se alojan fuera de nuestros puntos de recogida, un asesor les confirma la recogida antes de reservar.",
        "en": "Since you're staying outside our usual pick-up points, an advisor confirms the pick-up with you before booking.",
    },
    PLAN_SIN_ENLACE: {
        "es_uno": "Este plan no se reserva por la web: lo reserva un asesor.",
        "es_grupo": "Este plan no se reserva por la web: se lo reserva un asesor.",
        "en": "This plan can't be booked online: an advisor books it for you.",
    },
}
MOTIVO = {
    ASESOR: "pago en pesos: la reserva la cierra un asesor",
    RECOGIDA_POR_CONFIRMAR: "recogida fuera de los puntos de siempre: la confirma un asesor antes de reservar",
    GRUPO: "grupo de 5 o más: el descuento de grupo se pide antes de pagar",
    PARTE_SIN_ENLACE: "grupo con una parte del plan sin enlace: todo por el asesor",
    PLAN_SIN_ENLACE: "el plan no tiene enlace de reserva: lo reserva un asesor",
    ORIGEN_PRIMERO: "quiere reservar y no dice desde dónde sale",
}
# Las veces de cada aviso, en `preguntas_hechas` (la tabla de qué preguntar, P11), para que ninguno se repita.
_ORIGEN_PEDIDO = "4r_origen_para_reservar"
# Una pregunta del origen que ya va en la respuesta (la del redactor, la de la puerta o la de la tabla): no se pone otra.
_YA_PREGUNTA_EL_ORIGEN = re.compile(r"desde cartagena[^?]{0,80}\?|from cartagena[^?]{0,80}\?|on the (rosario )?islands\?", re.I)


def por_que(forma: str, state: ConversationState) -> str | None:
    lang = "es" if state.language == "es" else "en"
    return por_que_el_asesor(forma, lang) or (_POR_QUE.get(forma) or {}).get(clave_de_idioma_y_grupo(state))


def _no_pinta(state: ConversationState, answer: str | None, intenciones: set[str]) -> bool:
    from src.agents.rag_agent import is_fallback_answer  # lazy

    return (not answer or not (intenciones & _PIDE_ENLACE) or state.ya_reservado or state.step == Step.ESCALATE
            or bool(state.pending_escalation_reason) or getattr(state, "_tarjeta_del_turno", False) or is_fallback_answer(answer))


async def pintar_la_entrega(state: ConversationState, message: str, answer: str | None, history: list | None) -> str | None:
    """La respuesta del turno con lo que toca pintar del momento de reservar (o tal cual, si el turno no pide el enlace, el pago o la
    disponibilidad). Puede pasar con un asesor (`pasar_a_persona`), antes de que el supervisor mire el pase."""
    intenciones = set(getattr(state, "_intenciones", None) or [])
    if _no_pinta(state, answer, intenciones):
        return answer
    from src.agents.nucleo.extractor import con_lo_guardado  # lazy

    await con_lo_guardado(state, message)  # decide con lo que este mensaje ya dejó guardado (el origen, la nacionalidad)
    decision = entrega(state)
    clave = clave_de_idioma_y_grupo(state)
    hechas = state.preguntas_hechas if isinstance(getattr(state, "preguntas_hechas", None), dict) else {}
    forma = decision.forma
    if forma == ENLACE:
        enlaces, sin_enlace = await _enlaces_del_turno(state, message, history)
        if not enlaces and sin_enlace:
            forma = PLAN_SIN_ENLACE  # s03g: los hechos dicen que el plan lo reserva un asesor
        else:
            return _con_el_enlace(answer, enlaces, clave, decision.nacionalidad_por_saber)
    if forma == ORIGEN_PRIMERO:
        if not intenciones & _QUIERE_RESERVAR:
            return answer
        if not hechas.get(_ORIGEN_PEDIDO):
            hechas[_ORIGEN_PEDIDO] = 1
            state.preguntas_hechas = hechas
            if _YA_PREGUNTA_EL_ORIGEN.search(answer):
                return answer  # ya lo pregunta (sin el motivo): cuenta como esta vez; si sigue sin decirlo, el asesor
            logger.info("[CORE][4R] quiere reservar sin saber el origen: se le pide, con el motivo (P1b)")
            return f"{answer}\n\n{_ORIGEN_PARA_RESERVAR[clave]}"
        return _pasar(state, ORIGEN_PRIMERO, answer, clave)
    if forma in (*POR_EL_ASESOR, PLAN_SIN_ENLACE):
        if intenciones & _QUIERE_RESERVAR:
            return _pasar(state, forma, answer, clave)
        avisado = f"4r_asesor_{forma}"
        if not hechas.get(avisado) and (motivo := por_que(forma, state)):
            hechas[avisado] = 1
            state.preguntas_hechas = hechas
            logger.info(f"[CORE][4R] {forma}: se le dice una vez que lo reserva un asesor (P3)")
            return f"{answer}\n\n{motivo} {_CUANDO_QUIERAS[clave]}"
    return answer


def _pasar(state: ConversationState, forma: str, answer: str, clave: str) -> str:
    from src.agents.lead_summary import pasar_a_persona  # lazy

    pasar_a_persona(state, f"núcleo conversacional - {MOTIVO[forma]}")
    logger.info(f"[CORE][4R] {forma}: quiere reservar, pasa con un asesor")
    motivo = por_que(forma, state)
    return f"{answer}\n\n" + (f"{motivo} {_TE_PASO[clave]}" if motivo else _TE_PASO[clave])


async def _enlaces_del_turno(state: ConversationState, message: str, history: list | None) -> tuple[list[str], bool]:
    """Los enlaces de reserva de los planes de este turno (de los hechos, con el origen sabido) y si alguno es de un plan sin enlace."""
    from src.agents import redactor_hechos  # lazy

    turno = await redactor_hechos.hechos_del_turno(state, message, history or [])
    enlaces, sin_enlace = [], False
    for bloque in (turno or ([], []))[0]:
        enlace = bloque.get("enlace") or {}
        sin_enlace = sin_enlace or enlace.get("asesor") is True
        for url in enlace.values():
            if isinstance(url, str) and url.startswith("http") and url not in enlaces:
                enlaces.append(url)
    return enlaces, sin_enlace


def _con_el_enlace(answer: str, enlaces: list[str], clave: str, nacionalidad_por_saber: bool) -> str:
    from src.flows.catalog import SERVICES  # lazy

    nuevos = [u for u in enlaces if u not in answer]
    if not nuevos:
        if not enlaces:
            from src.observability import note_turn  # lazy

            note_turn(enlace_que_faltaba=True)
            logger.info("[CORE][4R] el turno pedía el enlace y los hechos no lo tienen (enlace_que_faltaba)")
        return answer
    if len(nuevos) == 1:
        lineas = [_PARA_RESERVAR[clave].format(url=nuevos[0])]
    else:
        campo = "name_es" if clave != "en" else "name_en"
        nombres = {(s.get(k) or "").split("?")[0]: s.get(campo) for s in SERVICES.values() for k in ("booking_url", "booking_url_island")}
        otro = "Reserva" if clave != "en" else "Booking"
        lineas = [_PARA_RESERVAR_CADA[clave].format(nombre=nombres.get(u.split("?")[0]) or otro, url=u) for u in nuevos]
    if nacionalidad_por_saber:
        lineas.append(_SI_ERES_COLOMBIANO[clave])
    logger.info(f"[CORE][4R] el enlace lo pinta el código ({len(nuevos)})")
    return f"{answer}\n\n" + "\n".join(lineas)
