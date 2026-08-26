"""Tests del núcleo conversacional de slot-filling (docs/conversational-refactor-plan.md).

Todo offline: el gap-filler LLM se mockea (patch de conversational_core.fill_gaps)
y RAG usa el stub del conftest (supervisor.rag_answer). El núcleo es el único
camino de enrutado desde Fase 4.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents import conversational_core as core
from src.agents.supervisor import route_message
from src.flows.decision_tree import ConversationState, Step


def make_state(lang: str = "es") -> ConversationState:
    s = ConversationState(conversation_id="core-test")
    s.language = lang
    return s


@pytest.fixture(autouse=True)
def _core_on(monkeypatch):
    """Deja el gap-filler y el detector de señales (recordar/acompañante) en
    no-op por defecto para todos los tests de este módulo (cada test los
    re-mockea si necesita que el LLM 'decida' algo)."""
    monkeypatch.setattr(core, "fill_gaps", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "detect_special_signals", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "resolve_slot_answer", AsyncMock(return_value={}))


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
async def test_menu_keyword_handled_as_normal_message_by_core():
    """Fase 4 (decisión owner 2026-07-28): "menú"/"volver" ya NO resetean a un
    menú de botones — el núcleo los trata como mensaje normal (reconduce a la
    reserva). No hay reset a MAIN_MENU y el núcleo responde algo."""
    state = make_state("es")
    state.step = Step.FREE_TEXT
    resp = await route_message(state, "menu")
    assert state.step != Step.MAIN_MENU
    assert resp


@pytest.mark.asyncio
async def test_sensitive_medical_still_escalates_before_core():
    state = make_state("es")
    state.step = Step.MAIN_MENU
    await route_message(state, "estoy embarazada, ¿puedo bucear?")
    assert state.step == Step.ESCALATE


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
async def test_tengo_n_amigos_counts_once_not_double(monkeypatch):
    """Bug en vivo PRE (2026-07-23, Rocío): 'tengo el AOWD, además tengo 3
    amigos...' — la extracción base (regex, ya arreglado) resuelve group_size=4
    (ella + 3). El gate de acompañante NO debe volver a disparar la red de
    precisión LLM para el MISMO mensaje y sumar 3 otra vez (4+3=7). Se mockea
    detect_special_signals como si el LLM SÍ devolviera un acompañante: aun
    así, `group_composition_resolved_by_base_extraction` debe evitar el doble
    conteo, así que la señal ni se consume."""
    signals_mock = AsyncMock(return_value={
        "companion_activity": "certified_diving", "companion_qty": 3,
        "mentions_other_person": True,
    })
    monkeypatch.setattr(core, "detect_special_signals", signals_mock)
    state = make_state("es")
    # Falta la ubicación (el número "3" NO se consume como respuesta de ese
    # slot). La extracción base resuelve group_size=4 (regex 'tengo N amigos'),
    # lo que cuenta como avance aunque la ubicación siga pendiente — así la red
    # de precisión LLM no re-cuenta los 3 acompañantes encima (4+3=7).
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.core_pending_slot = core.SLOT_LOCATION
    await route_message(state, "tengo 3 amigos que quieren hacer alguna actividad")
    assert state.detected_group_size == 4, "ella + 3 amigos = 4, nunca 7"
    signals_mock.assert_not_called()


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


# ---------------------------------------------------------------------------
# Fase C (2026-07-23): red anti-BUCLE de slot. Los slots booleanos/escalares
# no debían quedarse re-preguntando para siempre ante una respuesta válida
# pero no-canónica ("uf, hace muchísimo" / "vivo en bogotá" / "un par"). El
# resolutor LLM (resolve_slot_answer) interpreta la respuesta y desatasca.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safety_non_canonical_answer_resolved_by_slot_resolver(monkeypatch):
    """"uf, hace muchísimo" no es is_affirmative/is_negative — sin la red se
    re-preguntaría la seguridad para siempre. El resolutor lo interpreta como
    'sí, >2 años' y el flujo avanza."""
    monkeypatch.setattr(core, "resolve_slot_answer", AsyncMock(return_value={"value": True}))
    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    state.detected_group_size = 1
    state.core_pending_slot = core.SLOT_SAFETY
    await route_message(state, "uf, hace muchísimo")
    assert state.last_dive_over_2_years is True
    assert state.core_pending_slot != core.SLOT_SAFETY


@pytest.mark.asyncio
async def test_nationality_resident_answer_resolved_by_slot_resolver(monkeypatch):
    """"vivo en bogotá" implica residente en Colombia — sin la red quedaba en
    bucle (no lo cazaba is_affirmative). El resolutor lo resuelve a True."""
    monkeypatch.setattr(core, "resolve_slot_answer", AsyncMock(return_value={"value": True}))
    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    state.detected_group_size = 1
    state.last_dive_over_2_years = False
    state.core_pending_slot = core.SLOT_NATIONALITY
    await route_message(state, "vivo en bogotá")
    assert state.is_colombian is True


@pytest.mark.asyncio
async def test_qty_un_par_resolved_by_slot_resolver(monkeypatch):
    """"un par" = 2, que _parse_mixed_quantity no reconoce. El resolutor lo
    resuelve y el flujo no se queda pidiendo cantidad."""
    monkeypatch.setattr(core, "resolve_slot_answer", AsyncMock(return_value={"value": 2}))
    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    state.last_dive_over_2_years = False
    state.core_pending_slot = core.SLOT_QTY
    await route_message(state, "un par")
    assert state.detected_group_size == 2


@pytest.mark.asyncio
async def test_slot_resolver_abstains_no_infinite_state_change(monkeypatch):
    """Si el resolutor se abstiene ({}), el slot NO cambia y se re-pregunta —
    igual que antes, nunca peor (no se inventa un valor)."""
    resolver = AsyncMock(return_value={})
    monkeypatch.setattr(core, "resolve_slot_answer", resolver)
    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    state.detected_group_size = 1
    state.core_pending_slot = core.SLOT_SAFETY
    await route_message(state, "bla bla bla")
    resolver.assert_awaited()  # se intentó
    assert state.last_dive_over_2_years is None  # pero no se inventó nada
    assert state.core_pending_slot == core.SLOT_SAFETY


@pytest.mark.asyncio
async def test_hotel_dont_know_stored_as_marker_not_verbatim():
    """"no sé todavía" al preguntar el hotel NO se guarda como nombre de hotel;
    se guarda un marcador claro y el flujo avanza (no bucle, no basura)."""
    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "island"
    state.core_pending_slot = core.SLOT_HOTEL
    await route_message(state, "no sé todavía")
    assert state.hotel == "por confirmar"
    assert state.core_pending_slot != core.SLOT_HOTEL


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


# ---------------------------------------------------------------------------
# Auditoría 2026-07-22: refresher_interested sin respaldo LLM (riesgo de
# bucle) + recall_field ampliado (edades/hotel/seguridad/refresher).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresher_unusual_phrasing_resolved_by_signal_not_stuck_forever():
    """"sí, no estaría mal" no matchea is_affirmative — sin respaldo LLM el
    bot se quedaría preguntando el refresher para siempre. Con la señal
    ampliada, se resuelve y avanza."""
    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    state.detected_group_size = 1
    state.last_dive_over_2_years = True
    state.core_pending_slot = core.SLOT_REFRESHER
    with patch.object(core, "detect_special_signals",
                       new=AsyncMock(return_value={"refresher_interested": True})):
        await route_message(state, "sí, no estaría mal")
    assert state.refresher_interested is True
    assert state.core_pending_slot != core.SLOT_REFRESHER


@pytest.mark.asyncio
async def test_recall_ages_answers_from_state():
    state = make_state("es")
    state.detected_ages = [7, 9]
    state.core_pending_slot = core.SLOT_NATIONALITY
    with patch.object(core, "detect_special_signals", new=AsyncMock(return_value={"recall_field": "ages"})):
        resp = await route_message(state, "que edades te dije que tenian los niños?")
    assert "7" in resp and "9" in resp


@pytest.mark.asyncio
async def test_recall_hotel_answers_from_state():
    state = make_state("es")
    state.location = "island"
    state.hotel = "Hotel Coco Liso"
    state.core_pending_slot = core.SLOT_NATIONALITY
    with patch.object(core, "detect_special_signals", new=AsyncMock(return_value={"recall_field": "hotel"})):
        resp = await route_message(state, "en que hotel dije que estaba?")
    assert "Coco Liso" in resp


@pytest.mark.asyncio
async def test_recall_refresher_field_not_yet_known_falls_back():
    """Si el LLM pide recordar el refresher pero el estado no lo tiene
    resuelto de verdad, no se inventa — cae a RAG."""
    state = make_state("es")
    with patch.object(core, "detect_special_signals", new=AsyncMock(return_value={"recall_field": "refresher_interested"})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(return_value="Respuesta RAG")):
        resp = await route_message(state, "el refresher lo quería o no?")
    assert "Respuesta RAG" in resp


# ── Nombre del cliente desde el mensaje + acuse cálido (2026-07-22) ───────────

@pytest.mark.parametrize("msg,expected", [
    ("hola soy rocio, quiero hacer buceo, tengo el AOWD", "Rocio"),
    ("me llamo Ana y quiero snorkel", "Ana"),
    ("mi nombre es Carlos", "Carlos"),
    ("my name is John", "John"),
    ("soy certificado", None),          # atributo, no nombre
    ("soy colombiano", None),
    ("soy buzo open water", None),
    ("quiero bucear", None),
])
def test_capture_client_name(msg, expected):
    st = ConversationState(conversation_id="name")
    core._capture_client_name(st, msg)
    assert st.client_name == expected


def test_capture_client_name_first_wins():
    st = ConversationState(conversation_id="name2")
    core._capture_client_name(st, "soy Rocio")
    core._capture_client_name(st, "en realidad soy Ana")
    assert st.client_name == "Rocio"


def _fake_openai(text):
    from unittest.mock import MagicMock
    client = MagicMock()
    msg = MagicMock(); msg.content = text
    choice = MagicMock(); choice.message = msg
    resp = MagicMock(); resp.choices = [choice]
    client.chat.completions.create = AsyncMock(return_value=resp)
    return client


@pytest.mark.asyncio
async def test_ack_backstop_drops_price_link_or_question():
    from src.agents.llm_extractor import compose_acknowledgement
    # El redactor NUNCA debe colar precio, link ni pregunta (datos duros van aparte).
    assert await compose_acknowledgement("añade snorkel", client=_fake_openai("¡Genial! Son $140.")) == ""
    assert await compose_acknowledgement("x", client=_fake_openai("Mira https://book.divingplanet.org")) == ""
    assert await compose_acknowledgement("x", client=_fake_openai("¿Cuántos sois?")) == ""


@pytest.mark.asyncio
async def test_ack_passes_a_warm_sentence():
    from src.agents.llm_extractor import compose_acknowledgement
    assert await compose_acknowledgement("desde cartagena", client=_fake_openai("¡Qué alegría, Rocío!")) == "¡Qué alegría, Rocío!"


@pytest.mark.asyncio
async def test_ack_empty_message_no_call():
    from src.agents.llm_extractor import compose_acknowledgement
    assert await compose_acknowledgement("") == ""


@pytest.mark.parametrize("msg,expected", [
    # Acompañante (persona nombrada) -> True
    ("hay un amigo que quiere hacee snorkel", True),
    ("2 y uno hace snorkel", True),
    ("también viene mi primo a bucear", True),
    ("viene mi novia", True),
    ("y otra para snorkel", True),
    # Cambio de opinión (sin persona) -> False (nunca añade acompañante)
    ("mejor snorkel", False),
    ("en realidad quiero snorkel", False),
    ("mejor multi-día", False),
    ("solo yo", False),
    ("quiero bucear", False),
])
def test_mentions_person_discriminates_companion_from_change(msg, expected):
    assert core._mentions_person(msg) is expected


def test_full_booking_recap_lists_all_activities_and_location():
    st = ConversationState(conversation_id="recap"); st.language = "es"
    st.client_name = "Rocio"
    st.detected_group_allocation = {"certified_diving": 1, "snorkel": 1}
    st.location = "cartagena"
    r = core._full_booking_recap(st)
    assert r and "buceo certificado" in r and "snorkel" in r
    assert "Cartagena" in r and "Rocio" in r


def test_full_booking_recap_none_when_nothing_resolved():
    st = ConversationState(conversation_id="recap2"); st.language = "es"
    assert core._full_booking_recap(st) is None


# ---------------------------------------------------------------------------
# Recall rico end-to-end (Prioridad 2, punto 1 — pendiente del handoff de
# Álvaro: "_full_booking_recap existe, falta validar vía maybe_handle_turn").
# Verificado en vivo con LLM real antes de escribir estos tests (temp+audit
# 2026-07-23): 7 frases regionales ("qué llevamos hasta ahora", "recapitulemos",
# "che, decime de nuevo qué habíamos armado", "parce recuérdame que llevamos"...)
# clasifican bien como booking_recap; el recap en frío (nada resuelto) cae a
# RAG sin romperse; una pregunta de RECOMENDACIÓN pura ("y tú qué recomiendas
# para nosotros?") no se secuestra como recall. Un caso límite SÍ mostró
# variabilidad con un historial artificial recortado (misclasificó como
# recall_field=group_size en vez de responder la recomendación) — no se
# reprodujo con el historial real completo del pipeline; documentado como
# riesgo de baja severidad en docs/conversational-refactor-handoff.md.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_booking_recap_end_to_end_via_route_message():
    """El camino completo: señal LLM -> _recall_answer -> _full_booking_recap,
    con recap correcto Y re-pregunta del slot pendiente en el mismo turno."""
    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    state.detected_group_size = 3
    state.core_pending_slot = core.SLOT_SAFETY
    with patch.object(core, "detect_special_signals",
                       new=AsyncMock(return_value={"recall_field": "booking_recap"})):
        resp = await route_message(state, "¿qué llevamos hasta ahora?")
    assert "3" in resp and ("buceo" in resp.lower() or "certificado" in resp.lower())
    assert "2 años" in resp or "2 anos" in resp  # re-pregunta lo pendiente en el MISMO turno
    assert state.core_pending_slot == core.SLOT_SAFETY


@pytest.mark.asyncio
async def test_booking_recap_mixed_group_lists_every_activity():
    state = make_state("es")
    state.detected_group_allocation = {"certified_diving": 2, "snorkel": 1}
    state.detected_group_size = 3
    state.location = "cartagena"
    state.core_pending_slot = core.SLOT_NATIONALITY
    with patch.object(core, "detect_special_signals",
                       new=AsyncMock(return_value={"recall_field": "booking_recap"})):
        resp = await route_message(state, "a ver, recapitulemos, en que quedamos")
    assert "snorkel" in resp.lower() and ("certificado" in resp.lower() or "buceo" in resp.lower())


@pytest.mark.asyncio
async def test_booking_recap_cold_start_falls_back_to_rag_without_crashing():
    """Pedir el recap sin nada resuelto todavía (primer mensaje) — el estado no
    tiene nada real que recordar, así que debe caer a RAG limpio, nunca
    inventar un resumen ni romperse."""
    state = make_state("es")
    with patch.object(core, "detect_special_signals",
                       new=AsyncMock(return_value={"recall_field": "booking_recap"})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(return_value="Respuesta RAG")):
        resp = await route_message(state, "¿qué te había pedido?")
    assert "Respuesta RAG" in resp


@pytest.mark.asyncio
async def test_recommendation_question_not_hijacked_by_recall_signal():
    """Regresión del hallazgo de la auditoría: una pregunta de RECOMENDACIÓN
    pura no debe tratarse como un pedido de recordar, aunque el LLM real
    mostró variabilidad en un caso límite con historial artificial recortado."""
    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    state.detected_group_size = 3
    state.core_pending_slot = core.SLOT_SAFETY
    with patch.object(core, "detect_special_signals", new=AsyncMock(return_value={})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(return_value="Respuesta RAG")):
        resp = await route_message(state, "y tu que recomiendas para nosotros?")
    assert "Respuesta RAG" in resp


# ---------------------------------------------------------------------------
# Multi-ítem: other_companions con cola de preguntas (auditoría 2026-07-23).
# Medido con matriz de 9 casos x 4 repeticiones que el LLM NUNCA se abstiene
# de forma fiable ante un plural vago en other_companions (con y sin refuerzo
# de prompt) — mismo criterio determinista de _EXPLICIT_NUMBER_RE ya usado
# para el sub-grupo principal, extendido a cada item adicional: si su
# cantidad no tiene un número real en el texto, se pregunta, nunca se asume.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_three_activities_all_explicit_merge_without_asking():
    """"somos 2 que bucean y 3 que hacen snorkel" — los 2 números son reales
    (caso A de la matriz medida, 100% fiable en vivo) — se fusionan sin
    preguntar nada. fill_gaps mockeado a {} para aislar el camino de la señal
    (detect_special_signals), sin interferencia del extractor principal."""
    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    state.detected_group_size = 2
    state.last_dive_over_2_years = False
    state.core_pending_slot = core.SLOT_NATIONALITY
    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={})), \
         patch.object(core, "detect_special_signals", new=AsyncMock(return_value={
        "companion_activity": "snorkel", "companion_qty": 3,
        "mentions_other_person": True,
    })):
        resp = await route_message(state, "somos 2 que bucean y 3 que hacen snorkel")
    alloc = state.detected_group_allocation
    assert alloc.get("certified_diving") == 2
    assert alloc.get("snorkel") == 3
    assert state.core_pending_slot == core.SLOT_NATIONALITY  # no se quedó preguntando cantidad
    assert resp


@pytest.mark.asyncio
async def test_vague_plural_in_other_companions_asks_instead_of_guessing():
    """Verificado en vivo (auditoría 2026-07-23, caso D de la matriz), mensaje
    de apertura describiendo el grupo mixto de una vez: "2 bucean, mis amigos
    hacen snorkel, y uno hace el minicurso". El sub-grupo de snorkel es un
    plural vago sin número real — aunque fill_gaps (el extractor principal,
    NO la señal de acompañante) invente snorkel=2, el guard de
    group_allocation debe descartar esa entrada concreta y preguntar, sin
    perder las otras dos (respaldadas por "2" y "uno" reales)."""
    state = make_state("es")
    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={
        "group_allocation": {"certified_diving": 2, "minicourse": 1, "snorkel": 2},
        "group_size": 5, "is_certified": True,
    })), \
         patch.object(core, "detect_special_signals", new=AsyncMock(return_value={})):
        resp = await route_message(state, "2 bucean, mis amigos hacen snorkel, y uno hace el minicurso")
    assert state.core_pending_slot == core.SLOT_COMPANION_QTY
    assert state.pending_companion_activity == "snorkel"
    assert "snorkel" in resp.lower()
    # El principal (respaldado por "2") y el minicurso (respaldado por "uno")
    # SÍ se fusionaron; solo snorkel (sin número real propio) queda pendiente.
    alloc = state.detected_group_allocation or {}
    assert alloc.get("certified_diving") == 2
    assert alloc.get("minicourse") == 1
    assert "snorkel" not in alloc


@pytest.mark.asyncio
async def test_vague_plural_in_other_companions_then_answer_completes_booking():
    """Continuación del test anterior: al responder la cantidad preguntada,
    se fusiona y el carrito final queda con las 3 actividades, ninguna
    perdida ni inventada."""
    state = make_state("es")
    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={
        "group_allocation": {"certified_diving": 2, "minicourse": 1, "snorkel": 2},
        "group_size": 5, "is_certified": True,
    })), \
         patch.object(core, "detect_special_signals", new=AsyncMock(return_value={})):
        await route_message(state, "2 bucean, mis amigos hacen snorkel, y uno hace el minicurso")
    assert state.core_pending_slot == core.SLOT_COMPANION_QTY

    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={})), \
         patch.object(core, "detect_special_signals", new=AsyncMock(return_value={})):
        await route_message(state, "4")
    alloc = state.detected_group_allocation
    assert alloc.get("certified_diving") == 2
    assert alloc.get("minicourse") == 1
    assert alloc.get("snorkel") == 4
    assert state.core_pending_slot != core.SLOT_COMPANION_QTY  # avanzó, no se quedó preguntando


@pytest.mark.asyncio
async def test_other_companions_post_close_asks_before_adding_unconfirmed_item():
    """Tras el cierre, un mensaje con un sub-grupo nuevo confirmado (snorkel,
    con número real) y otro sin respaldo (minicurso, "otro" no es un número)
    — el confirmado se registra pero el carrito NO se toca todavía: primero
    se pregunta el que falta, nunca se factura una cantidad inventada."""
    state = make_state("es")
    await route_message(state, "soy buzo certificado, quiero bucear desde cartagena, voy solo")
    await route_message(state, "no")
    await route_message(state, "no soy colombiano")
    assert state.mixed_cart[0]["type"] == "cert"

    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={})), \
         patch.object(core, "detect_special_signals", new=AsyncMock(return_value={
        "companion_activity": "snorkel", "companion_qty": 2,
        "mentions_other_person": True,
        "other_companions": [{"activity": "minicourse", "qty": 1}],  # "otro" no es un número real
    })):
        resp = await route_message(state, "2 amigos hacen snorkel y otro el minicurso")
    # El carrito original nunca se pierde; el nuevo ítem sin confirmar (minicurso)
    # no se añade todavía — se pregunta primero.
    types = {it["type"]: it["qty"] for it in state.mixed_cart}
    assert types.get("cert") == 1, "el buceo original no puede perderse"
    assert "beginner" not in types, "no se factura una cantidad inventada"
    assert state.core_pending_slot == core.SLOT_COMPANION_QTY
    assert state.pending_companion_activity == "minicourse"
    assert "minicurso" in resp.lower() or "minicourse" in resp.lower()

    # Al responder, el carrito se cierra con AMBAS actividades nuevas.
    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={})), \
         patch.object(core, "detect_special_signals", new=AsyncMock(return_value={})):
        resp2 = await route_message(state, "1")
    types2 = {it["type"]: it["qty"] for it in state.mixed_cart}
    assert types2.get("cert") == 1
    assert types2.get("snorkel") == 2
    assert types2.get("beginner") == 1
    assert "norkel" in resp2


@pytest.mark.asyncio
async def test_correctly_abstained_activity_is_not_silently_lost():
    """Hallazgo en vivo 2026-07-23: "tres bucean, mis amigos hacen snorkel, y
    dos hacen el minicurso" hace que fill_gaps se ABSTENGA correctamente de
    "snorkel" (no incluye la clave en absoluto, tal y como se le pide ante un
    plural sin número propio) — pero eso significaba que la mención se perdía
    en silencio, sin preguntar nunca. La red debe detectar que el texto
    menciona "snorkel" y no aparece en ningún sitio del estado, y preguntar."""
    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.core_pending_slot = core.SLOT_LOCATION

    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={
        "group_size": 5,
        "group_allocation": {"certified_diving": 3, "minicourse": 2},
    })):
        resp = await route_message(
            state, "tres bucean, mis amigos hacen snorkel, y dos hacen el minicurso"
        )

    assert state.detected_group_allocation.get("certified_diving") == 3
    assert state.detected_group_allocation.get("minicourse") == 2
    assert "snorkel" not in state.detected_group_allocation, (
        "snorkel no debe aparecer con una cantidad inventada"
    )
    assert state.core_pending_slot == core.SLOT_COMPANION_QTY
    assert state.pending_companion_activity == "snorkel"
    assert "norkel" in resp.lower()

    # Al responder con el número real, snorkel se registra sin inventar nada.
    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={})), \
         patch.object(core, "detect_special_signals", new=AsyncMock(return_value={})):
        await route_message(state, "somos 2 para snorkel")
    assert state.detected_group_allocation.get("snorkel") == 2
    assert not state.pending_companion_queue


@pytest.mark.asyncio
async def test_hallucinated_main_activity_restatement_is_not_queued_as_companion():
    """Hallazgo en vivo 2026-07-23 (regresión detectada al verificar el fix
    anterior): en un turno MID-FLOW de "añadir acompañante singular"
    ("viene también un amigo que quiere hacer snorkel", tras una reserva de
    buceo certificado ya cerrada), fill_gaps puede alucinar un
    group_allocation COMPLETO sin ningún número real en el texto
    ({certified_diving:1, snorkel:1}) — ninguna de las dos cantidades tiene
    respaldo, así que ambas se descartan. Sin el fix, la actividad PRINCIPAL
    ya confirmada (certified_diving) se encolaba igual que si fuera un
    acompañante nuevo, y el bot preguntaba "¿Cuántos serían para buceo
    certificado?" — sin sentido, además de pisar la resolución correcta del
    fast-path regex (compañero singular inequívoco "un amigo" -> snorkel:1
    sin preguntar)."""
    state = make_state("es")
    await route_message(state, "soy buzo certificado, quiero bucear desde cartagena, voy solo")
    await route_message(state, "no")
    await route_message(state, "no soy colombiano")
    assert state.mixed_cart[0]["type"] == "cert"

    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={
        "group_allocation": {"certified_diving": 1, "snorkel": 1},
    })):
        resp = await route_message(state, "viene también un amigo que quiere hacer snorkel")

    assert "certificado" not in resp.lower(), (
        "no debe re-preguntar por la actividad principal ya confirmada"
    )
    types = {it["type"]: it["qty"] for it in state.mixed_cart}
    assert types.get("cert") == 1
    assert types.get("snorkel") == 1, (
        "el compañero singular inequívoco se resuelve sin preguntar (qty=1)"
    )
    assert state.core_pending_slot != core.SLOT_COMPANION_QTY
    assert not state.pending_companion_queue


def test_mentions_person_recognizes_english_plurals():
    """Hallazgo en vivo 2026-07-23 (matriz EN de multi-ítem): la lista de
    `_MENTIONS_PERSON_RE` en inglés no tenía plurales ("friend" sin "s?"),
    mientras que TODA la lista en español sí los tiene ("amig[oa]s?") — "my
    friends do snorkel" no disparaba NINGÚN mecanismo de acompañante en
    inglés (ni el chequeo de mención perdida, ni el gate original
    `companion_ambiguous`, ni el fast-path), un hueco real de idioma."""
    assert core._mentions_person("my friends do snorkel")
    assert core._mentions_person("2 brothers and my sisters are coming")
    assert core._mentions_person("some folks want to join")
    assert not core._mentions_person("I want to do snorkel")


@pytest.mark.asyncio
async def test_companion_qty_answer_mentioning_different_activity_not_misapplied():
    """Hallazgo en vivo 2026-07-23: si se pregunta "¿cuántos para snorkel?"
    y la respuesta menciona OTRA actividad producto distinta ("we are 3 for
    diving"), ese número NO es una respuesta válida para snorkel — aplicarlo
    a ciegas mezclaría el "3" de buceo con snorkel (bug en vivo: snorkel
    acababa con qty=3 cuando el cliente hablaba de buceo). Además, la
    pregunta de snorkel (aún sin responder) no debe perderse: el turno
    después debe seguir preguntando por snorkel, no saltar a otro slot."""
    state = make_state("en")
    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={
        "group_allocation": {"certified_diving": 1, "snorkel": 1},
    })):
        await route_message(state, "my friends dive and other friends do snorkel too")
    assert state.core_pending_slot == core.SLOT_COMPANION_QTY
    pending_before = state.pending_companion_activity
    assert pending_before in ("certified_diving", "snorkel")
    snorkel_before = (state.detected_group_allocation or {}).get("snorkel")

    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={
        "group_allocation": {"certified_diving": 3},
    })):
        resp = await route_message(state, "we are 3 for diving")

    assert (state.detected_group_allocation or {}).get("snorkel") == snorkel_before, (
        "el número de buceo no puede colarse como cantidad de snorkel"
    )
    # La pregunta original (la que sea que quedó pendiente) sigue viva, no
    # se pierde silenciosamente por caer al slot genérico siguiente.
    assert state.core_pending_slot == core.SLOT_COMPANION_QTY
    assert state.pending_companion_activity is not None
    assert "snorkel" in resp.lower() or "buce" in resp.lower() or "div" in resp.lower()


@pytest.mark.asyncio
async def test_companion_attribute_without_activity_asks_instead_of_guessing():
    """Hallazgo en vivo 2026-07-23: "mi amigo no está certificado" da un
    ATRIBUTO del acompañante (certificación) pero ninguna actividad ni
    intención declarada. Dos extractores distintos (fill_gaps y
    detect_special_signals) adivinaban actividades DISTINTAS para la MISMA
    frase ambigua (snorkel vs. minicurso) — reforzar el prompt para que se
    abstuviera no funcionó (medido 3/3 sigue adivinando). Fix determinista:
    se pregunta qué le gustaría hacer al acompañante en vez de adivinar."""
    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    state.detected_group_size = 1
    state.last_dive_over_2_years = False
    state.is_colombian = False
    state.core_pending_slot = None
    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={})), \
         patch.object(core, "detect_special_signals", new=AsyncMock(return_value={
             "companion_activity": "minicourse", "mentions_other_person": True,
             "companion_is_singular": False,
         })):
        resp = await route_message(state, "mi amigo no esta certificado")
    assert state.core_pending_slot == core.SLOT_COMPANION_ACTIVITY
    assert not (state.detected_group_allocation or {}).get("minicourse"), (
        "no se debe adivinar minicurso sin que el texto lo respalde"
    )
    assert not (state.detected_group_allocation or {}).get("snorkel")
    assert "?" in resp

    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={})), \
         patch.object(core, "detect_special_signals", new=AsyncMock(return_value={})):
        resp2 = await route_message(state, "snorkel")
    assert state.core_pending_slot == core.SLOT_COMPANION_QTY
    assert state.pending_companion_activity == "snorkel"
    assert "snorkel" in resp2.lower()


def test_activity_has_textual_backing_translates_diving_intent_to_minicourse():
    """La regla de negocio "no certificado + quiere bucear -> minicurso" debe
    seguir contando como respaldo textual válido para `minicourse` (no es
    una alucinación, es una traducción de negocio) — pero un mensaje que NO
    menciona ninguna actividad no respalda nada."""
    assert core._activity_has_textual_backing("minicourse", "quiere hacer buceo")
    assert core._activity_has_textual_backing("snorkel", "quiere hacer snorkel")
    assert not core._activity_has_textual_backing("minicourse", "mi amigo no esta certificado")


@pytest.mark.asyncio
async def test_companion_activity_ambiguity_defers_instead_of_burying_pending_slot():
    """Hallazgo en vivo 2026-08-26 (batería sintética contra PRE, conv 190 y
    210): cuando la ambigüedad de actividad del acompañante aparecía MIENTRAS
    todavía había una pregunta obligatoria pendiente (seguridad, en este
    caso), el bot la enterraba para siempre — interrumpía con "¿qué le
    gustaría hacer a tu acompañante?" y nunca volvía a preguntar por la
    seguridad, quedándose incluso en BUCLE repitiendo la pregunta del
    acompañante ante cualquier respuesta corta ("no", "no somos
    colombianos") que en realidad respondía a otra cosa. Ahora se difiere: se
    sigue preguntando lo que tocaba (seguridad), y el acompañante se retoma
    justo antes de cerrar, sin perderse ni bloquear nada por el medio."""
    state = make_state("es")
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.location = "cartagena"
    state.detected_group_size = 1
    state.core_pending_slot = core.SLOT_SAFETY

    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={})), \
         patch.object(core, "detect_special_signals", new=AsyncMock(return_value={
             "companion_activity": "minicourse", "mentions_other_person": True,
             "companion_is_singular": False, "companion_qty": 2,
         })):
        resp = await route_message(state, "mis amigos tambien vienen")
    # La ambigüedad del acompañante NO se pierde (se difiere), pero tampoco
    # entierra la pregunta de seguridad que ya estaba pendiente.
    assert state.core_pending_slot == core.SLOT_SAFETY
    assert state.companion_activity_deferred is True
    assert "año" in resp.lower() or "inmersión" in resp.lower() or "immersion" in resp.lower()

    # Resolver seguridad y nacionalidad — el bot debe seguir preguntando por
    # ELLAS, nunca volver a la ambigüedad del acompañante a mitad de camino.
    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={})), \
         patch.object(core, "detect_special_signals", new=AsyncMock(return_value={})):
        resp2 = await route_message(state, "no")
    assert state.last_dive_over_2_years is False
    assert state.core_pending_slot != core.SLOT_COMPANION_ACTIVITY

    with patch.object(core, "fill_gaps", new=AsyncMock(return_value={})), \
         patch.object(core, "detect_special_signals", new=AsyncMock(return_value={})):
        resp3 = await route_message(state, "no somos colombianos")
    assert state.is_colombian is False
    # Ahora que ya no queda nada más pendiente, se retoma el acompañante.
    assert state.core_pending_slot == core.SLOT_COMPANION_ACTIVITY
    assert state.companion_activity_deferred is False
    assert "acompañante" in resp3.lower() or "?" in resp3


# ---------------------------------------------------------------------------
# B2: deliberación entre actividades ("duda entre X y Y") → RAG, no reserva
# ---------------------------------------------------------------------------

def _at_activity_stage(lang: str = "es") -> ConversationState:
    """Estado justo tras el saludo: se preguntó la actividad, nada elegido."""
    state = make_state(lang)
    state.step = Step.FREE_TEXT
    state.core_pending_slot = core.SLOT_ACTIVITY
    return state


@pytest.mark.asyncio
async def test_comparing_options_object_routes_to_rag_not_cart():
    """El fallo en vivo: "mi pareja duda entre buceo y minicurso" (sin "?")
    se tomaba como reserva de AMBAS actividades. Con la señal objeto
    comparing_options debe ir a RAG (explicar) y NO construir carrito ni
    encolar cantidades de acompañante."""
    state = _at_activity_stage()
    obj = {"comparing_options": {
        "comparing": True,
        "options": ["certified_diving", "minicourse"],
        "who": "companion",
    }}
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value=obj)), \
         patch("src.agents.supervisor.rag_answer",
               new=AsyncMock(return_value="RAG_DIFERENCIA")) as rag:
        resp = await route_message(state, "vale y mi pareja duda entre buceo y minicurso")
    rag.assert_awaited_once()
    assert "RAG_DIFERENCIA" in resp
    assert not state.mixed_cart
    assert not state.pending_companion_queue
    assert state.detected_activity is None


@pytest.mark.asyncio
async def test_deliberation_backstop_without_llm_signal_routes_to_rag():
    """Aunque la señal LLM no marque nada ({}), el backstop determinista de
    frases de duda ("no sé si … o …") debe enrutar a RAG igual — sin depender
    del "?" (que es lo único que hoy lo salva)."""
    state = _at_activity_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})), \
         patch("src.agents.supervisor.rag_answer",
               new=AsyncMock(return_value="RAG_DIFERENCIA")) as rag:
        resp = await route_message(state, "no sé si hacer snorkel o el minicurso")
    rag.assert_awaited_once()
    assert "RAG_DIFERENCIA" in resp
    assert not state.mixed_cart
    assert state.detected_activity is None


@pytest.mark.asyncio
async def test_single_activity_selection_not_treated_as_comparing():
    """Guard contra falso positivo: una selección clara de UNA sola actividad
    ("quiero el minicurso") NO es deliberación aunque la señal LLM se equivoque
    y diga comparing=True — se necesita mencionar 2+ productos en el texto."""
    state = _at_activity_stage()
    obj = {"comparing_options": {"comparing": True, "options": ["minicourse"],
                                 "who": "self"}}
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value=obj)), \
         patch("src.agents.supervisor.rag_answer",
               new=AsyncMock(side_effect=AssertionError("no debe ir a RAG"))):
        await route_message(state, "quiero el minicurso")
    assert state.detected_activity == "minicourse"


def test_deliberation_backstop_patterns():
    assert core._looks_like_deliberation("mi pareja duda entre buceo y minicurso")
    assert core._looks_like_deliberation("no sé si snorkel o el minicurso")
    assert core._looks_like_deliberation("qué diferencia hay entre snorkel y buceo")
    assert core._looks_like_deliberation("not sure whether to snorkel or dive")
    # Una selección o pregunta normal NO es deliberación.
    assert not core._looks_like_deliberation("quiero el minicurso")
    assert not core._looks_like_deliberation("cuánto cuesta el snorkel")


# ---------------------------------------------------------------------------
# B2 exhaustivo: matriz de variantes del predicado de deliberación
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message, signals, expected", [
    # actividad vs actividad
    ("mi pareja duda entre buceo y minicurso", {}, True),
    ("no sé si hacer snorkel o el minicurso", {}, True),
    # 3+ actividades
    ("no sé si buceo, snorkel o minicurso", {}, True),
    # curso vs curso (gap cerrado: el detector de productos no los distinguía)
    ("no sé si el open water o el advanced", {}, True),
    ("dudo entre open water y rescue", {}, True),
    # actividad vs curso
    ("dudo entre el minicurso o el curso open water", {}, True),
    # "quiero saber si X o Y" es PREGUNTA pese al "quiero"
    ("quiero saber si buceo o snorkel", {}, True),
    ("no me decido entre buceo y snorkel", {}, True),
    # inglés
    ("not sure whether to snorkel or dive", {}, True),
    ("should i do the open water or the advanced", {}, True),
    # señal LLM sin patrón determinista, 2 ofertas, sin compromiso
    ("mi pareja se lo está pensando, buceo y snorkel",
     {"comparing_options": {"comparing": True}}, True),
    # --- NO deliberación ---
    # una sola actividad (aunque el LLM se equivoque y diga comparing)
    ("quiero el minicurso", {"comparing_options": {"comparing": True}}, False),
    # selección real doble (sin duda, sin señal LLM)
    ("quiero buceo y snorkel para los dos", {}, False),
    # selección real doble + LLM sobre-dispara → commitment lo anula
    ("quiero buceo y snorkel", {"comparing_options": {"comparing": True}}, False),
    # duda de SLOT (ubicación) — no hay 2 ofertas de producto, no se toca
    ("no sé si cartagena o las islas", {}, False),
])
def test_is_deliberation_between_options_matrix(message, signals, expected):
    assert core._is_deliberation_between_options(message, signals) is expected


def test_mentioned_offerings_includes_courses_and_dedupes():
    assert core._mentioned_offerings("open water o advanced") == ["open_water", "advanced"]
    assert core._mentioned_offerings("snorkel o buceo") == ["certified_diving", "snorkel"] \
        or set(core._mentioned_offerings("snorkel o buceo")) == {"certified_diving", "snorkel"}
    assert core._mentioned_offerings("no sé si cartagena o islas") == []


@pytest.mark.asyncio
async def test_course_vs_course_deliberation_routes_to_rag_without_qmark():
    """Gap cerrado: duda entre DOS cursos concretos sin "?" ya no cae a
    extracción — va a RAG con una query de comparación explícita."""
    state = _at_activity_stage()
    captured = {}

    async def _fake_rag(query, **kwargs):
        captured["query"] = query
        return "RAG_CURSOS"

    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})), \
         patch("src.agents.supervisor.rag_answer", new=_fake_rag):
        resp = await route_message(state, "no sé si el open water o el advanced")
    assert "RAG_CURSOS" in resp
    assert not state.mixed_cart
    # La query reescrita nombra ambos cursos (recupera bien en RAG).
    assert "Open Water" in captured["query"] and "Advanced" in captured["query"]


# ---------------------------------------------------------------------------
# Composer determinista de comparación (fallback cuando el KB no tiene el par)
# ---------------------------------------------------------------------------

def test_compose_comparison_uses_catalog_facts():
    out = core._compose_comparison(["certified_diving", "snorkel"], "es")
    # Nombres del catálogo + requisito de cert + precio (nunca inventado).
    assert "Snorkel" in out
    assert "Sin certificación previa" in out and "Requiere certificación previa" in out
    assert "U$" in out
    # Cierra invitando a elegir, NO ofreciendo asesor.
    assert "asesor" not in out.lower()
    assert "con cuál te animas" in out.lower()


@pytest.mark.asyncio
async def test_deliberation_falls_back_to_catalog_when_rag_has_no_pair():
    """Par que el KB no compara ("buceo vs snorkel"): RAG devuelve su fallback
    de asesor → se sustituye por la comparación del catálogo, sin asesor."""
    from src.agents.rag_agent import FALLBACK_ES
    state = _at_activity_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(return_value=FALLBACK_ES)):
        resp = await route_message(state, "no sé si buceo o snorkel")
    assert "no lo tengo a la mano" not in resp  # ya no cae al asesor
    assert "Snorkel" in resp and "U$" in resp
    assert not state.mixed_cart


@pytest.mark.asyncio
async def test_deliberation_keeps_rag_answer_when_kb_has_the_pair():
    """Si RAG SÍ responde (KB tiene el par, p.ej. open water vs advanced), se
    conserva su respuesta rica — el composer solo actúa como fallback."""
    state = _at_activity_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})), \
         patch("src.agents.supervisor.rag_answer",
               new=AsyncMock(return_value="RAG_RICA: open water vs advanced. ¿Cuál prefieres?")):
        resp = await route_message(state, "no sé si el open water o el advanced")
    assert "RAG_RICA" in resp


# ---------------------------------------------------------------------------
# A2: no duplicar el menú tras una respuesta que ya termina en pregunta
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rag_answer_that_already_asks_does_not_reappend_activity_menu():
    """Fallo estético: tras recomendar/comparar, RAG ya cierra con su propia
    pregunta y encima se pegaba el menú entero de 4 bullets. Si la respuesta
    ya termina en pregunta, no se re-adjunta nada."""
    state = _at_activity_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})), \
         patch("src.agents.supervisor.rag_answer",
               new=AsyncMock(return_value="Aquí la diferencia. ¿Te inclinas por alguna?")):
        resp = await route_message(state, "qué diferencia hay entre snorkel y minicurso")
    assert "¿Te inclinas por alguna?" in resp
    assert "qué te gustaría vivir con nosotros" not in resp.lower()


@pytest.mark.asyncio
async def test_activity_reask_after_rag_uses_short_variant():
    """Cuando la respuesta RAG NO termina en pregunta, se re-ancla la
    actividad — pero con la variante corta de una línea, no el bloque de 4
    bullets."""
    state = _at_activity_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})), \
         patch("src.agents.supervisor.rag_answer",
               new=AsyncMock(return_value="Salimos todos los días desde Cartagena.")):
        resp = await route_message(state, "cuánto cuesta todo esto")
    assert "qué te gustaría vivir con nosotros" not in resp.lower()
    assert "con cuál te animas" in resp.lower()


# ---------------------------------------------------------------------------
# #1 Ubicación robusta: deferral determinista + resolutor LLM (no-canónico)
# ---------------------------------------------------------------------------

def _at_location_stage(lang: str = "es") -> ConversationState:
    """Estado justo en el paso de ubicación (cert conocida, sin ubicación)."""
    s = make_state(lang)
    s.step = Step.FREE_TEXT
    s.detected_activity = "certified_diving"
    s.is_certified = True
    s.detected_group_size = 1
    s.core_pending_slot = core.SLOT_LOCATION
    return s


@pytest.mark.parametrize("message", [
    "no sé, el que recomiendes",
    "da igual",
    "el que sea",
    "tú decides",
    "lo que prefieras",
    "whatever you recommend",
])
@pytest.mark.asyncio
async def test_location_deferral_deterministic_recommends_cartagena(message):
    """Una deferral ("no sé/da igual/recomiéndame") ya no loopea: se recomienda
    Cartagena (la salida más común) y el flujo avanza — como el árbol legacy."""
    state = _at_location_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})):
        await route_message(state, message)
    assert state.location == "cartagena"
    assert state.core_pending_slot != core.SLOT_LOCATION


@pytest.mark.asyncio
async def test_location_noncanonical_resolved_by_slot_resolver(monkeypatch):
    """Una salida real fuera de patrón ("desde el hotel Las Américas") que el
    regex no caza ya no loopea: el resolutor LLM la interpreta."""
    monkeypatch.setattr(core, "resolve_slot_answer",
                        AsyncMock(return_value={"value": "cartagena"}))
    state = _at_location_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})):
        await route_message(state, "salimos desde el hotel Las Américas")
    assert state.location == "cartagena"
    assert state.core_pending_slot != core.SLOT_LOCATION


@pytest.mark.asyncio
async def test_location_resolver_island_value(monkeypatch):
    monkeypatch.setattr(core, "resolve_slot_answer",
                        AsyncMock(return_value={"value": "island"}))
    state = _at_location_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})):
        await route_message(state, "ya estamos alojados por la zona de playa blanca")
    assert state.location == "island"


@pytest.mark.asyncio
async def test_location_resolver_abstains_reasks(monkeypatch):
    """Si el resolutor se abstiene, la ubicación NO se inventa y se re-pregunta
    (nunca peor que hoy)."""
    monkeypatch.setattr(core, "resolve_slot_answer", AsyncMock(return_value={}))
    state = _at_location_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})):
        await route_message(state, "uff qué pregunta tan complicada")
    assert state.location is None
    assert state.core_pending_slot == core.SLOT_LOCATION


def test_apply_resolved_slot_value_location():
    state = make_state("es")
    assert core._apply_resolved_slot_value(state, core.SLOT_LOCATION, "island")
    assert state.location == "island"
    assert core._apply_resolved_slot_value(state, core.SLOT_LOCATION, "cartagena")
    assert state.location == "cartagena"
    # Valor basura no se aplica.
    assert not core._apply_resolved_slot_value(state, core.SLOT_LOCATION, "xyz")


# ---------------------------------------------------------------------------
# #2 Cantidad de acompañante robusta: red LLM (Fase C la excluía)
# ---------------------------------------------------------------------------

def _at_companion_qty_stage(activity: str = "snorkel", lang: str = "es") -> ConversationState:
    s = make_state(lang)
    s.step = Step.FREE_TEXT
    s.detected_activity = "certified_diving"
    s.is_certified = True
    s.location = "cartagena"
    s.detected_group_size = 1
    s.last_dive_over_2_years = False
    s.is_colombian = False
    s.pending_companion_activity = activity
    s.core_pending_slot = core.SLOT_COMPANION_QTY
    return s


@pytest.mark.asyncio
async def test_companion_qty_un_par_resolved_by_slot_resolver(monkeypatch):
    """"un par" como cantidad de acompañante ya no loopea (SLOT_QTY sí tenía
    red, SLOT_COMPANION_QTY no — asimetría cerrada)."""
    monkeypatch.setattr(core, "resolve_slot_answer", AsyncMock(return_value={"value": 2}))
    state = _at_companion_qty_stage("snorkel")
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})):
        await route_message(state, "un par")
    assert (state.detected_group_allocation or {}).get("snorkel") == 2
    assert state.pending_companion_activity is None


@pytest.mark.asyncio
async def test_companion_qty_resolver_abstains_reasks(monkeypatch):
    """Si el resolutor se abstiene, no se inventa cantidad y se re-pregunta."""
    monkeypatch.setattr(core, "resolve_slot_answer", AsyncMock(return_value={}))
    state = _at_companion_qty_stage("snorkel")
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})):
        resp = await route_message(state, "uff ni idea la verdad")
    assert state.pending_companion_activity == "snorkel"
    assert "snorkel" in resp.lower()


@pytest.mark.asyncio
async def test_availability_question_canned_answer_not_hallucination():
    """Bug vivo en PRE (2026-07-24): "¿tienen disponibilidad el sábado?" con el
    núcleo on alucinaba "Claro que sí, tenemos disponibilidad". El gate del
    Bloque 2.5 estaba tras el hook; portado al núcleo. Va a RAG NUNCA."""
    state = make_state("es")
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"availability_question": True})), \
         patch("src.agents.supervisor.rag_answer",
               new=AsyncMock(side_effect=AssertionError("no debe ir a RAG: alucinaría cupo"))):
        resp = await route_message(state, "y para el finde que viene cómo andan")
    assert "diaria" in resp.lower()
    assert "calendario" in resp.lower() or "link" in resp.lower()


@pytest.mark.asyncio
async def test_availability_signal_ignored_mid_booking():
    """Con una actividad ya elegida, la señal amplia de disponibilidad NO
    secuestra: "¿algo para más días?" es una pregunta de PLAN, no de cupo
    (evita la regresión multi-día que Álvaro documentó)."""
    state = make_state("es")
    state.step = Step.FREE_TEXT
    state.detected_activity = "certified_diving"
    state.is_certified = True
    state.core_pending_slot = core.SLOT_LOCATION
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={"availability_question": True})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(return_value="RAG")):
        resp = await route_message(state, "no tenéis algo para más días")
    # No devuelve el canned de disponibilidad (sigue el flujo normal).
    assert "siempre hay disponibilidad" not in resp.lower()


def test_word_ages_helper():
    assert core._word_ages("cinco y siete") == [5, 7]
    assert core._word_ages("nueve") == [9]
    assert core._word_ages("doce y catorce") == [12, 14]
    assert core._word_ages("no me acuerdo bien") == []


def _at_ages_stage(lang: str = "es") -> ConversationState:
    s = make_state(lang)
    s.step = Step.FREE_TEXT
    s.detected_activity = "snorkel"
    s.core_pending_slot = core.SLOT_AGES
    return s


@pytest.mark.parametrize("message, expected", [
    ("tienen 7 y 9 años", [7, 9]),          # dígitos (ya funcionaba)
    ("cinco y siete", [5, 7]),               # palabras (gap cerrado)
    ("el peque tiene nueve", [9]),
    ("doce y catorce", [12, 14]),
])
@pytest.mark.asyncio
async def test_ages_word_numbers_resolved(message, expected):
    state = _at_ages_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})):
        await route_message(state, message)
    assert state.detected_ages == expected


@pytest.mark.asyncio
async def test_ages_no_number_does_not_invent(monkeypatch):
    """Sin ningún número (ni dígito ni palabra) no se inventa una edad."""
    state = _at_ages_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})):
        await route_message(state, "son pequeños todavía")
    assert not state.detected_ages


# ---------------------------------------------------------------------------
# #5 Actividad de acompañante robusta: red LLM (enum snorkel/minicurso)
# ---------------------------------------------------------------------------

def _at_companion_activity_stage(lang: str = "es") -> ConversationState:
    s = make_state(lang)
    s.step = Step.FREE_TEXT
    s.detected_activity = "certified_diving"
    s.is_certified = True
    s.location = "cartagena"
    s.detected_group_size = 1
    s.last_dive_over_2_years = False
    s.is_colombian = False
    s.core_pending_slot = core.SLOT_COMPANION_ACTIVITY
    return s


@pytest.mark.asyncio
async def test_companion_activity_resolved_by_llm(monkeypatch):
    """Respuesta no-canónica a "¿minicurso o snorkel?" ("que se quede arriba
    viendo peces") la resuelve el LLM → snorkel, y encadena a la cantidad."""
    monkeypatch.setattr(core, "resolve_slot_answer",
                        AsyncMock(return_value={"value": "snorkel"}))
    state = _at_companion_activity_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})):
        await route_message(state, "prefiere quedarse arriba viendo los peces")
    assert state.pending_companion_activity == "snorkel"
    assert state.core_pending_slot == core.SLOT_COMPANION_QTY


