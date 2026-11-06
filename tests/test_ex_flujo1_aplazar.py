"""EX-FLUJO-1 (decisión de Gadea, 14-oct, opción 2): si el cliente no contesta una pregunta de la reserva, se pregunta otra cosa.
CALN-43 P11 (decisión de Gadea, 6-nov) la sustituye: la que ya salió 2 veces no vuelve nunca, tampoco «antes del resumen»; se sigue con
lo que hay (`src/flows/que_preguntar.py`)."""
from src.agents import conversational_core as core
from src.agents.nucleo import slotfill_close
from src.flows import que_preguntar
from src.flows.state import ConversationState


def _estado(**kw) -> ConversationState:
    st = ConversationState(conversation_id="flujo1", language="es")
    st.detected_activity = "certified_diving"
    st.is_certified = True
    st.location = "cartagena"
    for k, v in kw.items():
        setattr(st, k, v)
    return st


def test_a_la_tercera_se_pregunta_otra_cosa_y_no_vuelve():
    st = _estado(detected_group_size=2)  # faltan: última inmersión (safety) y nacionalidad
    assert core.next_missing_slot(st) == core.SLOT_SAFETY
    # Salió una vez y el cliente habló de otra cosa: se repite una vez…
    st.preguntas_hechas = {core.SLOT_SAFETY: 1}
    assert core._siguiente_pregunta(st, core.SLOT_SAFETY) == core.SLOT_SAFETY
    # …y con 2, no se repite una tercera: se pregunta otra cosa.
    st.preguntas_hechas = {core.SLOT_SAFETY: 2}
    assert core._siguiente_pregunta(st, core.SLOT_SAFETY) == core.SLOT_NATIONALITY
    # Contesta la nacionalidad: ya no falta nada más que la seguridad, agotada: la tarjeta sale con el aviso y sin la pregunta, aunque
    # la del turno anterior fuera la nacionalidad (antes volvía «justo antes del resumen»: la 3.ª vez).
    st.is_colombian = False
    assert slotfill_close._tarjeta_sin_seguridad(st, core.SLOT_SAFETY, prev_pending=core.SLOT_NATIONALITY)


def test_antes_de_dos_veces_se_pregunta_lo_primero_que_falta():
    st = _estado(detected_group_size=2)
    assert core._siguiente_pregunta(st, core.SLOT_SAFETY) == core.SLOT_SAFETY


def test_la_actividad_agotada_no_se_salta_y_queda_pendiente():
    """La actividad condiciona todo lo demás: no se salta. Queda pendiente y el compositor no la vuelve a poner (test_que_preguntar, a03)."""
    st = ConversationState(conversation_id="flujo1", language="es")
    st.preguntas_hechas = {core.SLOT_ACTIVITY: 2}
    assert core._siguiente_pregunta(st, core.SLOT_ACTIVITY) == core.SLOT_ACTIVITY
    assert core.SLOT_ACTIVITY not in que_preguntar.se_sigue_sin(st.preguntas_hechas)


def test_si_solo_falta_la_seguridad_sale_la_tarjeta_con_el_aviso():
    st = _estado(detected_group_size=2, is_colombian=False)  # solo falta la última inmersión
    assert not slotfill_close._tarjeta_sin_seguridad(st, core.SLOT_SAFETY, prev_pending=None)  # aún no se ha preguntado
    assert slotfill_close._tarjeta_sin_seguridad(st, core.SLOT_SAFETY, prev_pending=core.SLOT_SAFETY)
    st.preguntas_hechas = {core.SLOT_SAFETY: 2}
    assert slotfill_close._tarjeta_sin_seguridad(st, core.SLOT_SAFETY, prev_pending=None)


def test_sin_el_numero_agotado_se_cierra_por_persona():
    st = _estado(is_colombian=False, last_dive_over_2_years=False)  # solo falta cuántos son
    assert core.next_missing_slot(st) == core.SLOT_QTY
    st.preguntas_hechas = {core.SLOT_QTY: 2}
    assert core.next_missing_slot(st, saltar=que_preguntar.se_sigue_sin(st.preguntas_hechas)) is None  # se cierra con lo que hay
    from src.flows.cart_render import linea_de_precio

    assert linea_de_precio("178 USD", 1, "es") == "💰 *178 USD* por persona"  # sin el número: por persona


def test_el_origen_agotado_no_se_salta():
    st = _estado(detected_group_size=2)
    st.location = None
    st.preguntas_hechas = {core.SLOT_LOCATION: 2}
    assert core.next_missing_slot(st, saltar=que_preguntar.se_sigue_sin(st.preguntas_hechas)) == core.SLOT_LOCATION


def test_la_nacionalidad_es_siempre_la_ultima():
    st = _estado(detected_group_size=2)
    st.preguntas_hechas = {core.SLOT_SAFETY: 2}  # la última inmersión, agotada: ya no vuelve detrás
    assert "Última cosa" in core.ask_slot(st, core.SLOT_NATIONALITY)


def test_a_un_certificado_se_le_recomiendan_sus_opciones():
    st = ConversationState(conversation_id="flujo1", language="es")
    st.is_certified = True
    texto = core.ask_slot(st, core.SLOT_ACTIVITY)
    assert "2 inmersiones" in texto and "minicurso" not in texto.lower() and "snorkel" not in texto.lower()
    st2 = ConversationState(conversation_id="flujo1", language="es")
    assert "Minicurso" in core.ask_slot(st2, core.SLOT_ACTIVITY)  # sin certificación: el menú de siempre


def test_mismo_dia_solo_si_se_sabe():
    """EX-EST-2: "el plan de 5 buceos para el finde" (buceo certificado sin duración) recibía "ida y vuelta el mismo día"."""
    st = ConversationState(conversation_id="flujo1", language="es")
    st.detected_activity = "certified_diving"
    assert "mismo día" not in core.ask_slot(st, core.SLOT_LOCATION)
    st.detected_duration = "single_day"
    assert "mismo día" in core.ask_slot(st, core.SLOT_LOCATION)


def test_mismo_dia_no_si_el_cliente_pregunta():
    """CALN (g21): «¿y si en vez de un día buceamos 2 días?» con el plan de un día del estado recibía «ida y vuelta el
    mismo día». Si el cliente pregunta, el plan puede cambiar: no se afirma su duración."""
    st = ConversationState(conversation_id="flujo1", language="es")
    st.detected_activity = "certified_diving"
    st.detected_duration = "single_day"
    st._senales_router = {"asks_question": True}
    assert "mismo día" not in core.ask_slot(st, core.SLOT_LOCATION)
    st._senales_router = {"asks_question": False}
    assert "mismo día" in core.ask_slot(st, core.SLOT_LOCATION)


def test_politicas_nuevas_siempre_en_el_contexto():
    from src.flows.catalog import policies_facts

    es = policies_facts("es")
    assert "San Bernardo" in es and "Siempre hay disponibilidad" in es and "cédula de extranjería" in es
