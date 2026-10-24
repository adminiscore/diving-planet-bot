"""EX-FLUJO-1 (decisión de Gadea, 14-oct, opción 2): si el cliente no contesta
una pregunta de la reserva, no se repite en el turno siguiente; se aplaza y vuelve justo antes del resumen."""
from src.agents import conversational_core as core
from src.flows.state import ConversationState


def _estado(**kw) -> ConversationState:
    st = ConversationState(conversation_id="flujo1", language="es")
    st.detected_activity = "certified_diving"
    st.is_certified = True
    st.location = "cartagena"
    for k, v in kw.items():
        setattr(st, k, v)
    return st


def test_sin_contestar_se_pregunta_otra_cosa_y_vuelve_al_final():
    st = _estado(detected_group_size=2)  # faltan: última inmersión (safety) y nacionalidad
    assert core.next_missing_slot(st) == core.SLOT_SAFETY
    # El bot preguntó la última inmersión y el cliente habló de otra cosa: se repite una vez (como hoy)…
    assert core._siguiente_pregunta(st, prev_pending=core.SLOT_SAFETY) == core.SLOT_SAFETY
    assert st.preguntas_aplazadas == []
    # …y si tampoco la contesta, no se repite una tercera: se aplaza.
    assert core._siguiente_pregunta(st, prev_pending=core.SLOT_SAFETY) == core.SLOT_NATIONALITY
    assert st.preguntas_aplazadas == [core.SLOT_SAFETY]
    # Contesta la nacionalidad: ya no falta nada más -> vuelve la aplazada, justo antes del resumen.
    st.is_colombian = False
    assert core._siguiente_pregunta(st, prev_pending=core.SLOT_NATIONALITY) == core.SLOT_SAFETY


def test_contestada_no_se_aplaza():
    st = _estado(detected_group_size=2)
    assert core._siguiente_pregunta(st, prev_pending=core.SLOT_QTY) == core.SLOT_SAFETY
    assert st.preguntas_aplazadas == []


def test_la_actividad_no_se_aplaza():
    """La actividad condiciona todo lo demás: si no la contesta, se sigue preguntando."""
    st = ConversationState(conversation_id="flujo1", language="es")
    assert core._siguiente_pregunta(st, prev_pending=core.SLOT_ACTIVITY) == core.SLOT_ACTIVITY
    assert st.preguntas_aplazadas == []


def test_si_es_la_unica_que_falta_se_pregunta():
    st = _estado(detected_group_size=2, is_colombian=False)  # solo falta la última inmersión
    for _ in range(3):
        assert core._siguiente_pregunta(st, prev_pending=core.SLOT_SAFETY) == core.SLOT_SAFETY


def test_ultima_cosa_solo_si_es_la_ultima():
    st = _estado(detected_group_size=2)
    st.preguntas_aplazadas = [core.SLOT_SAFETY]  # la última inmersión, aplazada y sin contestar
    assert "Última cosa" not in core.ask_slot(st, core.SLOT_NATIONALITY)
    st.last_dive_over_2_years = False
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


def test_politicas_nuevas_siempre_en_el_contexto():
    from src.flows.catalog import policies_facts

    es = policies_facts("es")
    assert "San Bernardo" in es and "Siempre hay disponibilidad" in es and "cédula de extranjería" in es
