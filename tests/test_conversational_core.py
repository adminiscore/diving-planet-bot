"""Tests del núcleo conversacional de slot-filling (docs/conversational-refactor-plan.md).

Todo offline: el gap-filler LLM se mockea (patch de conversational_core.fill_gaps)
y RAG usa el stub del conftest (supervisor.rag_answer). El flag
settings.conversational_core se enciende por test — con el flag apagado (default)
el resto de la suite prueba que el comportamiento legacy queda intacto.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import conversational_core as core
from src.agents.supervisor import route_message
from src.config import settings
from src.flows.decision_tree import ConversationState, Step


def make_state(lang: str = "es") -> ConversationState:
    s = ConversationState(conversation_id="core-test")
    s.language = lang
    return s


@pytest.fixture(autouse=True)
def _core_on(monkeypatch):
    """Enciende el núcleo para todos los tests de este módulo y deja el
    gap-filler en no-op por defecto (cada test lo re-mockea si necesita que
    el LLM 'rellene' algo). settings es una instancia compartida, así que
    parchearlo aquí lo ve también el hook del supervisor."""
    monkeypatch.setattr(settings, "conversational_core", True)
    monkeypatch.setattr(core, "fill_gaps", AsyncMock(return_value={}))


# ---------------------------------------------------------------------------
# next_missing_slot (lógica pura)
# ---------------------------------------------------------------------------

def test_slot_order_empty_state_asks_activity():
    state = make_state()
    assert core.next_missing_slot(state) == core.SLOT_ACTIVITY


def test_slot_order_diving_without_cert_asks_certification():
    state = make_state()
    state.detected_activity = "certified_diving"
    assert core.next_missing_slot(state) == core.SLOT_CERTIFICATION


def test_slot_order_cert_known_asks_location():
    state = make_state()
    state.detected_activity = "certified_diving"
    state.is_certified = True
    assert core.next_missing_slot(state) == core.SLOT_LOCATION


def test_slot_order_island_needs_hotel():
    state = make_state()
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "island"
    assert core.next_missing_slot(state) == core.SLOT_HOTEL


def test_slot_order_cert_needs_safety_then_qty_then_nationality():
    state = make_state()
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    assert core.next_missing_slot(state) == core.SLOT_SAFETY
    state.last_dive_over_2_years = False
    assert core.next_missing_slot(state) == core.SLOT_QTY
    state.detected_group_size = 2
    assert core.next_missing_slot(state) == core.SLOT_NATIONALITY
    state.is_colombian = False
    assert core.next_missing_slot(state) is None


def test_slot_order_safety_true_asks_refresher():
    state = make_state()
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    state.last_dive_over_2_years = True
    assert core.next_missing_slot(state) == core.SLOT_REFRESHER
    state.refresher_interested = True
    assert core.next_missing_slot(state) == core.SLOT_QTY


def test_slot_order_beginner_skips_safety():
    """Un no-certificado (minicurso) no tiene pregunta de última inmersión."""
    state = make_state()
    state.detected_activity = "certified_diving"
    state.is_certified = False  # → minicurso efectivo
    state.location = "cartagena"
    assert core.next_missing_slot(state) == core.SLOT_QTY


def test_slot_order_minors_mentioned_asks_ages():
    state = make_state()
    state.detected_activity = "snorkel"
    state.location = "cartagena"
    state.detected_group_size = 3
    state.kids_mention_detected = True
    assert core.next_missing_slot(state) == core.SLOT_AGES
    state.detected_ages = [8]
    assert core.next_missing_slot(state) == core.SLOT_NATIONALITY


# ---------------------------------------------------------------------------
# Flujo completo ES (guion Sofía): certificada, 1 persona, Cartagena
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sofia_full_flow_spanish():
    state = make_state("es")
    resp = await route_message(state, "hola soy Sofia, ya soy certificada, quiero unas inmersiones desde cartagena")
    # activity+cert+location+qty(1, inferencia singular) conocidos → pregunta seguridad
    assert core.next_missing_slot(state) == core.SLOT_NATIONALITY or state.core_pending_slot == core.SLOT_SAFETY
    assert state.core_pending_slot == core.SLOT_SAFETY
    assert "2 años" in resp or "2 anos" in resp
    # Recomendación del plan popular incluida (decisión v0.20.27), sin duplicar "Genial"
    assert resp.lower().count("genial") <= 1

    resp = await route_message(state, "no")
    assert state.last_dive_over_2_years is False
    assert state.core_pending_slot == core.SLOT_NATIONALITY

    resp = await route_message(state, "no")
    # Completo → resumen determinista con link del catálogo
    assert state.is_colombian is False
    assert "divingplanet.org" in resp
    assert state.mixed_cart and state.mixed_cart[0]["type"] == "cert"
    assert state.mixed_cart[0]["qty"] == 1
    assert state.mixed_cart[0]["plan"] == "2_dives_1_day"


@pytest.mark.asyncio
async def test_safety_never_reasked_after_answered():
    """Bug 3-4 de Rocío: la pregunta de seguridad no puede repetirse una vez
    respondida — por construcción del slot-filling."""
    state = make_state("es")
    await route_message(state, "hola soy Rocio, tengo el open water y quiero hacer buceo desde cartagena, soy solo yo")
    assert state.core_pending_slot == core.SLOT_SAFETY
    await route_message(state, "no")
    # Mensajes posteriores: la seguridad ya está resuelta, nunca vuelve a pedirse
    resp = await route_message(state, "no somos colombianos")
    assert "2 años" not in resp and "2 anos" not in resp
    assert state.last_dive_over_2_years is False


# ---------------------------------------------------------------------------
# Flujo completo EN
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_flow_english():
    state = make_state("en")
    await route_message(state, "hi, we are 2 certified divers, from cartagena")
    assert state.core_pending_slot == core.SLOT_SAFETY
    await route_message(state, "no")
    resp = await route_message(state, "no, we're foreigners")
    assert "divingplanet.org" in resp
    assert "language=en" in resp
    assert state.mixed_cart[0]["qty"] == 2


# ---------------------------------------------------------------------------
# Carryover contextual (monosílabos / respuestas cortas)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_short_answer_resolves_pending_location():
    state = make_state("es")
    await route_message(state, "quiero bucear, somos 2 certificados")
    assert state.core_pending_slot == core.SLOT_LOCATION
    await route_message(state, "cartagena")
    assert state.location == "cartagena"
    assert state.core_pending_slot == core.SLOT_SAFETY


@pytest.mark.asyncio
async def test_short_answer_island_then_hotel():
    state = make_state("es")
    await route_message(state, "quiero bucear, somos 2 certificados")
    await route_message(state, "ya estamos en las islas")
    assert state.location == "island"
    assert state.core_pending_slot == core.SLOT_HOTEL
    await route_message(state, "hotel Cocoliso")
    assert state.hotel and "cocoliso" in state.hotel.lower()
    assert state.core_pending_slot == core.SLOT_SAFETY


@pytest.mark.asyncio
async def test_multi_slot_message_absorbed_in_one_turn():
    """Una frase con varios datos rellena varios slots a la vez — nunca se
    re-pregunta lo ya dicho (bug 5 por construcción)."""
    state = make_state("es")
    await route_message(state, "somos 3 certificados desde cartagena, la última inmersión fue hace 1 año")
    assert state.detected_group_size == 3
    assert state.location == "cartagena"
    assert state.last_dive_over_2_years is False
    assert state.core_pending_slot == core.SLOT_NATIONALITY


# ---------------------------------------------------------------------------
# Preguntas de info mid-flujo → RAG + retomar el slot sin perderlo
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_question_mid_flow_answers_and_reasks_pending_slot():
    state = make_state("es")
    await route_message(state, "quiero bucear, soy certificado, desde cartagena")
    assert state.core_pending_slot == core.SLOT_SAFETY
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock,
               return_value="RESPUESTA_RAG") as mocked:
        resp = await route_message(state, "¿qué incluye el precio?")
    mocked.assert_awaited_once()
    assert "RESPUESTA_RAG" in resp
    # Retoma el slot pendiente en el mismo mensaje (cierre a conversión)
    assert "2 años" in resp or "2 anos" in resp
    assert state.core_pending_slot == core.SLOT_SAFETY


# ---------------------------------------------------------------------------
# Gap-filler LLM como motor de slots (mensaje que el regex no entiende)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_gap_fill_feeds_slots(monkeypatch):
    state = make_state("en")
    monkeypatch.setattr(core, "fill_gaps", AsyncMock(return_value={
        "activity": "minicourse", "is_certified": False, "group_size": 1,
    }))
    resp = await route_message(state, "never been underwater before, wanna give it a try, solo")
    assert state.detected_activity == "minicourse"
    # minicurso: sin pregunta de seguridad; ubicación es el siguiente slot
    assert state.core_pending_slot == core.SLOT_LOCATION
    assert "Cartagena" in resp


# ---------------------------------------------------------------------------
# Gating colombiano: sin link directo → asesor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_colombian_checkout_escalates_no_direct_link():
    state = make_state("es")
    await route_message(state, "somos 2 buzos certificados desde cartagena, buceamos el mes pasado")
    assert state.core_pending_slot == core.SLOT_NATIONALITY
    resp = await route_message(state, "sí, somos colombianos")
    assert state.is_colombian is True
    assert state.step == Step.ESCALATE
    assert "asesor" in resp.lower()
    assert "book.divingplanet.org" not in resp
    assert state.mixed_display_currency == "COP"


# ---------------------------------------------------------------------------
# Re-pregunta sin repetición (hallazgo del guion Rocío en vivo, 2026-07-22)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reask_does_not_repeat_plan_recommendation():
    """Cuando la respuesta del cliente no resuelve el slot pendiente pero
    aporta otro dato ("desde cartagena" respondiendo a la pregunta de
    seguridad), la re-pregunta NO debe repetir la recomendación del plan —
    en vivo se veía 3 veces el mismo bloque entero."""
    state = make_state("es")
    await route_message(state, "hola soy rocio, tengo el open water y quiero hacer buceo")
    assert state.core_pending_slot == core.SLOT_LOCATION
    r2 = await route_message(state, "desde cartagena")
    assert state.core_pending_slot == core.SLOT_SAFETY
    assert "recomiendo" in r2.lower()  # primera vez: sí recomienda
    r3 = await route_message(state, "soy solo yo")  # no responde seguridad, aporta qty
    assert state.detected_group_size == 1
    assert state.core_pending_slot == core.SLOT_SAFETY
    assert "recomiendo" not in r3.lower(), "la re-pregunta no debe repetir la recomendación"
    assert "2 años" in r3 or "2 anos" in r3


# ---------------------------------------------------------------------------
# Fase 2 — multi-actividad (grupo mixto / acompañante por texto)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_allocation_builds_multi_item_cart():
    """"somos 5, 3 certificados y 2 quieren snorkel" → carrito con 2 ítems,
    sin perder a nadie (bug histórico del árbol, por construcción aquí)."""
    state = make_state("es")
    await route_message(state, "somos 5, 3 buceamos certificados y 2 hacen snorkel, desde cartagena")
    # El subgrupo cert existe → la pregunta de seguridad aplica
    assert state.core_pending_slot == core.SLOT_SAFETY
    await route_message(state, "no")
    resp = await route_message(state, "no somos colombianos")
    types = {it["type"]: it["qty"] for it in state.mixed_cart}
    assert types.get("cert") == 3
    assert types.get("snorkel") == 2
    assert resp.count("divingplanet.org") >= 2  # un link por actividad


@pytest.mark.asyncio
async def test_snorkel_companion_added_after_close():
    """Guion Rocío completo: tras el cierre con links, "viene también uno que
    hace snorkel" añade el ítem al carrito y re-emite el resumen con ambos."""
    state = make_state("es")
    await route_message(state, "hola soy rocio, tengo el open water y quiero hacer buceo")
    await route_message(state, "desde cartagena")
    await route_message(state, "soy solo yo")
    await route_message(state, "no")
    resp = await route_message(state, "no soy colombiana")
    assert state.mixed_cart[0]["type"] == "cert"

    resp = await route_message(state, "viene tambien uno que hace snorkel")
    types = {it["type"]: it["qty"] for it in state.mixed_cart}
    assert types.get("cert") == 1, "el buceo original no puede perderse"
    assert types.get("snorkel") == 1, "el acompañante snorkel debe añadirse"
    assert "norkel" in resp  # el resumen re-emitido incluye la actividad nueva


