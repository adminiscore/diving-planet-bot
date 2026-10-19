"""Lo que el núcleo de la reserva (ruta `booking`, `conversational_core` y `src/agents/nucleo/`) toma del
supervisor, siempre como `supervisor.<nombre>`: aplicar la intención detectada (`_apply_detected_intent`), el veto
de campos ya resueltos y la coherencia del reparto, el grupo de nacionalidades mixtas, la nota pendiente para el
asesor, la fecha cerrada, el saludo solo y la pregunta de información.

s4-2 (19-oct): movido tal cual desde `supervisor.py`, que lo re-exporta. Ver `src/agents/rutas/__init__.py`.
"""

import logging
import re

from src.agents.intent_detector import (
    DetectedIntent,
    matched_activity_categories,
    nationality_is_ambiguous,
)
from src.agents.lead_summary import build_lead_summary
from src.agents.llm_extractor import verify_fields
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


# Mapeo activity(enum del LLM) -> service_id del catalogo: el servicio base de
# cada actividad en el registro (F3a de docs/robustness/activity-domain-plan.md;
# antes una tabla a mano con los mismos valores). padi_course/padi_specialty se
# quedan sin service_id (igual que el regex): sin nivel concreto nombrado no hay
# un unico item de catalogo que elegir.
_ACTIVITY_TO_SERVICE_ID = {
    activity_id: service_id
    for activity_id in dom.activity_ids()
    if (service_id := dom.base_service_id(activity_id)) and not dom.by_id(activity_id).sold_as
}


def _apply_activity_veto(regex_intent: DetectedIntent, llm_activity: str) -> None:
    """Side-effect especifico de `activity`: ademas del valor, fija el
    `service_id` correspondiente (mismo mapeo que _detect_activity aplica
    inline). Es la unica pieza de logica que no generaliza al resto de los
    campos verificados -- de ahi que viva como `apply` custom en
    `_VETO_FIELD_SPECS` en vez de en el orquestador generico."""
    regex_intent.service_id = _ACTIVITY_TO_SERVICE_ID.get(llm_activity)


def _activity_should_verify(
    message: str, regex_intent: DetectedIntent, state: ConversationState | None = None
) -> bool:
    """Trigger de `activity`: SOLO cuando el mensaje dispara 2+ categorias a
    la vez (mismo criterio que el `_maybe_veto_activity_via_llm` original de
    Fase 9). Medido en vivo con el eval-set (2026-09-10, ver docs/robustness/
    progress-log.md Fase 11): ampliar esto a "resuelto este turno" (sin exigir
    ambiguedad) llama al LLM en TODO turno donde se resuelve `activity` --
    incluidos los casos claros, sin ambiguedad real -- y el sesgo propio del
    LLM hacia 'minicourse' en mensajes escuetos ("Hola quiero bucear")
    sobreescribia el default correcto del regex, hundiendo el agreement de
    89%->73%. La ambiguedad real (2+ categorias) sigue siendo la señal
    correcta de "aqui SI hay riesgo real de colision" -- el gap de la
    conversacion 913 se cerro por otra via (ver `_PADI_COURSE_PATTERNS` en
    intent_detector.py, patron nuevo para "primer nivel"/"primer curso"),
    no ampliando este trigger.

    Segunda condicion: la actividad del regex tiene "hermanas" en el registro
    (misma familia y nivel: Open Water y su curso referido, 474 USD frente a 693).
    El regex se queda con la suya si el LLM falla o no discrepa. Un primer intento
    (2026-09-14) con una glosa que nombraba `padi_open_water` bajo el eval-set 214
    -> 213; esta version usa una glosa que solo describe al referido."""
    if len(matched_activity_categories(message)) >= 2:
        return True
    return bool(dom.sibling_ids(getattr(regex_intent, "activity", None)))


def _nationality_should_verify(
    message: str, regex_intent: DetectedIntent, state: ConversationState | None = None
) -> bool:
    """Trigger de `is_colombian`: SOLO cuando el mensaje trae polaridad de
    nacionalidad contradictoria (`intent_detector.nationality_is_ambiguous`).

    Mismo razonamiento que `_activity_should_verify`: con el trigger generico el
    LLM opinaba tambien en los casos claros y su sesgo pisaba al regex -- aqui,
    en las negaciones compactas ("ninguno colombiano" -> True, eval-set; ver
    test_field_veto_generic_trigger_risk.py). Es la condicion que el propio test
    de riesgo exigia antes de plantearse encender el flag; encenderlo sigue
    siendo una decision aparte, con medida."""
    return nationality_is_ambiguous(message)


