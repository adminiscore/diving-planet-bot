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
    gap-filler y el detector de señales (recordar/acompañante) en no-op por
    defecto (cada test los re-mockea si necesita que el LLM 'decida' algo).
    settings es una instancia compartida, así que parchearlo aquí lo ve
    también el hook del supervisor."""
    monkeypatch.setattr(settings, "conversational_core", True)
    monkeypatch.setattr(core, "fill_gaps", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "detect_special_signals", AsyncMock(return_value={}))


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


def test_slot_order_cert_needs_qty_then_safety_then_nationality():
    """Decisión owner (2026-07-22): la CANTIDAD va antes que la seguridad, para
    que la pregunta de los 2 años ya sepa si hablar en singular o plural en vez
    de adivinar (se veía "¿tu última inmersión?" a un grupo aún sin contar)."""
    state = make_state()
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    assert core.next_missing_slot(state) == core.SLOT_QTY
    state.detected_group_size = 2
    assert core.next_missing_slot(state) == core.SLOT_SAFETY
    state.last_dive_over_2_years = False
    assert core.next_missing_slot(state) == core.SLOT_NATIONALITY
    state.is_colombian = False
    assert core.next_missing_slot(state) is None


def test_slot_order_safety_true_asks_refresher():
    state = make_state()
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    state.detected_group_size = 2
    state.last_dive_over_2_years = True
    assert core.next_missing_slot(state) == core.SLOT_REFRESHER
    state.refresher_interested = True
    assert core.next_missing_slot(state) == core.SLOT_NATIONALITY


def test_safety_question_knows_group_size_because_qty_comes_first():
    """Consecuencia práctica del reorden: al preguntar la seguridad ya se sabe
    la cantidad, así que la frase sale en plural para un grupo y en singular
    para una persona — sin adivinar."""
    solo = make_state("es")
    solo.detected_activity = "certified_diving"
    solo.is_certified = True
    solo.location = "cartagena"
    solo.detected_group_size = 1
    assert "tu última inmersión" in core.ask_slot(solo, core.SLOT_SAFETY)

    grupo = make_state("es")
    grupo.detected_activity = "certified_diving"
    grupo.is_certified = True
    grupo.location = "cartagena"
    grupo.detected_group_size = 3
    assert "del grupo" in core.ask_slot(grupo, core.SLOT_SAFETY)


@pytest.mark.asyncio
async def test_solo_signal_infers_one_person_for_diving_too():
    """Decisión owner (2026-07-22): la señal explícita "voy solo" deduce 1
    persona en CUALQUIER actividad, no solo en cursos PADI (antes solo padi_*).
    Sin señal explícita se sigue preguntando (ver el test de abajo)."""
    state = make_state("es")
    await route_message(state, "soy buzo certificado y quiero bucear, voy solo, desde cartagena")
    assert state.detected_group_size == 1
    assert state.core_pending_slot == core.SLOT_SAFETY  # ya no pregunta cantidad


@pytest.mark.asyncio
async def test_solo_signal_infers_one_person_for_snorkel():
    state = make_state("es")
    await route_message(state, "quiero hacer snorkel, voy sola, desde cartagena")
    assert state.detected_group_size == 1


@pytest.mark.asyncio
async def test_no_solo_signal_still_asks_quantity():
    """El caso de Rocío: auto-presentación en singular SIN decir que va sola —
    un jefe de grupo escribiría igual, así que se pregunta (no se asume)."""
    state = make_state("es")
    await route_message(state, "hola soy rocio, tengo el open water y quiero hacer buceo desde cartagena")
    assert state.detected_group_size is None
    assert state.core_pending_slot == core.SLOT_QTY


@pytest.mark.asyncio
async def test_company_signal_beats_solo_word():
    """Guarda conservadora: si hay señal de compañía, aunque aparezca "solo",
    se pregunta la cantidad."""
    state = make_state("es")
    await route_message(state, "quiero bucear, soy certificado, voy con mi novia, desde cartagena")
    assert state.detected_group_size != 1 or state.core_pending_slot == core.SLOT_QTY


def test_nationality_question_singular_for_one_person():
    """Coral pregunta en singular a quien viaja solo (antes salía siempre en
    plural: "¿sois colombianos?" a una sola persona)."""
    solo = make_state("es")
    solo.detected_group_size = 1
    q = core.ask_slot(solo, core.SLOT_NATIONALITY)
    assert "eres colombiano" in q
    assert "sois" not in q

    grupo = make_state("es")
    grupo.detected_group_size = 3
    assert "sois colombianos" in core.ask_slot(grupo, core.SLOT_NATIONALITY)


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
# Persona: Coral se presenta en el primer turno (cálida, Diving Planet, sin
# llamarse a sí misma "asistente"/"bot") y no repite el saludo después.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_turn_greets_as_coral_diving_planet():
    import re as _re
    state = make_state("es")
    resp = await route_message(state, "hola soy Sofia, ya soy certificada, quiero unas inmersiones desde cartagena")
    assert "Coral" in resp
    assert "Diving Planet" in resp
    assert "asistente" not in resp.lower()
    assert not _re.search(r"\bbot\b", resp.lower())
    # El saludo NO sustituye a la pregunta del slot: sigue avanzando la reserva
    assert state.core_pending_slot == core.SLOT_SAFETY


@pytest.mark.asyncio
async def test_first_turn_bare_greeting_presents_and_asks_activity():
    state = make_state("es")
    resp = await route_message(state, "hola")
    assert "Coral" in resp
    assert "Diving Planet" in resp
    assert state.core_pending_slot == core.SLOT_ACTIVITY


@pytest.mark.asyncio
async def test_greeting_not_repeated_after_first_turn():
    state = make_state("es")
    await route_message(state, "hola soy Sofia, ya soy certificada, quiero unas inmersiones desde cartagena")
    resp2 = await route_message(state, "no")
    assert "Coral" not in resp2  # el saludo es solo del primer turno


@pytest.mark.asyncio
async def test_first_turn_greeting_english():
    state = make_state("en")
    resp = await route_message(state, "hi, we are 2 certified divers, from cartagena")
    assert "Coral" in resp
    assert "Diving Planet" in resp
    assert "assistant" not in resp.lower()


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
    await route_message(state, "desde cartagena")
    # Orden nuevo (owner 2026-07-22): la cantidad va antes que la seguridad.
    assert state.core_pending_slot == core.SLOT_QTY
    r3 = await route_message(state, "soy solo yo")
    assert state.detected_group_size == 1
    assert state.core_pending_slot == core.SLOT_SAFETY
    assert "recomiendo" in r3.lower()  # primera vez que pregunta seguridad: sí recomienda
    # Un mensaje que NO resuelve la seguridad → re-pregunta sin repetir el bloque
    r4 = await route_message(state, "somos 3 en realidad")
    assert state.core_pending_slot == core.SLOT_SAFETY
    assert "recomiendo" not in r4.lower(), "la re-pregunta no debe repetir la recomendación"
    assert "2 años" in r4 or "2 anos" in r4


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


# ---------------------------------------------------------------------------
# Fix A del handoff (2026-07-22 tarde): el gap-fill del núcleo debe loguear en
# el MISMO formato que el cutover ([EXTRACT][CUTOVER] applied={...} msg='...'),
# con valores y mensaje completos — es lo que scripts/harvest_cutover_logs.py
# parsea para el bucle de datos reales (Fase 6 de robustez, hoy bloqueada).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gap_fill_logs_in_harvester_format(monkeypatch, caplog):
    import logging as _logging
    from scripts.harvest_cutover_logs import parse_lines

    state = make_state("es")
    monkeypatch.setattr(core, "fill_gaps", AsyncMock(return_value={"activity": "snorkel"}))
    with caplog.at_level(_logging.INFO, logger="uvicorn.error"):
        await route_message(state, "me gustaría hacer alguna actividad en el mar mañana")

    lines = [rec.getMessage() for rec in caplog.records]
    records = parse_lines(lines)
    assert records, f"el harvester no parseó ninguna línea de: {lines}"
    assert records[0]["patch"] == {"activity": "snorkel"}
    assert records[0]["message"] == "me gustaría hacer alguna actividad en el mar mañana"


# ---------------------------------------------------------------------------
# Fix B del handoff: no pedirle al LLM campos que el ESTADO ya conoce — los
# huecos se calculan contra el estado, no solo contra el intent del mensaje
# suelto. Sin huecos relevantes → ni siquiera se llama al LLM.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_understand_skips_llm_when_state_knows_driving_fields(monkeypatch):
    """Estado con todos los campos conductores conocidos (reserva lista salvo
    charla) → un mensaje suelto NO dispara llamada al LLM."""
    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = state.detected_is_certified = True
    state.location = state.detected_location = "cartagena"
    state.detected_group_size = 2
    state.last_dive_over_2_years = state.detected_last_dive_over_2_years = False
    state.is_colombian = False
    monkeypatch.setattr(core, "fill_gaps",
                        AsyncMock(side_effect=AssertionError("LLM must not be called")))
    await core._understand(state, "genial entonces nos vemos pronto por allá")


@pytest.mark.asyncio
async def test_understand_requests_only_state_missing_fields(monkeypatch):
    """Cuando SÍ hay huecos, la llamada pide SOLO los campos que el estado no
    conoce (ej. real de los logs de PRE: 'Cartagena' disparaba una llamada que
    rellenaba activity/is_certified/group_size — los tres ya conocidos)."""
    captured = {}

    async def _capturing_fill_gaps(message, intent, **kwargs):
        captured.update(kwargs)
        return {}

    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = state.detected_is_certified = True
    state.detected_group_size = 2
    # location aún desconocida → único hueco conductor
    monkeypatch.setattr(core, "fill_gaps", _capturing_fill_gaps)
    await core._understand(state, "pues estamos por el centro histórico ahora mismo")

    only = captured.get("only_fields")
    assert only is not None
    assert "location" in only
    assert "activity" not in only
    assert "is_certified" not in only
    assert "group_size" not in only


@pytest.mark.asyncio
async def test_understand_still_fills_when_state_is_empty(monkeypatch):
    """Primer mensaje (estado vacío): el gap-fill sigue funcionando igual."""
    state = make_state("en")
    monkeypatch.setattr(core, "fill_gaps", AsyncMock(return_value={
        "activity": "minicourse", "is_certified": False,
    }))
    await core._understand(state, "never tried it before but would love to")
    assert state.detected_activity == "minicourse"
    assert state.detected_is_certified is False


# ---------------------------------------------------------------------------
# Red de precisión: detect_special_signals (recordar / acompañante) —
# hallazgo en vivo 2026-07-22, decisión owner de NO ampliar más el regex.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recall_group_size_answers_from_state_not_rag():
    """"¿cuántas personas somos, me lo recuerdas?" — el bot YA sabe la
    cantidad; debe responder con el valor real del estado, sin pasar por RAG
    ni ofrecer un asesor (hallazgo en vivo: antes decía "eso no lo tengo a
    la mano")."""
    state = make_state("es")
    state.detected_group_size = 3
    state.core_pending_slot = core.SLOT_NATIONALITY
    with patch.object(core, "detect_special_signals", new=AsyncMock(return_value={"recall_field": "group_size"})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(side_effect=AssertionError("no debe ir a RAG"))):
        resp = await route_message(state, "cuantas personas somos, me lo recuerdas?")
    assert "3" in resp
    assert state.core_pending_slot == core.SLOT_NATIONALITY  # retoma el slot pendiente


@pytest.mark.asyncio
async def test_recall_unknown_field_falls_back_to_rag():
    """Si el LLM señala un campo que el estado NO tiene resuelto de verdad,
    _recall_answer devuelve None y el turno cae a RAG normal — nunca se
    inventa un valor."""
    state = make_state("es")
    state.core_pending_slot = core.SLOT_LOCATION
    with patch.object(core, "detect_special_signals", new=AsyncMock(return_value={"recall_field": "group_size"})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(return_value="Respuesta RAG")):
        resp = await route_message(state, "cuantos somos, recuerdame?")
    assert "Respuesta RAG" in resp


@pytest.mark.asyncio
async def test_companion_signal_adds_minicourse_not_regex_match():
    """"mi acompañante quiere hacer buceo pero no es certificado" — el regex
    NO lo reconoce (misma actividad que la principal, sin persona-añadida
    explícita); la señal LLM sí, y debe mapear a MINICURSO (no repetir el
    resumen de buceo certificado con un refresher que no venía a cuento)."""
    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    state.detected_group_size = 1
    state.last_dive_over_2_years = False
    state.core_pending_slot = core.SLOT_NATIONALITY
    with patch.object(core, "detect_special_signals",
                       new=AsyncMock(return_value={"companion_activity": "minicourse", "companion_qty": 1})):
        await route_message(state, "mi acompañante quiere hacer buceo pero no es certificado")
    alloc = state.detected_group_allocation or {}
    assert alloc.get("certified_diving") == 1
    assert alloc.get("minicourse") == 1


@pytest.mark.asyncio
async def test_companion_signal_post_close_adds_snorkel_item():
    """"hay un amigo que quiere hacer snorkel" tras el cierre — el regex no
    lo reconoce ('hay un amigo' no matchea _ADDED_PERSON_RE con posesivo);
    la señal LLM sí y el carrito debe quedar con AMBAS actividades."""
    state = make_state("es")
    await route_message(state, "soy buzo certificado, quiero bucear desde cartagena, voy solo")
    await route_message(state, "no")
    await route_message(state, "no soy colombiano")
    assert state.mixed_cart[0]["type"] == "cert"

    with patch.object(core, "detect_special_signals",
                       new=AsyncMock(return_value={"companion_activity": "snorkel", "companion_qty": 1})):
        resp = await route_message(state, "hay un amigo que quiere hacer snorkel")
    types = {it["type"]: it["qty"] for it in state.mixed_cart}
    assert types.get("cert") == 1, "el buceo original no puede perderse"
    assert types.get("snorkel") == 1
    assert "norkel" in resp


@pytest.mark.asyncio
async def test_no_signal_falls_through_to_generic_as_before():
    """Regresión: si detect_special_signals no encuentra nada (mensaje
    genuinamente ambiguo), el comportamiento sigue siendo el de antes — no se
    inventa ni una señal ni una respuesta."""
    state = make_state("es")
    state.core_pending_slot = core.SLOT_NATIONALITY
    with patch.object(core, "detect_special_signals", new=AsyncMock(return_value={})):
        resp = await route_message(state, "gracias por la ayuda")
    assert resp  # no crashea; sigue re-preguntando lo pendiente


@pytest.mark.asyncio
async def test_signal_detection_not_called_when_turn_already_advanced():
    """No se gasta la llamada de señales si el turno YA avanzó por el camino
    normal (regex/gap-fill) — solo es una red de precisión para el caso
    estancado."""
    state = make_state("es")
    signals_mock = AsyncMock(return_value={})
    with patch.object(core, "detect_special_signals", new=signals_mock):
        await route_message(state, "quiero hacer snorkel, somos 2, desde cartagena")
    signals_mock.assert_not_called()