@pytest.mark.asyncio
async def test_companion_beginner_added_mid_flow():
    """Acompañante minicurso mencionado ANTES del cierre: se acumula en el
    reparto y el carrito final tiene ambos ítems."""
    state = make_state("es")
    await route_message(state, "soy buzo certificado, quiero bucear desde cartagena, voy solo")
    assert state.core_pending_slot == core.SLOT_SAFETY
    await route_message(state, "mi novia no es buzo, ella viene y hace el minicurso")
    # sigue pendiente la seguridad (del subgrupo cert), sin perder el añadido
    assert state.core_pending_slot == core.SLOT_SAFETY
    await route_message(state, "no")
    await route_message(state, "no somos colombianos")
    types = {it["type"]: it["qty"] for it in state.mixed_cart}
    assert types.get("cert") == 1
    assert types.get("beginner") == 1


# ---------------------------------------------------------------------------
# Fase 3 — cursos PADI + checkout completo (menores/edades, lead note)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_padi_course_flow_no_cert_no_safety_questions():
    """Un curso PADI no pregunta certificación ni seguridad (no aplican):
    actividad → ubicación → cantidad → nacionalidad → resumen con el link
    del curso."""
    state = make_state("es")
    await route_message(state, "quiero hacer el curso open water, somos 2")
    assert state.core_pending_slot == core.SLOT_LOCATION
    await route_message(state, "desde cartagena")
    assert state.core_pending_slot == core.SLOT_NATIONALITY
    resp = await route_message(state, "no somos colombianos")
    assert state.mixed_cart[0]["type"] == "course"
    assert state.mixed_cart[0]["plan"] == "open_water"
    assert state.mixed_cart[0]["qty"] == 2
    assert "divingplanet.org" in resp
    # El boilerplate de curso, no el de tour de un día
    assert "Curso PADI" in resp


