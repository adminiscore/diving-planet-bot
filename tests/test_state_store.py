"""Pure serialize/deserialize round-trip tests for state_store — no Redis needed."""

import json

from src.agents.intent_detector import DetectedIntent
from src.flows.state import ConversationState, Step
from src.state_store import _PROCESSED_TTL, _STATE_TTL, deserialize_state, serialize_state


def test_dedup_outlives_the_window_in_which_a_message_can_be_reread():
    """INCIDENTE REAL (PRE, 2026-09-11): `_PROCESSED_TTL` era 3600 ("1 hour:
    dedup only needs to survive the webhook/poll race window"), pero
    `poll_active_conversations_once` RELEE todos los mensajes de cada
    conversación del set activo cada segundo, durante toda la vida del
    estado (30 días). Al caducar el dedup a la hora, el bot volvía a
    responder mensajes ya contestados: ~110/hora las 24h, con respuesta
    enviada a Chatwoot, y ~14.000 peticiones/día a OpenAI (por encima del
    límite de 10.000 de la cuenta).

    El invariante que hay que preservar no es un número concreto sino la
    relación: el marcador de "ya procesado" debe durar al menos tanto como
    la ventana en la que ese mensaje puede volver a leerse."""
    assert _PROCESSED_TTL >= _STATE_TTL, (
        "el dedup debe sobrevivir tanto como el estado: si caduca antes, el "
        "poller vuelve a responder mensajes ya contestados"
    )


def make_state(**overrides) -> ConversationState:
    state = ConversationState(conversation_id="test-conv")
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


def roundtrip(state: ConversationState) -> ConversationState:
    return deserialize_state(serialize_state(state))


def test_roundtrip_default_state():
    state = make_state()
    result = roundtrip(state)
    assert result == state


def test_roundtrip_non_default_step_and_back_step_override():
    state = make_state(step=Step.FREE_TEXT, back_step_override=Step.MAIN_MENU)
    result = roundtrip(state)
    assert result.step == Step.FREE_TEXT
    assert result.back_step_override == Step.MAIN_MENU


def test_roundtrip_back_step_override_none():
    state = make_state(back_step_override=None)
    result = roundtrip(state)
    assert result.back_step_override is None


def test_roundtrip_pending_intent_confirmation_with_detected_intent():
    intent = DetectedIntent(
        language="es",
        activity="padi_open_water",
        is_certified=True,
        group_size=2,
        detected_fields=["language", "activity"],
    )
    state = make_state(pending_intent_confirmation=intent)
    result = roundtrip(state)
    assert isinstance(result.pending_intent_confirmation, DetectedIntent)
    assert result.pending_intent_confirmation == intent


def test_deserialize_state_drops_field_removed_from_dataclass():
    """Hallazgo en vivo (2026-09-10): `mixed_pending_course_question` se
    borro de ConversationState como limpieza de codigo muerto (2026-07-29,
    docs/multi-agent-refactor-plan.md), pero un estado viejo guardado en
    Redis con ese campo todavia serializado hacia fallar
    `ConversationState(**data)` con TypeError en CADA poll de esa
    conversacion, para siempre (hasta expirar el TTL). La deserializacion
    debe ser tolerante a campos desconocidos -- los descarta, no falla."""
    raw = json.loads(serialize_state(make_state()))
    raw["mixed_pending_course_question"] = "algun_valor_viejo"
    raw["otro_campo_que_ya_no_existe"] = 42
    result = deserialize_state(json.dumps(raw), conversation_id="test-conv")
    assert result.conversation_id == "test-conv"
    assert not hasattr(result, "mixed_pending_course_question")


def test_deserialize_state_drops_field_removed_from_detected_intent():
    """Mismo hallazgo, pero para un campo obsoleto dentro del
    DetectedIntent envuelto en pending_intent_confirmation."""
    intent = DetectedIntent(language="es", activity="minicourse")
    state = make_state(pending_intent_confirmation=intent)
    raw = json.loads(serialize_state(state))
    raw["pending_intent_confirmation"]["data"]["campo_obsoleto_de_intent"] = "x"
    result = deserialize_state(json.dumps(raw), conversation_id="test-conv")
    assert isinstance(result.pending_intent_confirmation, DetectedIntent)
    assert result.pending_intent_confirmation.activity == "minicourse"


def test_roundtrip_pending_intent_confirmation_none():
    state = make_state(pending_intent_confirmation=None)
    result = roundtrip(state)
    assert result.pending_intent_confirmation is None


def test_roundtrip_mixed_booking_links_tuples():
    state = make_state(mixed_booking_links=[("Open Water", "https://roverd/ow"), ("Snorkel", "https://roverd/sn")])
    result = roundtrip(state)
    assert result.mixed_booking_links == [("Open Water", "https://roverd/ow"), ("Snorkel", "https://roverd/sn")]
    assert all(isinstance(item, tuple) for item in result.mixed_booking_links)


def test_roundtrip_various_none_fields():
    state = make_state(
        selected_service=None,
        is_certified=None,
        location=None,
        island=None,
        hotel=None,
        is_colombian=None,
    )
    result = roundtrip(state)
    assert result.selected_service is None
    assert result.is_certified is None
    assert result.location is None
    assert result.island is None
    assert result.hotel is None
    assert result.is_colombian is None


def test_roundtrip_mixed_cart_and_quick_replies():
    state = make_state(
        mixed_cart=[{"type": "cert", "qty": 2, "plan": "3_dives", "label": "Certified 3 dives"}],
        quick_replies=[{"title": "Sí", "value": "yes"}],
    )
    result = roundtrip(state)
    assert result.mixed_cart == state.mixed_cart
    assert result.quick_replies == state.quick_replies
