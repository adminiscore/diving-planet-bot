"""Paso 6 (flag `s4_fixes`, 27-sep): salida y flujo deterministas de S4.

- s4-14: si piden un teléfono, el WhatsApp oficial (de la base de conocimiento), decisión de Gadea.
- s4-15: "¿eres un bot?" -> dice que es la asistente virtual.
- s4-16: la queja pasa a staff con una disculpa.
- s4-21: nunca un id interno en el resumen; el aviso sensible en el idioma del mensaje de apertura;
  un acuse sin prosa ('{" "}') se descarta.
- s4-7: "¿cómo pago?" -> el link de reserva, no "un asesor te enviará el enlace".
- s4-20: post-venta y empresa (Jev `needs_staff`) -> una persona, antes del núcleo.
- s4-6: cambio de fecha con el carrito abierto (Jev `changes_date`) -> política + asesor.
"""

from __future__ import annotations

import pytest

from src.agents import escalation, jev_router, supervisor
from src.agents import rag_agent
from src.config import Settings, settings
from src.domain import activities as dom
from src.flows.state import ConversationState
from src.orchestration import router
from src.prompts import info


def _state(**kw) -> ConversationState:
    s = ConversationState(conversation_id="s4")
    s.language = "es"
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_el_flag_nace_apagado():
    assert Settings().s4_fixes is False


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(settings, "s4_fixes", True)


# ─── Respuestas fijas ────────────────────────────────────────────────────────

def test_si_piden_telefono_se_da_el_whatsapp_oficial(on):
    number = supervisor._official_whatsapp()
    assert number and number.startswith("+57")
    assert number in supervisor._contact_number_deflection("es")
    assert number in supervisor._contact_number_deflection("en")


def test_sin_el_flag_no_se_da_el_numero(monkeypatch):
    monkeypatch.setattr(settings, "s4_fixes", False)
    assert "no manejo un número" in supervisor._contact_number_deflection("es")


def test_eres_un_bot_dice_que_es_la_asistente_virtual(on):
    assert "asistente virtual" in supervisor._ai_identity_deflection("es")
    assert "virtual assistant" in supervisor._ai_identity_deflection("en")


def test_la_queja_pasa_a_staff_con_una_disculpa(on):
    _, text = escalation.sensitive_response_for("complaints_or_emergencies", "es")
    assert "Siento mucho" in text and "staff" in text
    _, text = escalation.detect_sensitive_escalation("this is a scam, I want my money back", "en")
    assert "sorry" in text.lower()


# ─── s4-21 ───────────────────────────────────────────────────────────────────

def test_un_resumen_nunca_muestra_un_id_interno():
    for act in dom.activity_ids():
        for lang in ("es", "en"):
            text = dom.text(act, "recall", lang, default=act)
            assert text and "_" not in text, (act, lang, text)


def test_el_aviso_sensible_sale_en_el_idioma_del_mensaje_de_apertura():
    st = _state()
    assert supervisor._reply_language(st, "I completed the medical form, is that ok?") == "en"
    assert supervisor._reply_language(st, "tengo asma, ¿puedo bucear?") == "es"
    st.detected_language = "es"
    assert supervisor._reply_language(st, "I have asthma") == "es"  # ya fijado: se respeta


async def test_un_acuse_sin_prosa_se_descarta(monkeypatch):
    from src.agents import llm_extractor

    class _Msg:
        content = '{" "}'

    class _Resp:
        choices = [type("C", (), {"message": _Msg()})()]

    class _Cli:
        def __init__(self, *a, **k):
            async def create(**kw):
                return _Resp()
            self.chat = type("Ch", (), {"completions": type("Co", (), {"create": staticmethod(create)})()})()

    monkeypatch.setattr(llm_extractor, "AsyncOpenAI", _Cli)
    monkeypatch.setattr(llm_extractor, "trace_openai", lambda c: c)
    assert await llm_extractor.compose_acknowledgement("somos 4", lang="es") == ""


# ─── s4-7 ────────────────────────────────────────────────────────────────────

def test_las_vinetas_de_pago_de_antes_siguen_en_el_prompt():
    """Si alguien las reescribe, la sustitución del flag dejaría de aplicarse sin avisar."""
    assert info.RAG_PAYMENT_OLD_ES in info.RAG_BODY_ES
    assert info.RAG_PAYMENT_OLD_EN in info.RAG_BODY_EN


def test_con_el_flag_el_prompt_manda_al_link_de_reserva(on):
    for lang, new, old in (("es", info.RAG_PAYMENT_V2_ES, info.RAG_PAYMENT_OLD_ES),
                           ("en", info.RAG_PAYMENT_V2_EN, info.RAG_PAYMENT_OLD_EN)):
        prompt = rag_agent.build_system_prompt(lang)
        assert new in prompt and old not in prompt


# ─── s4-20 y s4-6: preguntas de Jev ──────────────────────────────────────────

def test_las_preguntas_nuevas_solo_van_con_el_flag(monkeypatch):
    monkeypatch.setattr(settings, "s4_fixes", False)
    q = jev_router._questions_for_turn()
    assert jev_router.NEEDS_STAFF not in q and jev_router.CHANGES_DATE not in q
    monkeypatch.setattr(settings, "s4_fixes", True)
    q = jev_router._questions_for_turn()
    assert jev_router.NEEDS_STAFF in q and jev_router.CHANGES_DATE in q
    out = jev_router.answers_to_signals({"needs_staff": {"noul": 0.9}, "changes_date": {"noul": 0.2}})
    assert out["needs_staff"] is True and out["changes_date"] is False


def test_post_venta_pasa_a_una_persona(on):
    st = _state()
    reply = supervisor._needs_staff_handoff(st, "ya hice la reserva, ¿la recibieron?", {"needs_staff": True})
    assert reply and "asesor" in reply
    assert st.pending_escalation_reason and st.step.value == "escalate"
    assert supervisor._needs_staff_handoff(_state(), "hola", {"needs_staff": False}) is None


def test_post_venta_va_al_nodo_de_escalado(on):
    assert router.classify_route(_state(), "¿está todo ok con mis reservas?", {"needs_staff": True}) == router.ROUTE_SAFETY


def test_cambio_de_fecha_con_el_carrito_abierto_va_a_cambios(on, monkeypatch):
    st = _state(detected_activity="snorkel", detected_group_size=3, location="cartagena")
    monkeypatch.setattr(supervisor, "_in_active_cart_building", lambda s: True)
    signals = {"booking_change_topic": "reschedule", "changes_date": True}
    assert router.classify_route(st, "espera, mejor cambiemos la fecha", signals) == router.ROUTE_CHANGE
    # sin la pregunta de Jev, la señal del router sigue sin valer con el carrito abierto
    assert router.classify_route(st, "hazlo para 3 días", {"booking_change_topic": "reschedule"}) != router.ROUTE_CHANGE
