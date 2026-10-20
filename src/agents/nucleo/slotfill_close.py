"""Nodo `slotfill_close` del subgrafo de la reserva: `_slotfill_close_phase` (elegir y preguntar el hueco que falta o
cerrar la reserva: carrito, `_finalize`), y el acuse en paralelo, que se lanza en `setup` y se usa aquí.

s4-2 (19-oct): movido tal cual desde `conversational_core.py`, que lo re-exporta. Ver `src/agents/nucleo/__init__.py`.
"""

from __future__ import annotations

import asyncio
import logging

from src.agents.conversational_core import (
    _IMPORTE_RE,
    _JUST_ANSWERED_PHRASE,
    _SLOTS_APLAZABLES,
    SLOT_COMPANION_ACTIVITY,
    SLOT_COMPANION_QTY,
    SLOT_SAFETY,
    _answer_asks_the_origin,
    _answer_replaces_the_booking_question,
    _booking_context_summary,
    _cart_item,
    _effective_activity,
    _es_pregunta_de_origen,
    _fijar_origen_antes_del_precio,
    _group_allocation_fully_resolved,
    _has_pending_answer,
    _is_rag_fallback,
    _known_field_values,
    _merge_pending_undecided,
    _rag_answer,
    _same_for_customer,
    _take_parallel_answer,
    ask_slot,
    next_missing_slot,
)
from src.agents.llm_extractor import compose_acknowledgement
from src.config import settings
from src.domain import activities as dom
from src.flows import cart_render
from src.flows.state import ConversationState, Step
from src.flows.textos import de_cartagena
from src.utils import money

logger = logging.getLogger("uvicorn.error")


def _tarjeta_sin_seguridad(state: ConversationState, nxt: str | None, prev_pending: str | None) -> bool:
    """CAL-F (flag `tarjeta_sin_seguridad`, decisión de Gadea, 18-oct): ¿sale ya la tarjeta con el precio aunque falte la
    respuesta de seguridad? Sí cuando es lo ÚNICO que falta y el cliente no la contestó en este mensaje (se la hicimos
    en el anterior). pareja-certificados-cop-descuento-almuerzo (3/3): la pareja preguntaba por un "bono" y por el
    almuerzo, el bot repetía "¿más de 2 años?" y la tarjeta con el precio no salía nunca. El aplazamiento de EX-FLUJO-1
    no servía: siendo la última pregunta, el resumen la volvía a hacer en el mismo turno."""
    return bool(
        settings.tarjeta_sin_seguridad and nxt == SLOT_SAFETY and prev_pending == SLOT_SAFETY
        and next_missing_slot(state, saltar=frozenset({SLOT_SAFETY})) is None
    )


def _nota_seguridad(state: ConversationState) -> str:
    """La pregunta de seguridad, una vez, dentro de la tarjeta, con el precio del refresher (del catálogo)."""
    precio = cart_render.refresher_price_text(state, una_moneda=True)  # una sola moneda por mensaje (Gadea)
    if state.language == "es":
        return ("\n\n⚠️ Si alguno lleva *más de 2 años* sin bucear, se añade el *refresher* (repaso en el agua antes de "
                f"la inmersión): *{precio}* por persona. "
                + de_cartagena("¿Es el caso de alguno de ustedes?" if (state.detected_group_size or 1) > 1
                               else "¿Es tu caso?", "¿Es vuestro caso?"))
    return ("\n\n⚠️ If anyone hasn't dived for *more than 2 years*, a *refresher* is added (a review in the water before "
            f"the dive): *{precio}* per person. Is that your case?")


def _siguiente_pregunta(state: ConversationState, prev_pending: str | None) -> str | None:
    """EX-FLUJO-1 (flag `aplazar_pregunta_sin_respuesta`, decisión de Gadea, 14-oct): si el cliente no contestó la
    pregunta del turno anterior (sigue faltando ese dato), no se repite: se aplaza y se pregunta otra cosa; las
    aplazadas vuelven justo antes del resumen, cuando no falta nada más. Ronda atencion-B2: "¿Ha pasado más de 2 años
    desde la última inmersión?" salía tres turnos seguidos mientras el cliente daba fechas y su regreso."""
    nxt = next_missing_slot(state)
    if not settings.aplazar_pregunta_sin_respuesta or nxt is None:
        return nxt
    # Ronda flujo1-B2: aplazar a la PRIMERA pregunta sin contestar reordenaba casi todas las conversaciones ("Última
    # cosa… ¿sois colombianos?" demasiado pronto; el acuse tomaba la respuesta a una aplazada por la de la pendiente).
    # El problema era el bucle: se pregunta como mucho dos veces seguidas y a la tercera se aplaza.
    state.veces_sin_respuesta = state.veces_sin_respuesta + 1 if nxt == prev_pending else 0
    if (nxt == prev_pending and state.veces_sin_respuesta >= 2 and nxt in _SLOTS_APLAZABLES
            and nxt not in state.preguntas_aplazadas):
        state.preguntas_aplazadas.append(nxt)
        logger.info(f"[CORE][APLAZA] el cliente no contestó {nxt!r} dos veces: se pregunta antes del resumen")
    otro = next_missing_slot(state, saltar=set(state.preguntas_aplazadas))
    return otro if otro is not None else nxt


