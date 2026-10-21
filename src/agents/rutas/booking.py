"""Lo que el núcleo de la reserva (ruta `booking`, `conversational_core` y `src/agents/nucleo/`) toma del
supervisor, siempre como `supervisor.<nombre>`: aplicar la intención detectada (`_apply_detected_intent`), el veto
de campos ya resueltos y la coherencia del reparto, el grupo de nacionalidades mixtas, la nota pendiente para el
asesor, la fecha cerrada, el saludo solo y la pregunta de información.

s4-2 (19-oct): movido tal cual desde `supervisor.py`, que lo re-exporta. Ver `src/agents/rutas/__init__.py`.
"""

import logging
import re

from src.agents.intent_detector import DetectedIntent
from src.agents.lead_summary import build_lead_summary
from src.agents.supervisor import _booking_change_buttons
from src.config import settings
from src.domain import activities as dom
from src.flows import cart_render
from src.flows.state import ConversationState, Step
from src.utils.text import strip_accents as _strip_accents

logger = logging.getLogger("uvicorn.error")


# Los ÚNICOS 2 días cerrados del año (`policies.json["closed_days"]`): 25 de
# diciembre y 1 de enero, en cualquier forma de nombrarlos (fecha exacta,
# festividad, o "hoy/mañana" no aplica aquí — solo la fecha/festividad
# explícita, que es lo único que se puede resolver sin saber la fecha real
# de "hoy"). Usado para NO darle al cliente el canned de disponibilidad
# genérico ("siempre hay disponibilidad") en esos dos días concretos, que
# sería una respuesta falsa. (Portado de pre_gadea v0.21.10.)
_CLOSED_DATE_RE = re.compile(
    r"\b(25\s+de\s+diciembre|diciembre\s+25|december\s+25th?|dec\s+25th?|"
    r"navidad|christmas\s+day|"
    r"1\s+de\s+enero|enero\s+1|january\s+1st?|jan\s+1st?|"
    r"a[ñn]o\s+nuevo|new\s+year'?s?(?:\s+day)?)\b",
    re.IGNORECASE,
)


# Question starters used to recognize plain informational questions ("incluye
# comida?", "what's included?") inside the cart-style mixed flow. Real bug this
# guards against: the tool-calling orchestrator (an LLM) occasionally
# misclassified an info question as a cart action — e.g. "Incluye algún
# servicio de comida y bebida" got turned into add_to_cart(companion, 4),
# silently adding 4 bogus companions to the cart. Routing obvious questions
# straight to RAG, before the orchestrator ever sees them, removes that
# failure mode entirely instead of trying to prompt-engineer it away.
# El acento se quita antes de matchear (más abajo), así que "qué" y "que" son
# indistinguibles aquí. El lookahead evita el falso positivo del "que"
# CONJUNCIÓN/exhortativo ("que se anime", "que él venga", "que uno haga") —
# seguido de pronombre átono/sujeto NUNCA es interrogativo, mientras que "que
# incluye"/"que precio" sí. (Los marcadores están ya sin acento: "él"->"el".)
_QUE_CONJUNCION = r"(?!\s+(?:se|el|ella|ellos|ellas|uno|una|unos|unas)\b)"
_INFO_QUESTION_STARTER_PATTERN = re.compile(
    r"^("
    r"qu[ée]" + _QUE_CONJUNCION + r"|cu[áa]nto|cu[áa]ndo|c[óo]mo|d[óo]nde|cu[áa]l|"
    r"inclu[yi]e|tiene|tienen|hay|puedo\s+saber|"
    # Aperturas de BÚSQUEDA de info sin palabra-pregunta ni "?" (2026-07-24):
    # "cuéntame del precio", "me gustaría saber qué incluye", "dime cómo es".
    # Inequívocamente informativas (no acciones de carrito tipo "puedo añadir").
    r"cu[ée]ntame|d[ií]me|expl[ií]came|me\s+gustar[ií]a\s+saber|"
    r"quiero\s+saber|quisiera\s+saber|necesito\s+saber|"
    r"what|how|when|where|which|does|is\s+there|are\s+there|do\s+you|can\s+i\s+know|"
    r"tell\s+me|i'?d\s+like\s+to\s+know|i\s+want\s+to\s+know"
    r")\b"
)