# FASE 3 — cerrada (2026-07-22): las 2 causas raíz del handoff quedaron
# arregladas en conversational_core:
#   (A) "voy solo" en contexto de CURSO → _COURSE_SOLO_RE/_NOT_ALONE_RE fijan
#       group_size=1 en _understand (scoped al núcleo, no toca el detector).
#   (B) el carryover del slot pendiente corre ANTES del check de pregunta en
#       maybe_handle_turn — una respuesta que "parece pregunta" ("tienen 7 y 9
#       años") resuelve el slot; un "?" explícito sigue yendo a RAG.
@pytest.mark.asyncio
async def test_padi_course_island_variant_resolved():
    state = make_state("es")
    await route_message(state, "quiero el curso open water, ya estoy en las islas, voy solo")
    assert state.core_pending_slot == core.SLOT_HOTEL
    await route_message(state, "hotel Cocoliso")
    await route_message(state, "no soy colombiano")
    assert state.mixed_cart[0]["plan"] == "open_water_already_on_island"


@pytest.mark.asyncio
async def test_divemaster_contact_only_no_direct_link():
    """Divemaster es contact-only: resumen sin link de reserva directa, con
    el copy de asesor."""
    state = make_state("es")
    await route_message(state, "quiero el curso de divemaster, voy solo, desde cartagena")
    resp = await route_message(state, "no soy colombiano")
    assert state.mixed_cart[0]["plan"] == "divemaster"
    assert "book.divingplanet.org" not in resp
    assert "asesor" in resp.lower()