def _prune_applied_corrections(state: ConversationState) -> None:
    """u3-5: antes de decidir qué preguntar, fuera las correcciones que ya coinciden con lo guardado.
    Lo propuesto puede haberse aplicado en el MISMO turno por otro camino (el acompañante resuelto:
    "2 buceo" -> "1 buceo, 1 snorkel") y la pregunta salía "X -> X" (replay del 27-sep)."""
    if not state.pending_correction:
        return
    known = _known_field_values(state)
    lang = state.language or "es"
    still = {f: v for f, v in state.pending_correction.items() if not _same_for_customer(f, v, known.get(f), lang)}
    if len(still) != len(state.pending_correction):
        logger.info(f"[CORE] correcciones ya aplicadas en este turno: {sorted(set(state.pending_correction) - set(still))}")
    state.pending_correction = still or None


def _derive_kids_counts(state: ConversationState) -> None:
    """Traducir edades explícitas a los contadores que el split por edad del
    checkout ya entiende (<8 → snorkel desde los 6; 8-10 → Bubble Makers;
    10+ cuenta normal) — misma regla de negocio que el árbol (eligibility)."""
    ages = state.detected_ages or []
    minors = [a for a in ages if a < 18]
    if not minors:
        return
    state.kids_under_8_count = len([a for a in minors if a < 8])
    state.kids_eight_to_ten_count = len([a for a in minors if 8 <= a <= 10])
    state.detected_ages = ages


def _build_cart_from_slots(state: ConversationState) -> None:
    _derive_kids_counts(state)
    alloc = state.detected_group_allocation or {}
    # Todo lo que el carrito sabe cobrar, no solo los productos de un día: un
    # acompañante puede elegir el Open Water o ir sin actividad.
    cartable = set(dom.cart_activity_ids())
    product_alloc = {k: v for k, v in alloc.items() if k in cartable and v}
    if product_alloc:
        # Grupo mixto: un ítem por subgrupo ("3 certificados y 2 snorkel").
        # Las claves ya vienen resueltas por el detector (los no certificados
        # ya son minicourse), así que NO se re-aplica _effective_activity.
        state.mixed_cart = [
            _cart_item(state, activity, qty) for activity, qty in product_alloc.items()
        ]
    else:
        qty = state.detected_group_size or 1
        state.mixed_cart = [_cart_item(state, _effective_activity(state), qty)]
    if state.is_colombian:
        state.mixed_display_currency = "COP"
        state.mixed_final_is_colombian = True
    elif state.mixed_final_is_colombian:
        # Nacionalidad corregida despues de cerrar en COP (tarea 7b).
        state.mixed_display_currency = "USD"
        state.mixed_final_is_colombian = None


def _refresher_note(state: ConversationState) -> str:
    """Nota del refresher en el cierre. Se cobra (owner 2026-09-14): precio por
    persona desde el catalogo y, fuera del gating colombiano, su link de reserva.
    No se inventa cuantos lo necesitan: la pregunta de seguridad es de grupo."""
    if not state.refresher_interested:
        return ""
    price = cart_render.refresher_price_text(state, una_moneda=settings.rag_sin_precio_con_tarjeta)  # G3-07a
    url = None if state.is_colombian else cart_render.refresher_booking_url(state)
    if state.language == "es":
        how = f" Resérvalo aquí: {url}" if url else " El asesor te lo confirma junto con el pago."
        return (
            "✅ *Refresher añadido* — el guía hace el repaso en el agua antes de la "
            f"inmersión. Tiene un costo de *{price}* por persona que lo necesite.{how}\n\n"
        )
    how = f" Book it here: {url}" if url else " The advisor will confirm it with the payment."
    return (
        "✅ *Refresher added* — the guide runs the in-water review before the dive. "
        f"It costs *{price}* per person who needs it.{how}\n\n"
    )