# La pregunta no siempre abre el mensaje (2026-09-15): "primero dime qué incluye el
# tour", "vale, cuánto cuesta", "antes de nada, cuéntame del minicurso". Se reconoce
# por la ESTRUCTURA, con clases gramaticales cerradas y no frases:
#   - pedir informacion en imperativo, en cualquier posicion (inequivoco);
#   - palabra interrogativa al inicio de una clausula: tras puntuacion, con o sin
#     conjuncion ("perfecto, y como pago"), o tras una conjuncion sola ("ok y donde
#     nos recogen"). Ahi no valen "hay/tiene/incluye" ("somos 3, hay un nino" es un
#     dato), y "como/cuando/donde" solo con tilde: sin ella son relativos ("somos 3,
#     como te dije"). Tras una conjuncion sola, "que" solo con tilde ("quiero bucear y
#     que mi hijo haga snorkel" es un dato), y en ingles solo what/how/which ("and when
#     we arrive" es declarativa).
_INFO_REQUEST_ANYWHERE_RE = re.compile(
    r"\b(?:d[ií]me|cu[ée]ntame|expl[ií]came|inf[óo]rmame|"
    r"(?:quiero|quisiera|necesito|me\s+gustar[ií]a)\s+saber|"
    r"tell\s+me|let\s+me\s+know|i'?d\s+like\s+to\s+know|i\s+want\s+to\s+know)\b",
    re.IGNORECASE,
)
_CLAUSE_QUESTION_RE = re.compile(
    r"[,.;:!¡¿]\s*(?:(?:y|e|pero|o|u|and|but|or|so)\s+)?"
    r"(?:qu[ée]" + _QUE_CONJUNCION + r"|cu[áa]nt[oa]s?|cu[áa]l(?:es)?|cómo|dónde|cuándo"
    r"|what|how|which|where|when)\b"
    r"|\b(?:y|e|pero|and|but)\s+(?:qué|cu[áa]nt[oa]s?|cu[áa]l(?:es)?|cómo|dónde|cuándo|what|how|which)\b",
    re.IGNORECASE,
)


def _looks_like_info_question(message: str) -> bool:
    """True for plain informational questions ("incluye comida?", "what's
    included?"). Deliberately conservative: only starter words that signal
    "I'm asking for information" (qué/incluye/hay/what/does...), NOT polite
    request phrasing like "puedo añadir..." / "can you remove..." — those are
    real cart actions and must still reach the orchestrator. The question may
    also sit later in the message (`_INFO_REQUEST_ANYWHERE_RE`,
    `_CLAUSE_QUESTION_RE`).
    """
    lowered = message.strip().lower()
    normalized = _strip_accents(lowered)
    if not normalized:
        return False
    return bool(
        _INFO_QUESTION_STARTER_PATTERN.match(normalized)
        or _INFO_REQUEST_ANYWHERE_RE.search(lowered)
        or _CLAUSE_QUESTION_RE.search(lowered)
    )


def _mixed_nationality_response(state: ConversationState, message: str) -> str:
    """Copy + efecto de estado para grupos con nacionalidades mixtas (portado a
    `booking_agent.py`, 2026-08-27 — gap encontrado al verificar hallazgo P en
    vivo contra PRE: el router ya clasificaba estos mensajes como ROUTE_BOOKING,
    pero el subgrafo de booking nunca reproducía esta explicación, así que en
    el grafo caían al slot-fill normal sin decir nada del pago individual por
    nacionalidad). Extraído de `_shared_turn_handler` para que la cascada y el
    nodo `booking` usen una única fuente de copy/estado, mismo patrón que
    `_booking_change_response`.

    Hallazgo A (2026-09-15): lo dispara el nucleo cuando el LLM lee un grupo mixto
    (antes una lista de fraseos en la cascada, el nodo `booking` y el router), y el
    historial lo escribe quien llama."""
    # Decision del owner (2026-09-14): un grupo con nacionalidades mixtas paga
    # TODO en dolares (USD). Antes se explicaba un pago individual por nacionalidad.
    state.is_colombian = False
    if state.language == "es":
        response = (
            "¡Entendido! Cuando en el grupo hay nacionalidades mixtas, la reserva se paga en "
            "dólares (USD) para todo el grupo, al mismo precio equivalente — no hay descuento "
            "especial por ser colombiano.\n\n¿Quieres que te conecte con un asesor, o prefieres "
            "volver al menú principal?"
        )
    else:
        response = (
            "Got it! When the group has mixed nationalities, the booking is paid in US dollars "
            "(USD) for the whole group, at the same equivalent price — there's no special "
            "discount for being Colombian.\n\nWould you like me to connect you with an advisor, "
            "or would you rather go back to the main menu?"
        )
    state.quick_replies = _booking_change_buttons(state.language)
    logger.info("[SUPERVISOR] Mixed-nationality group detected -> honest explanation + escalate/home buttons")
    return response