@pytest.mark.asyncio
async def test_companion_activity_deferral_reasks_not_dropped(monkeypatch):
    """Deferral que el LLM no fija ("lo que sea mejor"): se re-pregunta la
    actividad del acompañante en vez de caer al resumen perdiéndolo."""
    monkeypatch.setattr(core, "resolve_slot_answer", AsyncMock(return_value={}))
    state = _at_companion_activity_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})):
        resp = await route_message(state, "uy no sé, lo que sea mejor para ella")
    assert state.pending_companion_activity is None
    assert state.core_pending_slot == core.SLOT_COMPANION_ACTIVITY
    assert "snorkel" in resp.lower() or "minicurso" in resp.lower()


def test_apply_resolved_slot_value_companion_activity():
    state = make_state("es")
    assert core._apply_resolved_slot_value(state, core.SLOT_COMPANION_ACTIVITY, "minicourse")
    assert state.pending_companion_activity == "minicourse"
    assert state.needs_companion_activity is False
    assert not core._apply_resolved_slot_value(state, core.SLOT_COMPANION_ACTIVITY, "buceo")


# ---------------------------------------------------------------------------
# #6 Aperturas de búsqueda de info sin palabra-pregunta ni "?"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg", [
    "cuéntame qué incluye el precio",
    "me gustaría saber qué incluye",
    "dime cómo es el minicurso",
    "necesito saber los horarios",
    "tell me what's included",
    "i'd like to know the prices",
])
def test_info_question_openers_recognized(msg):
    from src.agents import supervisor
    assert supervisor._looks_like_info_question(msg)


