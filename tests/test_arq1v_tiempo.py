"""ARQ-1v (22-oct, flag `tiempo_limitado`): «me voy mañana al mediodía, ¿me da tiempo?» entra en la tabla. Jev lo pregunta
(pide_si_alcanza) y «otra cosa» deja de contarlo; los hechos dan la decisión de Gadea (política time_limited_departure:
desde las islas va muy justo y lo confirma un asesor; desde Cartagena no alcanza; cierre de las 4:30) y la espera antes
de volar aparte (`si_vuela`). Sin red."""
from src.agents import jev_router as j
from src.flows import hechos
from src.flows.state import ConversationState


def _st():
    return ConversationState(conversation_id="arq1v", language="es")


def test_encendido_jev_pregunta_y_otra_cosa_no_lo_cuenta(monkeypatch):
    q = j._questions_for_turn()
    assert q[j.PIDE_SI_ALCANZA] is j._PIDE_SI_ALCANZA_Q
    assert j._OTRA_COSA_SIN_EL_TIEMPO in q[j.PIDE_OTRA_COSA]["instructions"]  # arq-1i añade su frase detrás
    assert j.answers_to_signals({j.PIDE_SI_ALCANZA: {"type": "noul", "noul": 0.9}})[j.PIDE_SI_ALCANZA] is True


def test_los_hechos_llevan_la_decision_y_aparte_el_vuelo(monkeypatch):
    [b] = hechos.hechos_sin_actividad(_st(), ["tiempo"])
    assert b["tiempo"][0] == hechos._politica("time_limited_departure", "es")
    assert "4:30" in b["tiempo"][0] and "asesor" in b["tiempo"][0]
    assert b["si_vuela"] == hechos._politica("flight_after_diving", "es")
    con_actividad = hechos.hechos(_st(), ["tiempo"], ["minicourse"])[0]
    assert con_actividad["tiempo"] == b["tiempo"]


def test_arq3_echa_de_menos_la_decision(monkeypatch):
    [b] = hechos.hechos_sin_actividad(_st(), ["tiempo"])
    assert hechos.faltan("La actividad termina hacia las 12:00-13:00.", [b], ["tiempo"]) == [b["tiempo"][0]]
    assert hechos.faltan(b["tiempo"][0], [b], ["tiempo"]) == []


def test_la_senal_viaja_tambien_cuando_jev_duda():
    """Banco arq-1v, v1: con Jev dudando en otra pregunta del router, solo pasan `_TURN_SIGNALS`."""
    assert j.PIDE_SI_ALCANZA in j._TURN_SIGNALS