GREETING_ONLY_KEYWORDS = {
    "hola", "hello", "hi", "buenas", "buenos dias", "buenos días",
    "buenas tardes", "buenas noches", "hey",
}

# Cortesías de small-talk que acompañan a un saludo ("hola buenas que tal?", "hi
# how are you") y NO son una pregunta de info real. Se comparan sin tildes (ver
# `conversational_core._is_greeting_only`, que compone saludo + cortesía).
GREETING_SMALLTALK_KEYWORDS = {
    "que tal", "que mas", "que hubo", "como estas", "como andas", "como va",
    "como te va", "todo bien", "how are you", "hows it going", "whats up",
    "what's up", "buenas buenas",
}


def _append_mixed_cart_item(state: ConversationState, item_type: str, plan: str | None, qty: int) -> None:
    if qty <= 0:
        return
    lang = getattr(state, "language", "es") or "es"
    existing = next(
        (item for item in state.mixed_cart if item.get("type") == item_type and item.get("plan") == plan),
        None,
    )
    if existing is not None:
        existing["qty"] += qty
        return
    state.mixed_cart.append({
        "type": item_type,
        "qty": qty,
        "plan": plan,
        "label": cart_render.cart_label_for(item_type, plan, lang),
    })


def _maybe_build_pending_note(state: ConversationState) -> None:
    """Build the lead note after a tree call, either via a real escalation or
    a silent note (e.g. a booking link was sent directly, no handoff needed)."""
    if state.step == Step.ESCALATE and not state.pending_note:
        reason = state.pending_escalation_reason or "derivado por el árbol de opciones"
        state.pending_escalation_reason = reason
        state.pending_note = build_lead_summary(state, escalation_reason=reason)
    elif state.pending_lead_note_reason and not state.pending_note:
        state.pending_note = build_lead_summary(state, escalation_reason=state.pending_lead_note_reason)
        state.pending_lead_note_reason = None


def _finalize_tree_response(state: ConversationState, message: str, response: str) -> str:
    """Persist a tool-driven turn in history and fill the lead note if we escalated."""
    state.history.append({"role": "user", "content": message})
    state.history.append({"role": "assistant", "content": response})
    _maybe_build_pending_note(state)
    return response


# Cap on state.remembered_facts["notes"] (Fase C) — keeps the most recent
# entries so the list doesn't grow unbounded over a very long conversation.
_MAX_REMEMBERED_NOTES = 8


# s4-1 (19-oct): fuera el cutover por dominio del extractor (`_maybe_apply_llm_extraction_cutover` y sus
# `_*_CUTOVER_FIELDS`) y la sonda en sombra de la Fase 0 (`_maybe_log_llm_extraction_shadow`, con su flag
# `llm_extraction_shadow_mode`): no los llamaba nadie desde que se retiró el orquestador antiguo (308488d, 28-jul).
# El relleno de huecos vivo es el de `conversational_core._understand` (`fill_gaps`).
def _log_safe_message(message: str, limit: int = 500) -> str:
    """Message text for [EXTRACT] log lines. Real bug found live (2026-07-21):
    truncating to 60 chars (as this used to) silently cut off the end of real
    customer messages, so candidates harvested by
    scripts/harvest_cutover_logs.py for the eval-set (Fase 6, bucle de datos
    reales) reproduced a DIFFERENT, truncated message — the opposite of what
    that tool needs. 500 chars comfortably covers real chat messages; only
    pathologically long ones get cut, and are marked with "…[truncated]" so
    it's never silently ambiguous.
    """
    if len(message) <= limit:
        return message
    return message[:limit] + "…[truncated]"