def _finalize(state: ConversationState) -> str:
    """Todos los slots listos → resumen por actividad + links (determinista,
    del catálogo), con gating colombiano: colombiano → asesor coordina el pago
    en COP (100% online o 50/50), sin link directo."""
    from src.agents.lead_summary import build_lead_summary

    lang = state.language
    state.core_pending_slot = None
    # Siempre desde el estado (tarea 7b, 2026-09-15): con el carrito congelado tras
    # el primer cierre, "espera, en realidad no somos colombianos" re-emitia el mismo
    # resumen en COP. Las altas post-cierre ya estan en el reparto, asi que no se pierden.
    _build_cart_from_slots(state)

    refresher_note = _refresher_note(state)

    if state.is_colombian:
        # Gating colombiano: SIN link de reserva directa — el asesor coordina el
        # pago en COP (100% online o 50/50). Resumen determinista del catálogo.
        state.step = Step.ESCALATE
        state.quick_replies = []
        reason = "núcleo conversacional - cliente colombiano, pago en COP con asesor"
        state.pending_escalation_reason = reason
        summary = _colombian_summary_lines(state)
        state.mixed_last_summary = summary
        state.pending_note = build_lead_summary(state, escalation_reason=reason)
        if lang == "es":
            return (
                f"{refresher_note}{summary}\n\n"
                + de_cartagena("Como son colombianos/residentes", "Como sois colombianos/residentes")
                + ", el pago es en pesos (COP): puedes "
                "pagar *100% online* o *50% online + 50% en persona*. Te paso con un "
                "asesor para confirmar disponibilidad y coordinar el pago — enseguida "
                "se pone en contacto contigo. 🌊"
            )
        return (
            f"{refresher_note}{summary}\n\n"
            "As Colombian residents you pay in COP: *100% online* or *50% online + "
            "50% in person*. I'll connect you with an advisor to confirm availability "
            "and arrange payment — they'll be in touch shortly. 🌊"
        )

    response = cart_render.goto_final_summary(state)
    return refresher_note + response


def _colombian_summary_lines(state: ConversationState) -> str:
    """Resumen por actividad para clientes colombianos: label + cantidad +
    precio en COP del catálogo, sin URLs de reserva directa."""
    lang = state.language
    lines: list[str] = []
    for b in cart_render.cart_booking_blocks(state):
        qty = b["qty"]
        lines.append(f"🤿 *{b['label']}*")
        cop = b.get("cop")
        if cop:
            if qty > 1:
                lines.append(f"💰 {qty} × {money.cop(cop)} p.p. = *{money.cop(cop, qty)}*")
            else:
                lines.append(f"💰 *{money.cop(cop)}*" + (" por persona" if lang == "es" else " per person"))
        if b.get("note"):
            lines.append(b["note"])
        lines.append("")
    return "\n".join(lines).strip()


# u3-1 paso 3 (24-sep): el acuse cálido en PARALELO. Medido en la ronda A2: en el 48 % de
# los turnos iban en serie extracción (p50 0,85 s) -> acuse (p50 1,0 s), y el acuse no
# necesita esperar: recibe el mensaje (que ya trae lo que el cliente acaba de decir) y un
# resumen de la reserva. EXCEPCIÓN: si la pregunta pendiente es una de sí/no de
# `_JUST_ANSWERED_PHRASE`, el resumen necesita el valor RECIÉN extraído (antes de extraer,
# un "sí" a "¿eres colombiano?" se leería como el valor viejo) -> ahí sigue en serie, como hoy.
def _maybe_launch_ack(state: ConversationState, message: str) -> None:
    pending = state.core_pending_slot
    if pending in _JUST_ANSWERED_PHRASE:
        return
    # La foto se toma AQUÍ, antes de lanzar la tarea (lección de la carrera de l1-4).
    snapshot = {
        "summary": _booking_context_summary(state, just_answered_slot=pending),
        "client_name": state.client_name,
        "lang": state.language,
    }
    state._pending_ack = {
        "prev_pending": pending,
        "task": asyncio.create_task(compose_acknowledgement(
            message, state_summary=snapshot["summary"], client_name=snapshot["client_name"], lang=snapshot["lang"],
        )),
    }