@pytest.mark.asyncio
async def test_kids_ages_split_cart_blocks():
    """Menores con edades explícitas: el checkout separa por edad — <8 va a
    snorkel, 8-10 a Bubble Makers — reutilizando el split del catálogo."""
    state = make_state("es")
    await route_message(state, "queremos el minicurso mi esposa y yo con nuestros hijos, somos 4, desde cartagena")
    assert state.kids_mention_detected
    assert state.core_pending_slot == core.SLOT_AGES
    await route_message(state, "tienen 7 y 9 años")
    resp = await route_message(state, "no somos colombianos")
    assert state.kids_under_8_count == 1
    assert state.kids_eight_to_ten_count == 1
    assert "Bubble Makers" in resp
    assert "norkel" in resp  # el de 7 va a snorkel


@pytest.mark.asyncio
async def test_lead_note_built_at_close():
    """El cierre no-colombiano deja la nota de lead construida (antes solo
    quedaba el pending_lead_note_reason sin materializar)."""
    state = make_state("es")
    await route_message(state, "soy buzo certificado, quiero bucear desde cartagena, voy solo")
    await route_message(state, "no")
    await route_message(state, "no soy colombiano")
    assert state.pending_note, "la nota de lead debe quedar construida al cierre"


# ---------------------------------------------------------------------------
# El núcleo delega en los handlers legacy lo que no le toca
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalation_keyword_still_escalates():
    state = make_state("es")
    state.step = Step.MAIN_MENU
    await route_message(state, "asesor")
    assert state.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_menu_keyword_falls_through_to_legacy_reset():
    state = make_state("es")
    state.step = Step.FREE_TEXT
    await route_message(state, "menu")
    assert state.step == Step.MAIN_MENU


@pytest.mark.asyncio
async def test_sensitive_medical_still_escalates_before_core():
    state = make_state("es")
    state.step = Step.MAIN_MENU
    await route_message(state, "estoy embarazada, ¿puedo bucear?")
    assert state.step == Step.ESCALATE


# ---------------------------------------------------------------------------
# Flag apagado → el núcleo no interviene (comportamiento legacy intacto)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_flag_off_core_not_engaged(monkeypatch):
    monkeypatch.setattr(settings, "conversational_core", False)
    state = make_state("es")
    with patch.object(core, "maybe_handle_turn",
                      new=AsyncMock(side_effect=AssertionError("core must not run"))):
        await route_message(state, "hola quiero bucear, soy certificado")
    # (la aserción del mock es la prueba; el estado sigue el camino legacy)
    assert state.core_pending_slot is None