def _group_size_that_will_persist(
    intent: DetectedIntent, state: ConversationState | None, message: str | None
) -> int | None:
    """El total del grupo que quedara GUARDADO al terminar el turno.

    Unica fuente de la regla que ya aplicaba `_apply_detected_intent`: el total
    se escribe una sola vez, y el de un turno posterior solo lo sustituye si el
    turno lo acepta como correccion (`intent.overwrite`: cue explicito o confirmada
    por el cliente, ver `conversational_core._route_contradictions`).

    Existe porque la invariante del reparto razonaba con el total del TURNO, que es justo el que el regex lee mal: con 7 ya
    sabidos, "4 certificados" da group_size=4 en el turno (cifra de un tramo
    tomada por el total), un reparto {certified_diving: 4} "cuadraba" con ese 4
    y se guardaba junto a un estado que seguia en 7. Medido con LLM real en PRE
    (2026-09-14, docs/robustness/progress-log.md). Comparar contra lo que se
    guarda, y no contra lo que dijo el turno, cierra el caso para cualquier
    fraseo sin tocar un regex.
    """
    turn = getattr(intent, "group_size", None)
    turn = turn if isinstance(turn, int) and turn > 0 else None
    known = getattr(state, "detected_group_size", None) if state else None
    known = known if isinstance(known, int) and known > 0 else None
    if turn is None or known is None:
        return turn or known
    if turn != known and "group_size" in getattr(intent, "overwrite", ()):
        return turn
    return known