@pytest.mark.parametrize("msg", [
    "puedo añadir snorkel",
    "quiero reservar buceo para dos",
    "quita el minicurso del carrito",
])
def test_info_question_not_cart_action(msg):
    from src.agents import supervisor
    assert not supervisor._looks_like_info_question(msg)


@pytest.mark.parametrize("msg", [
    "que se anime a bucear",          # exhortativo, NO pregunta
    "que él venga también",
    "que uno haga snorkel",
    "que ella pruebe el minicurso",
])
def test_que_conjuncion_not_a_question(msg):
    """"que" conjunción/exhortativo (seguido de pronombre átono/sujeto) NO es
    una pregunta, aunque tras quitar el acento sea indistinguible de "qué"."""
    from src.agents import supervisor
    assert not supervisor._looks_like_info_question(msg)


@pytest.mark.parametrize("msg", [
    "que incluye el precio",          # pregunta real sin tilde (muy común)
    "qué actividades hay",
    "que me recomiendas",             # "me" NO se excluye (sigue siendo pregunta)
    "qué precio tiene",
])
def test_que_interrogativo_still_question(msg):
    from src.agents import supervisor
    assert supervisor._looks_like_info_question(msg)


@pytest.mark.asyncio
async def test_companion_activity_que_se_anime_resolves(monkeypatch):
    """La respuesta "que se anime a bajar con el instructor" (empieza por "que")
    ya no se confunde con pregunta: llega al resolutor → minicurso."""
    monkeypatch.setattr(core, "resolve_slot_answer",
                        AsyncMock(return_value={"value": "minicourse"}))
    state = _at_companion_activity_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})):
        await route_message(state, "que se anime a bajar con el instructor")
    assert state.pending_companion_activity == "minicourse"


