"""ARQ-1i (23-oct, flag `intenciones_clima_pago`, decisión de Gadea #1312): el clima en GENERAL y cómo se paga entran en
la tabla. Jev los pregunta (pide_clima, pide_pago) y «otra cosa» deja de contarlos; una pregunta general del clima ya no
va a la ruta sensible (con un día concreto Jev no la marca y sigue el pase); los hechos dan la política del clima
(weather_cancellation: reprogramar o reembolso del 100 %) y el pago según la nacionalidad. Sin red."""
import pytest

from src.agents import jev_router as j
from src.config import settings
from src.flows import hechos
from src.flows.state import ConversationState
from src.orchestration.router import classify_route
from src.orchestration.state import ROUTE_SAFETY

CLIMA = "¿Qué pasa si hace mal tiempo y hay tormenta? ¿Se cancela?"


@pytest.fixture
def encendido(monkeypatch):
    monkeypatch.setattr(settings, "intenciones_clima_pago", True)


def _st(**kw):
    return ConversationState(conversation_id="arq1i", language="es", **kw)


def test_apagado_jev_no_pregunta(monkeypatch):
    monkeypatch.setattr(settings, "intenciones_clima_pago", False)
    q = j._questions_for_turn()
    assert j.PIDE_CLIMA not in q and j.PIDE_PAGO not in q
    assert j._OTRA_COSA_SIN_CLIMA_NI_PAGO not in q[j.PIDE_OTRA_COSA]["instructions"]


def test_encendido_jev_pregunta_y_otra_cosa_no_los_cuenta(encendido):
    q = j._questions_for_turn()
    assert q[j.PIDE_CLIMA] is j._PIDE_CLIMA_Q and q[j.PIDE_PAGO] is j._PIDE_PAGO_Q
    otra = q[j.PIDE_OTRA_COSA]["instructions"]
    assert otra.endswith(j._OTRA_COSA_SIN_CLIMA_NI_PAGO)
    assert "the weather, " not in otra and "payment methods, cancellations" not in otra
    senales = j.answers_to_signals({j.PIDE_CLIMA: {"type": "noul", "noul": 0.9},
                                    j.PIDE_PAGO: {"type": "noul", "noul": 0.2}})
    assert senales[j.PIDE_CLIMA] is True and senales[j.PIDE_PAGO] is False


def test_las_senales_viajan_tambien_cuando_jev_duda():
    assert {j.PIDE_CLIMA, j.PIDE_PAGO} <= set(j._TURN_SIGNALS) and {j.PIDE_CLIMA, j.PIDE_PAGO} <= set(j._U34_QUESTIONS)


def test_el_clima_general_no_va_a_la_ruta_sensible(encendido):
    general = {"sensitive_topic": "weather_conditions", j.PIDE_CLIMA: True}
    assert classify_route(_st(), CLIMA, general) != ROUTE_SAFETY
    # Con un día concreto Jev no marca pide_clima: sigue el pase.
    assert classify_route(_st(), "¿va a llover el sábado?", {"sensitive_topic": "weather_conditions"}) == ROUTE_SAFETY


def test_apagado_el_clima_sigue_en_la_ruta_sensible(monkeypatch):
    monkeypatch.setattr(settings, "intenciones_clima_pago", False)
    general = {"sensitive_topic": "weather_conditions", j.PIDE_CLIMA: True}
    assert classify_route(_st(), CLIMA, general) == ROUTE_SAFETY


def test_pide_clima_no_salva_otro_tema_sensible(encendido):
    assert classify_route(_st(), "Estoy embarazada, ¿y si hace mal tiempo?",
                          {"sensitive_topic": "medical_questions", j.PIDE_CLIMA: True}) == ROUTE_SAFETY


def test_hechos_del_clima_sin_actividad_y_con_ella(encendido):
    [b] = hechos.hechos_sin_actividad(_st(), ["clima"])
    assert b["clima"][0] == hechos._politica("weather_cancellation", "es")
    assert "100" in b["clima"][0] and "reprogramar" in b["clima"][0]
    assert b["clima"][1] == hechos._politica("closed_days", "es") and "asesor" in b["clima"][2]
    assert hechos.hechos(_st(), ["clima"], ["snorkel"])[0]["clima"] == b["clima"]


def test_el_pago_segun_la_nacionalidad(encendido):
    [extranjero] = hechos.hechos_sin_actividad(_st(is_colombian=False), ["pago"])
    assert "100 %" in extranjero["pago"][0] and "50 %" not in " ".join(extranjero["pago"])
    assert hechos._politica("payment_confirmation", "es") in extranjero["pago"]
    [colombiano] = hechos.hechos_sin_actividad(_st(is_colombian=True), ["pago"])
    assert colombiano["pago"][0].startswith("El anticipo del 50 %") and "asesor" in colombiano["pago"][0]
    [no_se_sabe] = hechos.hechos_sin_actividad(_st(), ["pago"])
    assert no_se_sabe["pago"][0] == hechos._politica("foreign_card_payment", "es")


def test_apagado_no_hay_hechos_de_clima_ni_pago(monkeypatch):
    monkeypatch.setattr(settings, "intenciones_clima_pago", False)
    assert hechos.hechos_sin_actividad(_st(), ["clima", "pago"]) in (
        [], [{"actividad": None, "nombre": "general", "origen": None}])


def test_arq3_echa_de_menos_el_reembolso_y_el_pago(encendido):
    [b] = hechos.hechos_sin_actividad(_st(is_colombian=False), ["clima", "pago"])
    sin_nada = hechos.faltan("Si hace mal tiempo te avisamos.", [b], ["clima", "pago"])
    assert sin_nada == [b["clima"][0], b["pago"][0]]
    assert hechos.faltan(f"{b['clima'][0]}\n{b['pago'][0]}", [b], ["clima", "pago"]) == []