def _certification_should_verify(
    message: str, regex_intent: DetectedIntent, state: ConversationState | None = None
) -> bool:
    """Trigger de `is_certified`: SOLO con polaridad de certificacion
    contradictoria (`intent_detector.certification_is_ambiguous`), misma regla
    comun que la nacionalidad. Sustituye al trigger generico que el test de
    riesgo marcaba como peligroso. Encender el flag sigue siendo una decision
    aparte, con medida."""
    from src.agents.intent_detector import certification_is_ambiguous
    return certification_is_ambiguous(message)


def _group_size_that_will_persist(
    intent: DetectedIntent, state: ConversationState | None, message: str | None
) -> int | None:
    """El total del grupo que quedara GUARDADO al terminar el turno.

    Unica fuente de la regla que ya aplicaba `_apply_detected_intent`: el total
    se escribe una sola vez, y el de un turno posterior solo lo sustituye si el
    turno lo acepta como correccion (`intent.overwrite`: cue explicito o confirmada
    por el cliente, ver `conversational_core._route_contradictions`).

    Existe porque la invariante del reparto y el trigger de su veto razonaban
    con el total del TURNO, que es justo el que el regex lee mal: con 7 ya
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


def _group_allocation_should_verify(
    message: str, regex_intent: DetectedIntent, state: ConversationState | None = None
) -> bool:
    """Trigger propio de `group_allocation`: solo si el reparto NO suma el
    `group_size` conocido.

    El fallo que motiva el veto es un reparto INCOMPLETO pero VISIBLE --
    "somos 5: 3 certificados, 1 minicurso y 1 snorkel" da group_size=5 y
    allocation={minicourse:1, snorkel:1}, porque "N certificados" sin verbo
    no matchea `activity_kw`. Esa incoherencia (2 != 5) es comprobable con
    aritmetica, sin preguntarle a nadie, asi que se usa como disparador en
    vez del generico "resuelto este turno".

    No es un detalle de eficiencia sino de precision: el trigger generico ya
    se midio en `activity` (89%->73%, revertido) porque llamar al LLM tambien
    en los casos CLAROS mete su sesgo por encima de un regex que acertaba.
    Aqui, ademas, un reparto que ya cuadra no tiene nada que corregir.

    Sin `group_size` conocido -- ni en el turno ni en la conversacion -- no hay
    con que comparar: se abstiene (False).
    """
    allocation = getattr(regex_intent, "group_allocation", None)
    if not allocation:
        return False
    # El total puede venir de ESTE turno o de uno anterior. Mirar solo el turno
    # dejaba el veto mudo justo en el caso multi-turno ("somos 6" y, dos turnos
    # despues, "4 con titulo y 2 snorkel") -- medido en
    # scripts/battery_group_allocation_gate.py, 2026-09-12. Y cuando hay los dos,
    # cuenta el que se va a GUARDAR (ver `_group_size_that_will_persist`).
    group_size = _group_size_that_will_persist(regex_intent, state, message)
    if group_size is None:
        return False
    try:
        total = sum(allocation.values())
    except (AttributeError, TypeError):
        return False
    return total != group_size


class _VetoSpec:
    __slots__ = ("shadow_flag", "cutover_flag", "apply", "should_verify")

    def __init__(self, shadow_flag: str, cutover_flag: str, apply=None, should_verify=None):
        self.shadow_flag = shadow_flag
        self.cutover_flag = cutover_flag
        self.apply = apply
        # Por defecto: "el campo se resolvio ESTE turno" (field in
        # regex_intent.detected_fields). `activity` sobreescribe esto con un
        # trigger mas estricto (ambiguedad real) -- ver `_activity_should_
        # verify` y su comentario para el porque.
        self.should_verify = should_verify


# Mecanismo por-campo (docs/multi-agent-refactor-plan.md, hallazgo en vivo
# conversacion real "purple-sun-590" 2026-09-03 + conversacion real 913
# 2026-09-10): un LLM verifica INDEPENDIENTEMENTE un campo que el regex ya
# resolvio y lo corrige si discrepa. Nacio como `_maybe_veto_activity_via_llm`
# (solo `activity`, disparado unicamente cuando el mensaje se autodiagnostica
# ambiguo via `matched_activity_categories`) y se generalizo para no repetir,
# al nivel del propio fix, el mismo anti-patron de "logica duplicada que se
# desincroniza" que motivo la auditoria regex de hoy -- el usuario pidio
# explicitamente extender el mismo patron a `is_certified`/`is_colombian`/
# `location`.
#
# El trigger POR DEFECTO ("resuelto este turno") se intento ampliar tambien
# para `activity` (cerrar el gap de la conv. 913 sin depender de que el regex
# se autodiagnostique ambiguo), pero el eval-set demostro en vivo que eso
# regresiona la precision (89%->73%: el LLM llamado en CADA resolucion,
# incluidas las claras, introduce su propio sesgo por encima del default
# correcto del regex). `activity` mantiene su trigger original de ambiguedad
# (`_activity_should_verify`); el gap real de la conv. 913 se cerro con una
# entrada nueva en `_PADI_COURSE_PATTERNS` (intent_detector.py), no ampliando
# este trigger. Los otros 3 campos si usan el trigger generico "resuelto este
# turno" -- pero permanecen con AMBOS flags en False (paridad preventiva,
# sin evidencia de bug real ni de que su propio trigger generico sea seguro
# a esa escala todavia; el eval-set de hoy ya deja datos parciales, ver
# progress-log.md).
_VETO_FIELD_SPECS = {
    "activity": _VetoSpec(
        shadow_flag="llm_activity_veto_shadow_mode",
        cutover_flag="llm_activity_veto_cutover",
        apply=_apply_activity_veto,
        should_verify=_activity_should_verify,
    ),
    "is_certified": _VetoSpec(
        shadow_flag="llm_certification_veto_shadow_mode",
        cutover_flag="llm_certification_veto_cutover",
        should_verify=_certification_should_verify,
    ),
    "is_colombian": _VetoSpec(
        shadow_flag="llm_nationality_veto_shadow_mode",
        cutover_flag="llm_nationality_veto_cutover",
        should_verify=_nationality_should_verify,
    ),
    "location": _VetoSpec(
        shadow_flag="llm_location_veto_shadow_mode",
        cutover_flag="llm_location_veto_cutover",
    ),
    # Hallazgo en vivo (bateria sintetica, 2026-09-10): "mi pareja y nuestros
    # dos hijos" resuelve group_size=2 (subcuenta) via el patron `pareja`->2
    # -- el regex CONTESTA CON CONFIANZA y se equivoca, a diferencia de un
    # hueco (None) que ya cubriria fill_gaps. Un intento de arreglarlo por
    # regex rompio un caso real validado por el owner (ver comentario en
    # config.py); se deja en manos de este mecanismo en su lugar.
    "group_size": _VetoSpec(
        shadow_flag="llm_group_size_veto_shadow_mode",
        cutover_flag="llm_group_size_veto_cutover",
    ),
    # Reparto incompleto pero visible (ver config.py para la justificacion,
    # que NO es el 91% del eval-set). Unico campo del mecanismo que es un
    # DICT y no un escalar: `_clean_verified_value` ya limpia los nulls que
    # mete el schema estricto y la comparacion `!=` de `verify_fields`
    # funciona igual sobre dicts -- hay tests explicitos de eso porque el
    # resto del mecanismo se diseño pensando en escalares.
    "group_allocation": _VetoSpec(
        shadow_flag="llm_group_allocation_veto_shadow_mode",
        cutover_flag="llm_group_allocation_veto_cutover",
        should_verify=_group_allocation_should_verify,
    ),
}


def _eligible_veto_fields(
    message: str, regex_intent: DetectedIntent, state: ConversationState | None = None
) -> list[str]:
    """Campos de `_VETO_FIELD_SPECS` que toca verificar en este turno: con
    alguna de sus 2 banderas encendida, con valor resuelto, marcados como
    resueltos ESTE turno, y que pasen su `should_verify` propio si lo tienen."""
    eligible = []
    for field, spec in _VETO_FIELD_SPECS.items():
        if not (getattr(settings, spec.shadow_flag) or getattr(settings, spec.cutover_flag)):
            continue
        value = getattr(regex_intent, field, None)
        if value in (None, [], ""):
            continue  # nada resuelto que vetar (eso ya lo cubre el cutover de huecos)
        if field not in regex_intent.detected_fields:
            continue  # no se resolvio ESTE turno -- nada nuevo que verificar
        if spec.should_verify is not None and not spec.should_verify(
            message, regex_intent, state
        ):
            continue  # trigger especifico del campo (p. ej. ambiguedad de activity)
        eligible.append(field)
    return eligible


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

    El total se busca primero en el turno y luego en la conversacion, igual que
    `_group_allocation_should_verify`. Sin total conocido no hay invariante que
    comprobar y no se toca nada.
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


async def _maybe_veto_resolved_fields_via_llm(
    message: str, regex_intent: DetectedIntent, state: ConversationState,
    only_fields: list[str] | None = None,
) -> None:
    """Verifica en UNA SOLA peticion todos los campos que el regex resolvio
    este turno y que tengan el veto encendido. Ver el comentario de
    `_VETO_FIELD_SPECS` arriba para el diseño completo.

    Una peticion para N campos, no N peticiones (medido en vivo 2026-09-10):
    el recurso escaso de la cuenta son las peticiones/dia (limite RPD
    agotado con los tokens intactos), asi que agrupar es lo correcto contra
    el limite real -- y de paso deja una sola ida y vuelta de latencia.

    IMPORTANTE: la LLAMADA se hace si algun campo tiene cualquiera de sus 2
    banderas, pero la APLICACION es POR CAMPO segun SU PROPIA bandera de
    cutover -- un campo en shadow-mode nunca se aplica aunque otro campo del
    mismo lote si este en cutover. Cualquier fallo degrada a "regex-only" en
    silencio.
    """
    fields = _eligible_veto_fields(message, regex_intent, state)
    if only_fields is not None:
        fields = [f for f in fields if f in only_fields]
    if not fields:
        return  # cero coste: ni una peticion
    try:
        regex_values = {f: getattr(regex_intent, f, None) for f in fields}
        disagreements = await verify_fields(
            fields, message, regex_values, history=state.history, lang=state.language,
        )
        apply_veto_disagreements(disagreements, regex_intent, message, regex_values)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[EXTRACT][VETO] failed, degrading to regex-only (ignored): {exc}")


def _veto_would_generalize(regex_activity, llm_activity) -> bool:
    """True si el LLM solo propone la actividad GENERICA de la misma familia que la
    concreta que ya dio el regex. Derivado del registro (`generic`, `family`)."""
    concrete = dom.by_id(regex_activity) if isinstance(regex_activity, str) else None
    proposed = dom.by_id(llm_activity) if isinstance(llm_activity, str) else None
    return (
        concrete is not None and proposed is not None
        and not concrete.generic and proposed.generic
        and concrete.family == proposed.family
    )


def valid_veto_corrections(disagreements: dict, regex_values: dict, message: str = "") -> dict:
    """Discrepancias del LLM que cuentan como correccion. Unico filtro: lo usan
    `apply_veto_disagreements` y el eval-set, para que midan lo mismo."""
    valid = {}
    for field, llm_value in disagreements.items():
        if field == "activity" and _veto_would_generalize(regex_values.get(field), llm_value):
            # La lista del LLM no tiene todas las actividades concretas: si solo puede
            # decir la generica de la MISMA familia ("padi_specialty" frente a
            # "specialty_mindful_diving"), eso no es una correccion, es perder lo que
            # el cliente nombro (2026-09-15).
            logger.info(
                f"[EXTRACT][ACTIVITY_VETO] ignorado (generaliza) regex={regex_values.get(field)!r} "
                f"llm={llm_value!r} msg={_log_safe_message(message)!r}"
            )
            continue
        valid[field] = llm_value
    return valid


def apply_veto_disagreements(
    disagreements: dict, regex_intent: DetectedIntent, message: str,
    regex_values: dict | None = None,
) -> None:
    """Aplica (o solo loguea) las discrepancias que devolvio el LLM.

    Separado de la LLAMADA a proposito: desde que `extract_and_verify` puede
    traer las discrepancias en la misma peticion que los huecos (ver
    `conversational_core._understand`), hay DOS sitios que obtienen
    discrepancias y uno solo que decide que hacer con ellas. La semantica
    delicada -- aplicar POR CAMPO segun SU flag de cutover, y el side-effect
    de `spec.apply` -- vive aqui una sola vez.
    """
    regex_values = regex_values or {}
    for field, llm_value in valid_veto_corrections(disagreements, regex_values, message).items():
        spec = _VETO_FIELD_SPECS[field]
        cutover = getattr(settings, spec.cutover_flag)
        logger.info(
            f"[EXTRACT][{field.upper()}_VETO] regex={regex_values.get(field)!r} "
            f"llm={llm_value!r} applied={cutover} msg={_log_safe_message(message)!r}"
        )
        if cutover:
            setattr(regex_intent, field, llm_value)
            if spec.apply:
                spec.apply(regex_intent, llm_value)


async def _maybe_veto_resolved_field_via_llm(
    field: str, message: str, regex_intent: DetectedIntent, state: ConversationState
) -> None:
    """Atajo de un solo campo sobre `_maybe_veto_resolved_fields_via_llm`."""
    await _maybe_veto_resolved_fields_via_llm(message, regex_intent, state, only_fields=[field])


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

    if intent.duration and not state.detected_duration:
        state.detected_duration = intent.duration
        logger.info(f"[INTENT] Detected duration: {intent.duration}")

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