def test_product_mention_business_synonyms():
    """El detector de productos del núcleo reconoce ahora los sinónimos de
    negocio (bautizo=minicurso, careteo=snorkel) que el intent_detector ya
    conocía — sin esto, la deliberación con estas palabras no disparaba."""
    assert core._mentioned_product_activities("el bautizo") == ["minicourse"]
    assert core._mentioned_product_activities("bautismo de buceo") \
        and "minicourse" in core._mentioned_product_activities("bautismo de buceo")
    assert "snorkel" in core._mentioned_product_activities("careteo")
    assert "snorkel" in core._mentioned_product_activities("caretear en el arrecife")
    # bautizo vs careteo = 2 ofertas distintas
    offs = set(core._mentioned_offerings("no sé si el bautizo o el careteo"))
    assert {"minicourse", "snorkel"} <= offs


@pytest.mark.asyncio
async def test_deliberation_bautizo_vs_snorkel_routes_to_rag(monkeypatch):
    """"no sé si el bautizo o el snorkel" (sin "?") ahora dispara la
    deliberación (antes el regex no conocía "bautizo")."""
    from src.agents.rag_agent import FALLBACK_ES
    state = _at_activity_stage()
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})), \
         patch("src.agents.supervisor.rag_answer", new=AsyncMock(return_value=FALLBACK_ES)):
        resp = await route_message(state, "no sé si el bautizo o el snorkel")
    # Composer determinista (RAG cae al fallback) — no reserva.
    assert not state.mixed_cart
    assert "Snorkel" in resp