def enforce_group_allocation_consistency(
    regex_intent: DetectedIntent, state: ConversationState, message: str
) -> None:
    """Un reparto por actividad que NO suma el total conocido se descarta.

    Por que existe (bateria de conversacion, 2026-09-12): la comprobacion
    "el reparto debe sumar el total" solo la hacia el VETO, y el veto solo mira
    campos que resolvio el REGEX (`field in regex_intent.detected_fields`, y la
    lista se calcula ANTES de la llamada al LLM). Un reparto producido por
    `fill_gaps` quedaba, por construccion, sin revisar: "4 con titulo y 2
    snorkel" en un grupo de 6 se guardaba como {snorkel: 2}, dejando fuera a 4
    personas y mal-tarificando la reserva EN SILENCIO.

    Esto cierra el agujero por el otro lado: en vez de anadir otra comprobacion
    a cada productor de repartos (regex, fill_gaps, veto), se comprueba UNA vez
    sobre el resultado final, justo antes de aplicarlo al estado. Cualquier
    fuente futura queda cubierta sin tocar nada.

    Dos desenlaces segun por donde falle la cuenta, no uno:
      - el reparto suma MAS que el total -> se cree al reparto y se sube el
        total (mismo criterio que `_set_group_size_from_allocation`), porque el
        total tambien puede venir mal leido;
      - el reparto suma MENOS -> le falta gente y se descarta.

    Se DESCARTA en vez de intentar arreglarlo: a estas alturas del turno la
    peticion al LLM ya se hizo, y pedir otra por esto gastaria el recurso
    escaso (peticiones/dia) en un caso que el bot resuelve gratis preguntando.
    Un reparto ausente hace que el bot pregunte; un reparto incompleto se
    aplica tal cual y se lleva por delante el precio. Abstenerse es mejor.

    El total se busca primero en el turno y luego en la conversacion. Sin total
    conocido no hay invariante que comprobar y no se toca nada.
    """
    allocation = getattr(regex_intent, "group_allocation", None)
    if not allocation:
        return
    # El total contra el que se comprueba es el que QUEDARA GUARDADO, no el del
    # turno: ver `_group_size_that_will_persist` para el caso medido.
    total = _group_size_that_will_persist(regex_intent, state, message)
    if total is None:
        return  # sin total con que comparar
    try:
        suma = sum(allocation.values())
    except (AttributeError, TypeError):
        return
    if suma == total:
        return
    if suma > total:
        # El reparto AMPLIA el total: se cree al reparto y se sube el total.
        # Es el mismo criterio que ya aplica el regex en
        # `_set_group_size_from_allocation` ("nunca a la baja, pero puede
        # ampliar"), y hace falta aqui porque el total del turno tambien puede
        # venir equivocado: "3 certified and 3 snorkel" con el total leido como
        # 3 descartaba un reparto CORRECTO de 6 (medido en la bateria).
        logger.info(
            f"[EXTRACT][GROUP_ALLOCATION_AMPLIA_TOTAL] allocation={allocation!r} "
            f"suma={suma} total_previo={total} msg={_log_safe_message(message)!r}"
        )
        regex_intent.group_size = suma
        if "group_size" not in regex_intent.detected_fields:
            regex_intent.detected_fields.append("group_size")
        # Si la conversacion ya tenia un total, la escritura unica de
        # `_apply_detected_intent` lo conservaria y quedaria un reparto de 7
        # con un total de 6. Mismo criterio que `_merge_companion_activity`: el
        # reparto completo manda sobre el total.
        if state is not None and (state.detected_group_size or 0) < suma:
            state.detected_group_size = suma
        return
    # suma < total: al reparto le FALTA gente. Nunca se guarda asi -- el bot
    # pregunta, que sale gratis, en vez de tarificar de menos en silencio.
    principal = state.detected_activity if state is not None else None
    if (settings.reparto_parcial_con_lo_sabido and principal and not state.detected_group_allocation
            and principal in dom.cart_activity_ids()):
        # G3-01 (17-oct): sin reparto guardado, todo el grupo hace la actividad principal (así se tarifica). "el de 12
        # minicurso y el de 8 snorkel" en una familia de 4 cuyos padres ya eligieron la salida de 2 inmersiones dice
        # qué hacen DOS: los otros siguen con lo que tenían. Antes se descartaba y la actividad del turno pasaba a ser
        # la de todos (3 × minicurso + Bubble Makers, y pase a un asesor).
        completo = dict(allocation)
        completo[principal] = completo.get(principal, 0) + total - suma
        logger.info(
            f"[EXTRACT][GROUP_ALLOCATION_CON_LO_SABIDO] {allocation!r} + el resto ({total - suma}) en {principal} "
            f"-> {completo!r} msg={_log_safe_message(message)!r}"
        )
        regex_intent.group_allocation = completo
        return
    logger.info(
        f"[EXTRACT][GROUP_ALLOCATION_INCOMPLETO] descartado={allocation!r} "
        f"suma={suma} total={total} msg={_log_safe_message(message)!r}"
    )
    regex_intent.group_allocation = None
    if "group_allocation" in regex_intent.detected_fields:
        regex_intent.detected_fields.remove("group_allocation")


# Cue de CORRECCIÓN explícita de un dato ya fijado ("en realidad revisamos y
# somos 4", "perdón, en realidad somos 3", "me equivoqué, somos 2",
# "actually we're 4"/"sorry, we're actually 3") — a diferencia de
# `_GROUP_RECOMPOSE_RE` (código legacy nunca conectado, borrado 2026-09-15),
# esta NO exige que "en realidad" preceda INMEDIATAMENTE a "somos": tolera
# relleno intermedio ("revisamos y", "lo pensamos y", "checamos y") —
# hallazgo en vivo (batería sintética contra PRE, 2026-08-26, lote 4,
# portado de pre_gadea v0.21.11) de que el fraseo real de una corrección
# casi nunca es tan limpio. Deliberadamente estrecho (exige el cue léxico
# explícito) para no convertir `detected_group_size` en escribible en
# cualquier mensaje — un número suelto sin este cue nunca lo sobreescribe.
_CORRECTION_CUE_RE = re.compile(
    r"\b(?:en\s+realidad|realmente|perd[oó]n|me\s+equivoqu[eé]|corrijo|"
    r"en\s+verdad|actually|sorry|my\s+mistake|i\s+made\s+a\s+mistake)\b",
    re.IGNORECASE,
)


