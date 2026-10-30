"""Sparring s30a (30-oct, contra la candidata 0.39; docs/robustness/g3/hallazgos.md, CALN-S30A-03): el buzo que lleva
años sin bucear y viene varios días hace el refresher el primero y bucea los demás; los hechos llevan los dos. Sin red."""
from src.agents import redactor_hechos
from src.flows import hechos
from src.flows.state import ConversationState


def _buzo(duracion):
    st = ConversationState(conversation_id="s30a", language="en")
    st.detected_activity, st.is_certified, st.last_dive_over_2_years = "certified_diving", True, True
    st.location, st.detected_duration = "cartagena", duracion
    return st


def test_varios_dias_el_refresher_y_el_buceo_de_los_demas_dias():
    assert redactor_hechos._actividades(_buzo("multi_day"), {}) == ["refresher", "certified_diving"]
    assert redactor_hechos._actividades(_buzo("single_day"), {}) == ["refresher"]
    assert redactor_hechos._actividades(_buzo(None), {}) == ["refresher"]


def test_con_el_refresher_el_buceo_va_con_su_plan_de_un_dia():
    st = _buzo("multi_day")
    solo = {b["actividad"]: b for b in hechos.hechos(st, ["precio"], ["certified_diving"])}
    juntos = {b["actividad"]: b for b in hechos.hechos(st, ["precio"], ["refresher", "certified_diving"])}
    assert set(juntos) == {"refresher", "certified_diving"}
    assert "2 days" in solo["certified_diving"]["precio"]["cartagena"]["plan"]  # sin el refresher: el paquete de 2 días
    assert "(1 day)" in juntos["certified_diving"]["precio"]["cartagena"]["plan"]  # con él: el día de buceo que queda
