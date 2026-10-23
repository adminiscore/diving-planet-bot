"""arq-8c (23-oct, flag `principiante_sin_buceo_certificado`; G10 nº 6, g10-003): a quien dijo que no está certificado
no se le ofrece reservar una actividad que exige la certificación («Si quieres, te ayudo a reservar: *Buceo
certificado*»)."""
import pytest

from src.agents import conversational_core as cc
from src.config import settings
from src.flows.state import ConversationState


def _conv(**campos) -> ConversationState:
    st = ConversationState(conversation_id="arq8c", language="es")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def test_al_que_no_esta_certificado_no_se_le_ofrece_el_buceo(monkeypatch):
    monkeypatch.setattr(settings, "principiante_sin_buceo_certificado", True)
    st = _conv(actividad_preguntada="certified_diving", is_certified=False)
    assert cc._ofrecer_la_actividad_preguntada(st) is None and st.suggested_activity is None


@pytest.mark.parametrize("flag, certificado, actividad", [(False, False, "certified_diving"),
                                                          (True, True, "certified_diving"),
                                                          (True, None, "certified_diving"),
                                                          (True, False, "minicourse")])
def test_los_demas_casos_como_siempre(monkeypatch, flag, certificado, actividad):
    monkeypatch.setattr(settings, "principiante_sin_buceo_certificado", flag)
    st = _conv(actividad_preguntada=actividad, is_certified=certificado)
    oferta = cc._ofrecer_la_actividad_preguntada(st)
    assert oferta and "te ayudo a reservar" in oferta and st.suggested_activity == actividad