def _principal_sigue_en_el_reparto(intent, state: ConversationState) -> bool:
    """G3-01 (flag `actividad_principal_en_el_reparto`, 17-oct): "el de 12 minicurso y el de 8 snorkel" en una familia
    cuyos padres ya eligieron la salida de 2 inmersiones da el reparto {certified_diving: 2, minicourse: 1, snorkel: 1}
    y la actividad "minicourse". La regla de "la última actividad gana" ponía el minicurso como principal; luego "mi
    esposo bucea conmigo" movía a uno del minicurso a las inmersiones ({certified_diving: 3, snorkel: 1}). Si la
    actividad principal sigue en el reparto con gente, la nueva es la de otra parte del grupo: no la sustituye."""
    if not settings.actividad_principal_en_el_reparto:
        return False
    principal, reparto = state.detected_activity, getattr(intent, "group_allocation", None)
    return bool(
        principal and intent.activity and intent.activity != principal and isinstance(reparto, dict)
        and (reparto.get(principal) or 0) > 0 and intent.activity in reparto
    )


def _apply_detected_intent(intent, state: ConversationState, message: str | None = None) -> None:
    if intent.language and not state.detected_language:
        state.detected_language = intent.language
        state.language = intent.language
        logger.info(f"[INTENT] Detected language: {intent.language}")

    # Latest concrete activity wins: the customer may change their mind mid-chat
    # ("quiero bucear" ... "mejor un minicurso para mi hijo"). Before, the FIRST
    # activity stuck forever (write-once), so after talking about Bubble Makers /
    # a minicurso, clicking "🤿 Reservar" still routed them into the CERTIFIED
    # diving flow. Now a newly-detected activity replaces the stale one.
    if _principal_sigue_en_el_reparto(intent, state):
        logger.info(f"[INTENT][G3-01] la actividad principal {state.detected_activity} sigue en el reparto "
                    f"{intent.group_allocation}: {intent.activity} es de otra parte del grupo")
    elif intent.activity and intent.activity != state.detected_activity:
        state.detected_activity = intent.activity
        # El servicio SIEMPRE sale del registro de actividades, aqui, en el unico
        # punto que guarda la actividad (F4 de docs/robustness/activity-domain-plan.md).
        # Los detectores (regex, relleno LLM, veto) solo deciden la actividad: antes
        # cada uno ponia su propio service_id, el relleno LLM no ponia ninguno (curso
        # sin precio ni link) y el regex usaba nombres inexistentes ("nitrox" en vez
        # de "nitrox_specialty"). Genericas (padi_course) -> None hasta decidir nivel.
        state.detected_service_id = dom.base_service_id(intent.activity)
        # A beginner activity (minicurso/snorkel) also carries a certification
        # signal — refresh it so the (possibly stale) certified flag doesn't
        # send a beginner request down the certified path.
        if intent.is_certified is not None:
            state.detected_is_certified = intent.is_certified
            state.is_certified = intent.is_certified
        logger.info(f"[INTENT] Activity updated to: {intent.activity} (service: {intent.service_id})")
    elif intent.is_certified is not None and (
        state.detected_is_certified is None or "is_certified" in intent.overwrite
    ):
        state.detected_is_certified = intent.is_certified
        state.is_certified = intent.is_certified
        logger.info(f"[INTENT] Detected certification: {intent.is_certified}")

    # Curso/especialidad generico que el estado ya permite concretar (regla del
    # owner 2026-09-14: quien no tiene certificacion va a su `default_level`, p. ej.
    # un "curso PADI" -> Open Water). Si no, el nucleo pregunta cual (F4).
    generic = dom.by_id(state.detected_activity) if state.detected_activity else None
    if generic and generic.generic and generic.default_level and state.is_certified is False:
        state.detected_activity = generic.default_level
        state.detected_service_id = dom.base_service_id(generic.default_level)
        logger.info(f"[INTENT] Generic {generic.id} resolved to {generic.default_level} (not certified)")

    # La regla (una sola escritura, salvo correccion explicita) vive en
    # `_group_size_that_will_persist`: la invariante del reparto la usa ANTES de
    # llegar aqui, y las dos tienen que ver el mismo total.
    persisted_group_size = _group_size_that_will_persist(intent, state, message)
    if persisted_group_size and not state.detected_group_size:
        state.detected_group_size = persisted_group_size
        logger.info(f"[INTENT] Detected group size: {persisted_group_size}")
    elif persisted_group_size and persisted_group_size != state.detected_group_size:
        logger.info(
            f"[INTENT] Group size CORRECTED: {state.detected_group_size} -> {persisted_group_size}"
        )
        state.detected_group_size = persisted_group_size

    if getattr(intent, "solo_confirmed", False):
        state.solo_traveler_confirmed = True

    # Estos campos se escriben una vez; un turno solo los sobrescribe con una correccion
    # aceptada (`intent.overwrite`, tarea 7b).
    if intent.group_allocation and (
        not state.detected_group_allocation or "group_allocation" in intent.overwrite
    ):
        state.detected_group_allocation = intent.group_allocation
        logger.info(f"[INTENT] Detected group allocation: {intent.group_allocation}")

    if intent.ages:
        merged = sorted(set((state.detected_ages or []) + list(intent.ages)))
        if merged != (state.detected_ages or []):
            state.detected_ages = merged
            logger.info(f"[INTENT] Detected ages: {merged}")

    if intent.last_dive_over_2_years is not None and (
        state.detected_last_dive_over_2_years is None or "last_dive_over_2_years" in intent.overwrite
    ):
        state.detected_last_dive_over_2_years = intent.last_dive_over_2_years
        state.last_dive_over_2_years = intent.last_dive_over_2_years
        logger.info(f"[INTENT] Detected last dive: {intent.last_dive_over_2_years}")

    if getattr(intent, "is_colombian", None) is not None and (
        state.is_colombian is None or "is_colombian" in intent.overwrite
    ):
        # Set only is_colombian; the checkout's _goto_mixed_final_colombian inherits
        # it (and sets mixed_final_is_colombian + currency) so its skip stays intact.
        state.is_colombian = intent.is_colombian
        logger.info(f"[INTENT] Detected nationality is_colombian={intent.is_colombian}")

    # ex-9b paso 6 (`duracion_por_extractor`): la duración del extractor cambia la guardada (`overwrite`): lo que el
    # cliente dice ahora de sus días de buceo manda (decisión de Gadea, 19-oct). Sin el flag, una sola escritura.
    if intent.duration and (not state.detected_duration or "duration" in intent.overwrite):
        state.detected_duration = intent.duration
        logger.info(f"[INTENT] Detected duration: {intent.duration}")
    if getattr(intent, "_duracion_de_buceo", False):
        state.duracion_de_buceo = True

    if getattr(intent, "cert_dives", None) and not state.detected_cert_dives:
        state.detected_cert_dives = intent.cert_dives
        logger.info(f"[INTENT] Detected cert dive count: {intent.cert_dives}")

    if getattr(intent, "cert_days", None) and not state.detected_cert_days:
        state.detected_cert_days = intent.cert_days
        logger.info(f"[INTENT] Detected cert day count: {intent.cert_days}")

    if intent.location and (not state.detected_location or "location" in intent.overwrite):
        state.detected_location = intent.location
        state.location = intent.location
        logger.info(f"[INTENT] Detected location: {intent.location}")

    if intent.island and not state.detected_island:
        state.detected_island = intent.island
        state.island = intent.island
        logger.info(f"[INTENT] Detected island: {intent.island}")

    if intent.hotel and not state.detected_hotel:
        state.detected_hotel = intent.hotel
        state.hotel = intent.hotel
        logger.info(f"[INTENT] Detected hotel: {intent.hotel}")


_INTENT_TRIGGER_STEPS = {
    Step.WELCOME,
    Step.LANGUAGE,
    Step.MAIN_MENU,
}


def _should_skip_to_certified_flow(intent, state: ConversationState) -> bool:
    return (
        intent.activity == "certified_diving"
        and intent.is_certified is True
        and state.step in _INTENT_TRIGGER_STEPS
    )