async def _take_parallel_ack(state: ConversationState, prev_pending) -> str | None:
    """El acuse lanzado en `_setup_phase`, si sirve para este cierre; `None` = calcularlo
    en serie como siempre (no había, o la pregunta pendiente cambió por el camino)."""
    pending = getattr(state, "_pending_ack", None)
    state._pending_ack = None
    if not pending:
        return None
    task = pending["task"]
    if pending["prev_pending"] != prev_pending:
        task.cancel()
        return None
    try:
        return await task
    except Exception as exc:  # noqa: BLE001 — un acuse nunca tumba el turno
        logger.warning(f"[CORE][ACK][PARALELO] falló, sin acuse: {exc}")
        return ""


def cancel_pending_ack(state: ConversationState) -> None:
    """Red de seguridad al cerrar el turno: un acuse lanzado que nadie usó se cancela."""
    pending = getattr(state, "_pending_ack", None)
    state._pending_ack = None
    if pending and not pending["task"].done():
        pending["task"].cancel()


async def _slotfill_close_phase(
    state: ConversationState, message: str, greeting: str, first_turn: bool, carry: dict,
) -> str:
    """Fase 3.3e — RESOLVER + RESPONDER: elige el siguiente slot que falta
    (`next_missing_slot`) y lo pregunta (`ask_slot`), o cierra la reserva
    (`_finalize` + nota de lead), y envuelve la respuesta con el acuse cálido
    (`compose_acknowledgement`). Extraído de `_extract_close_phase`; corre cuando
    la extracción no resolvió el turno. Lo llama la cascada (vía
    `maybe_handle_turn`) y el nodo `slotfill_close` del subgrafo."""
    from src.agents import supervisor  # lazy

    resolved_short = carry["resolved_short"]
    prev_pending = carry["prev_pending"]
    finalized = False
    cierre_previo = None

    # El reparto sigue a un cambio de la actividad principal cuando solo tenia la
    # anterior (tarea 7b, 2026-09-15): "mejor snorkel" con {certified_diving: 2}
    # cerraba cobrando 2 inmersiones. Va aqui, con el turno ya decidido, y no al
    # escribir la actividad: si el turno hablaba de otra persona, la red de
    # precision ya ha restaurado la principal y no hay cambio que seguir.
    prev_main_activity = carry["prev_main_activity"]
    alloc = state.detected_group_allocation or {}
    if (
        prev_main_activity and state.detected_activity
        and state.detected_activity != prev_main_activity and set(alloc) == {prev_main_activity}
    ):
        state.detected_group_allocation = {state.detected_activity: alloc[prev_main_activity]}
        logger.info(f"[CORE] reparto sigue a la actividad principal -> {state.detected_group_allocation}")

    # Circuit-breaker (portado 2026-09-01, hallazgo en vivo, batería de
    # grupos mixtos contra PRE, lote 8): repetido aquí (además de en
    # `_understand()`, `next_missing_slot`) porque un turno resuelto por
    # respuesta corta (`resolved_short=True`, p. ej. "no" a la pregunta de
    # seguridad) puede saltarse la extracción completa y llegar aquí sin
    # pasar por ese chequeo — este es el punto que de verdad CONSUME
    # `pending_companion_queue`/`pending_companion_activity`
    # (líneas de abajo), así que es donde tiene que estar la última barrera
    # antes de preguntar por un acompañante que ya no existe (el reparto ya
    # cubre a todo el grupo).
    if _group_allocation_fully_resolved(state):
        state.needs_companion_activity = False
        state.companion_activity_deferred = False
        state.pending_companion_activity = None
        state.pending_companion_queue = []
        state.pending_split_total = None
        state.pending_undecided_qty = None

    # RESOLVER + RESPONDER.
    #
    # Bug en vivo 2026-07-23 (matriz EN de multi-ítem): si este turno NO
    # resolvió la pregunta de cantidad de un acompañante pendiente (p. ej.
    # el mensaje mencionaba OTRA actividad distinta a la preguntada — guarda
    # nueva en `_apply_short_answer`/SLOT_COMPANION_QTY — y cayó de largo
    # hasta aquí), `next_missing_slot()` NO conoce en absoluto
    # `pending_companion_activity`/`pending_companion_queue`: sin este
    # chequeo, `core_pending_slot` se sobreescribía con el siguiente slot
    # "normal" (ubicación, seguridad...) dejando la pregunta de acompañante
    # huérfana — el estado seguía "pensando" que faltaba responderla pero
    # nada volvía a preguntarla nunca. Se prioriza sobre next_missing_slot
    # igual que el resto de comprobaciones de este bloque multi-ítem.
    _merge_pending_undecided(state)
    _prune_applied_corrections(state)
    if state.pending_companion_activity:
        response = ask_slot(state, SLOT_COMPANION_QTY, reasking=True)
        state.step = Step.FREE_TEXT
    elif state.pending_companion_queue:
        state.pending_companion_activity = state.pending_companion_queue.pop(0)
        response = ask_slot(state, SLOT_COMPANION_QTY)
        state.step = Step.FREE_TEXT
    elif prev_pending == SLOT_COMPANION_ACTIVITY and not resolved_short:
        # La actividad del acompañante seguía pendiente y este turno no la
        # resolvió (deferral "lo que sea mejor" que el LLM no fija): re-preguntar
        # en vez de caer al resumen y PERDER al acompañante (hallazgo en vivo
        # 2026-07-24). `next_missing_slot` no rastrea este slot, de ahí el guard
        # explícito antes de dejar que sobrescriba `core_pending_slot`.
        #
        # Auditoría 2026-08-26 (batería sintética contra PRE, portado de
        # pre_gadea v0.21.1): re-preguntar INCONDICIONALMENTE aquí entraba
        # en BUCLE — seguía repitiendo la MISMA pregunta para siempre,
        # incluso cuando había otras preguntas obligatorias (seguridad,
        # nacionalidad) todavía sin responder por detrás, enterradas sin
        # posibilidad de llegar a plantearse nunca. Ahora se distingue: si
        # el resto de la reserva YA está completa, repreguntar aquí mismo
        # (si no, se pierde el acompañante al cerrar); si todavía falta
        # algo más, se deja avanzar a por ello primero y se marca
        # `companion_activity_deferred` (NO `needs_companion_activity` —
        # ese otro flag es para la detección FRESCA del turno actual, se
        # consume de inmediato justo tras `_understand()`, y usarlo aquí
        # también haría que ese chequeo temprano interceptara el turno
        # SIGUIENTE antes de procesar la respuesta a la pregunta realmente
        # pendiente) para retomar el acompañante justo antes de cerrar.
        nxt_now = next_missing_slot(state)
        if nxt_now is None:
            response = ask_slot(state, SLOT_COMPANION_ACTIVITY, reasking=True)
            state.step = Step.FREE_TEXT
        else:
            state.companion_activity_deferred = True
            response = ask_slot(state, nxt_now, reasking=(nxt_now == prev_pending))
            state.step = Step.FREE_TEXT
    else:
        nxt = next_missing_slot(state)
        if _tarjeta_sin_seguridad(state, nxt, prev_pending):
            # CAL-F pareja-certificados-cop-descuento-almuerzo (decisión de Gadea, 18-oct): solo falta la seguridad y el
            # cliente no la contestó; la tarjeta sale igualmente, con la pregunta una vez dentro (ver la función).
            finalized = True
            cierre_previo = state.mixed_last_summary
            response = _finalize(state) + _nota_seguridad(state)
            state.core_pending_slot = SLOT_SAFETY  # su respuesta, si llega, se recoge como siempre
            supervisor._maybe_build_pending_note(state)
        elif nxt is None:
            if state.companion_activity_deferred:
                # Ya se cerró el hueco que interrumpió la pregunta del
                # acompañante (seguridad/nacionalidad/etc.) — se retoma
                # ahora, antes de cerrar, en vez de darla por perdida.
                state.companion_activity_deferred = False
                response = ask_slot(state, SLOT_COMPANION_ACTIVITY, reasking=True)
                state.step = Step.FREE_TEXT
            else:
                finalized = True
                cierre_previo = state.mixed_last_summary
                response = _finalize(state)
                # Materializar la nota de lead (el cierre no-colombiano deja solo
                # pending_lead_note_reason; en el camino legacy la construye
                # _finalize_tree_response — aquí el equivalente).
                supervisor._maybe_build_pending_note(state)
        else:
            nxt = _siguiente_pregunta(state, prev_pending)
            response = ask_slot(state, nxt, reasking=(nxt == prev_pending))
            state.step = Step.FREE_TEXT

    # Envoltorio cálido (Parte 2 del plan): en los turnos posteriores al saludo,
    # reconocer con calidez lo que el cliente acaba de decir ANTES de encadenar la
    # pregunta/dato (el "responde-y-encadena" que se había perdido). Los datos DUROS
    # (precio/links/plan/seguridad/resumen) ya están en `response` y NO pasan por el
    # LLM; el acuse solo pone el envoltorio. Si falla o se salta las reglas -> "".
    # u3-4: "contesta y sigue". La respuesta a la pregunta va primero y ocupa el sitio del
    # acuse (un "¡genial!" delante de una respuesta sobra). Se omite la pregunta de la
    # reserva solo en el caso que ya cubría `_answer_question`: la respuesta ya invita a
    # elegir actividad y lo siguiente sería el menú entero (fallo en vivo 2026-07-24).
    if settings.rag_origen_pregunta and state.pregunta_precio_pendiente and (state.location or state.detected_location):
        # 7-oct (opción C del punto 3): el cliente ya dijo desde dónde sale; se contesta la pregunta del precio que
        # quedó pendiente (si este mensaje no trae otra pregunta, que manda). Se consume pase lo que pase.
        pendiente, state.pregunta_precio_pendiente = state.pregunta_precio_pendiente, None
        if not _has_pending_answer(state):
            logger.info("[CORE][ORIGEN] ya sabemos el origen: se contesta la pregunta del precio pendiente")
            state._pending_answer = asyncio.create_task(_rag_answer(state, pendiente, history=list(state.history)))
    answer = await _take_parallel_answer(state)
    if answer and _es_pregunta_de_origen(answer):
        # 7-oct: la pregunta del origen ocupa el turno (con sus botones); la de la reserva queda para después.
        cancel_pending_ack(state)
        _fijar_origen_antes_del_precio(state, message)
        response = greeting + answer
        state.history.append({"role": "assistant", "content": response})
        return response
    if (answer and finalized and settings.rag_sin_precio_con_tarjeta and _IMPORTE_RE.search(answer)
            and not (settings.cierre_sin_repetir and cierre_previo and state.mixed_last_summary == cierre_previo)):
        # G3-07a (18-oct, decisión de Gadea: una sola moneda por mensaje): el turno lleva la tarjeta del plan con su
        # precio, y la respuesta (adelantada, escrita antes de saber de dónde es el cliente) traía otro importe: "126
        # USD" en el texto y "2 × 448.000 COP" en la tarjeta (conv 5573). Se rehace sin precio; solo en este caso.
        logger.info("[CORE][G3-07a] la respuesta trae un importe y el turno lleva la tarjeta: se rehace sin precio")
        try:
            answer = await _rag_answer(state, message, history=list(state.history), sin_precio=True) or answer
        except Exception as exc:  # noqa: BLE001 — si falla, va la de antes
            logger.warning(f"[CORE][G3-07a] no se pudo rehacer sin precio: {exc!r}")
    if answer and finalized and _is_rag_fallback(answer):
        # s4-7 (paso 6): con el cierre de la reserva (resumen + link) en este turno, un "eso no lo
        # tengo a la mano" no aporta nada y, por la regla de arriba, TAPABA el cierre: "great, how do
        # i pay" se quedaba sin el link (ronda B de u3-5). El cierre ya contesta "¿cómo pago?".
        answer = None
    if answer:
        cancel_pending_ack(state)
        if _answer_replaces_the_booking_question(state, answer, finalized=finalized):
            state.quick_replies = []
            response = answer
        elif settings.cierre_sin_repetir and finalized and cierre_previo and state.mixed_last_summary == cierre_previo:
            # s4-26: la reserva ya estaba cerrada y no ha cambiado; la tarjeta (precio, link) ya la tiene el cliente.
            # Repetirla detrás de cada respuesta ("¿cuánto dura?") era el fallo de manual-duracion-curso.
            logger.info("[CORE][S4-26] cierre igual al ya enviado: va solo la respuesta")
            response = answer
        elif _answer_asks_the_origin(state, answer):
            response = answer  # la misma pregunta que la de la reserva: va una vez, con sus botones de origen
        else:
            response = f"{answer.rstrip()}\n\n{response}"
        response = greeting + response
        state.history.append({"role": "assistant", "content": response})
        return response

    ack = ""
    if not first_turn:
        # u3-1 paso 3: el acuse que se lanzó en paralelo en `_setup_phase`, si sirve.
        ack = await _take_parallel_ack(state, prev_pending)
        if ack is None:
            ack = await compose_acknowledgement(
                message,
                state_summary=_booking_context_summary(state, just_answered_slot=prev_pending),
                client_name=state.client_name,
                lang=state.language,
            )
        if ack:
            ack = ack.rstrip() + "\n\n"
    response = greeting + ack + response
    state.history.append({"role": "assistant", "content": response})
    return response