@pytest.mark.asyncio
async def test_companion_qty_other_product_not_resolved(monkeypatch):
    """Si la respuesta menciona OTRO producto distinto al preguntado ("3 for
    diving" respondiendo a la pregunta de snorkel), NO se aplica ese número al
    snorkel (evita facturar snorkel:3 con un número que era de buceo)."""
    resolver = AsyncMock(return_value={"value": 3})
    monkeypatch.setattr(core, "resolve_slot_answer", resolver)
    state = _at_companion_qty_stage("snorkel")
    with patch("src.agents.supervisor.detect_routing_signals",
               new=AsyncMock(return_value={})):
        await route_message(state, "en realidad somos 3 para buceo")
    assert (state.detected_group_allocation or {}).get("snorkel") != 3
    resolver.assert_not_awaited()  # ni se intentó resolver como cantidad de snorkel


# ---------------------------------------------------------------------------
# Fallback LLM de idioma en el welcome (re-cableado en Fase 4 tras retirar el
# flujo legacy que lo usaba). Solo se consulta si la heurística de stopwords
# (_detect_language_from_text) no detecta nada; su resultado gana a _infer_language.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_welcome_language_uses_llm_fallback_when_heuristic_misses(monkeypatch):
    """Si la heurística de stopwords devuelve None en el primer turno, el núcleo
    consulta detect_language_llm y usa su idioma (aquí 'en')."""
    monkeypatch.setattr("src.flows.decision_tree._detect_language_from_text", lambda m: None)

    async def _llm_says_en(message):
        return "en"

    monkeypatch.setattr("src.agents.language_detector.detect_language_llm", _llm_says_en)
    state = make_state("es")
    state.step = Step.WELCOME
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        await route_message(state, "info pls")
    assert state.language == "en"


@pytest.mark.asyncio
async def test_welcome_language_llm_not_called_when_heuristic_hits(monkeypatch):
    """Si la heurística ya detecta idioma, el fallback LLM NO se llama (short-circuit)."""
    called = False

    async def _llm(message):
        nonlocal called
        called = True
        return "en"

    monkeypatch.setattr("src.agents.language_detector.detect_language_llm", _llm)
    monkeypatch.setattr("src.flows.decision_tree._detect_language_from_text", lambda m: "es")
    state = make_state("en")
    state.step = Step.WELCOME
    with patch("src.agents.supervisor.detect_routing_signals", new=AsyncMock(return_value={})):
        await route_message(state, "hola quiero bucear")
    assert state.language == "es"
    assert called is False
