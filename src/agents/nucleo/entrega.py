"""Bloque 4R (C3, Plan Gadea): el pintor de la entrega. Lo que se le da al cliente en el momento de reservar lo decide
`como_reserva.entrega` y lo pinta el código, aquí, a la salida de la respuesta del escritor (el RAG o el redactor de hechos), antes
del pase del supervisor. El escritor ya no recibe enlaces de reserva (`rag_agent`, C2) ni la orden de ofrecer el pase en la reserva
(C4). Diseño: `docs/robustness/caln/diseno-bloque4r.md`.

- `ENLACE`: el enlace de su plan, del origen sabido, y la línea de quien es colombiano si no se sabe la nacionalidad (Gadea, #3741).
- `ORIGEN_PRIMERO` y quiere reservar: el origen, una vez y con el motivo; si sigue sin decirlo, pasa con un asesor (P1b, #3742).
- Un plan por el asesor (colombiano, grupo, una parte sin enlace, recogida por confirmar): si quiere reservar o pagar, pasa con un
  asesor; si no, se le dice una vez por qué lo reserva un asesor, sin preguntarle (P3, #3741).
Cada caso deja `[CORE][4R]` en el registro; el turno que pedía el enlace y se queda sin él, `enlace_que_faltaba` en [TURN_METRICS].
"""
from __future__ import annotations

import logging

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
from src.flows.state import ConversationState

logger = logging.getLogger(__name__)

_PIDE_ENLACE = frozenset({"enlace", "pago", "disponibilidad"})  # «¿me pasas el link?», «¿cómo pago?», «¿hay sitio el sábado?»
_QUIERE_RESERVAR = frozenset({"enlace", "pago"})

_PARA_RESERVAR = {"es_uno": "👉 Para reservar: {url}", "es_grupo": "👉 Para reservar: {url}", "en": "👉 To book: {url}"}
_PARA_RESERVAR_CADA = {"es_uno": "👉 *{nombre}*: {url}", "es_grupo": "👉 *{nombre}*: {url}", "en": "👉 *{nombre}*: {url}"}
_SI_ERES_COLOMBIANO = {
    "es_uno": "Si eres de nacionalidad colombiana o tienes cédula de extranjería, dímelo y te paso con un asesor para pagar en pesos.",
    "es_grupo": "Si alguno es de nacionalidad colombiana o tiene cédula de extranjería, díganmelo y les paso con un asesor para pagar en "
                "pesos.",
    "en": "If you're Colombian or hold a Colombian foreigner ID (cédula de extranjería), tell me and I'll pass you to an advisor to pay "
          "in pesos.",
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
    "es_uno": "Cuando quieras reservar, dímelo y te paso con un asesor.",
    "es_grupo": "Cuando quieran reservar, díganmelo y les paso con un asesor.",
    "en": "Whenever you want to book, just tell me and I'll pass you to an advisor.",
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
}
MOTIVO = {
    ASESOR: "pago en pesos: la reserva la cierra un asesor",
    RECOGIDA_POR_CONFIRMAR: "recogida fuera de los puntos de siempre: la confirma un asesor antes de reservar",
    GRUPO: "grupo de 5 o más: el descuento de grupo se pide antes de pagar",
    PARTE_SIN_ENLACE: "grupo con una parte del plan sin enlace: todo por el asesor",
    ORIGEN_PRIMERO: "quiere reservar y no dice desde dónde sale",
}
# Las veces de cada aviso, en `preguntas_hechas` (la tabla de qué preguntar, P11), para que ninguno se repita.
_ORIGEN_PEDIDO = "4r_origen_para_reservar"
_ASESOR_AVISADO = "4r_asesor_avisado"


def por_que(forma: str, state: ConversationState) -> str | None:
    lang = "es" if state.language == "es" else "en"
    return por_que_el_asesor(forma, lang) or (_POR_QUE.get(forma) or {}).get(clave_de_idioma_y_grupo(state))


async def pintar_la_entrega(state: ConversationState, message: str, answer: str | None, history: list | None) -> str | None:
    """La respuesta del turno con lo que toca pintar del momento de reservar (o tal cual, si el turno no pide el enlace, el pago o la
    disponibilidad). Puede pasar con un asesor (`pasar_a_persona`), antes de que el supervisor mire el pase."""
    intenciones = set(getattr(state, "_intenciones", None) or [])
    if not answer or not (intenciones & _PIDE_ENLACE) or state.ya_reservado:
        return answer
    decision = entrega(state)
    clave = clave_de_idioma_y_grupo(state)
    hechas = state.preguntas_hechas if isinstance(getattr(state, "preguntas_hechas", None), dict) else {}
    if decision.forma == ENLACE:
        return await _con_el_enlace(state, message, answer, history, clave, decision.nacionalidad_por_saber)
    if decision.forma == ORIGEN_PRIMERO and intenciones & _QUIERE_RESERVAR:
        if not hechas.get(_ORIGEN_PEDIDO):
            hechas[_ORIGEN_PEDIDO] = 1
            state.preguntas_hechas = hechas
            logger.info("[CORE][4R] quiere reservar sin saber el origen: se le pide, con el motivo (P1b)")
            return f"{answer}\n\n{_ORIGEN_PARA_RESERVAR[clave]}"
        return _pasar(state, ORIGEN_PRIMERO, answer, clave)
    if decision.forma in POR_EL_ASESOR:
        if intenciones & _QUIERE_RESERVAR:
            return _pasar(state, decision.forma, answer, clave)
        if not hechas.get(_ASESOR_AVISADO) and (motivo := por_que(decision.forma, state)):
            hechas[_ASESOR_AVISADO] = 1
            state.preguntas_hechas = hechas
            logger.info(f"[CORE][4R] {decision.forma}: se le dice una vez que lo reserva un asesor (P3)")
            return f"{answer}\n\n{motivo} {_CUANDO_QUIERAS[clave]}"
    return answer


def _pasar(state: ConversationState, forma: str, answer: str, clave: str) -> str:
    from src.agents.lead_summary import pasar_a_persona  # lazy

    pasar_a_persona(state, f"núcleo conversacional - {MOTIVO[forma]}")
    logger.info(f"[CORE][4R] {forma}: quiere reservar, pasa con un asesor")
    motivo = por_que(forma, state)
    return f"{answer}\n\n" + (f"{motivo} {_TE_PASO[clave]}" if motivo else _TE_PASO[clave])


async def _con_el_enlace(state: ConversationState, message: str, answer: str, history: list | None, clave: str,
                         nacionalidad_por_saber: bool) -> str:
    from src.agents import redactor_hechos  # lazy
    from src.flows.catalog import SERVICES  # lazy

    turno = await redactor_hechos.hechos_del_turno(state, message, history or [])
    enlaces = []
    for bloque in (turno or ([], []))[0]:
        for url in (bloque.get("enlace") or {}).values():
            if isinstance(url, str) and url.startswith("http") and url not in enlaces:
                enlaces.append(url)
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
