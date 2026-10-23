"""gen-7 (20-oct, fase GEN; refresher).

- `seguridad_de_grupo`: la pregunta de seguridad es de GRUPO ("¿… de alguno del grupo?"). "Sí, uno de nosotros no bucea
  desde hace 4 años" lo guarda el extractor como de otra persona (`acompanante_certificado_inactivo`) y la pregunta se
  repetía; ahora cuenta y sigue al refresher (banco gen-7: 2/2 repetía la pregunta).
- `refresher_completo`: el texto fijo del refresher dice que se reserva como Minicurso y que lleva el formulario médico
  de curso (lo que dice la base)."""

import pytest

from src.agents import conversational_core as core
from src.flows.state import ConversationState


def _grupo_certificado(**over) -> ConversationState:
    st = ConversationState(conversation_id="gen7", language="es")
    st.detected_activity = "certified_diving"
    st.is_certified = True
    st.location = st.detected_location = "cartagena"
    st.detected_group_size = 2
    for k, v in over.items():
        setattr(st, k, v)
    return st


def test_otro_del_grupo_sin_bucear_contesta_la_pregunta_de_seguridad():
    st = _grupo_certificado(acompanante_certificado_inactivo=True)
    assert core.next_missing_slot(st) == core.SLOT_REFRESHER


@pytest.mark.parametrize("ultima, otro, esperado", [
    (None, False, None), (True, False, True), (False, False, False), (False, True, True), (None, True, True),
])
def test_refresh_en_el_grupo(monkeypatch, ultima, otro, esperado):
    st = _grupo_certificado(last_dive_over_2_years=ultima, acompanante_certificado_inactivo=otro)
    assert core.refresh_en_el_grupo(st) is esperado


def test_nadie_sin_bucear_sigue_sin_refresher(monkeypatch):
    st = _grupo_certificado(last_dive_over_2_years=False)
    assert core.next_missing_slot(st) not in (core.SLOT_SAFETY, core.SLOT_REFRESHER)


def test_el_texto_del_refresher():
    texto = core.ask_slot(_grupo_certificado(last_dive_over_2_years=True), core.SLOT_REFRESHER)
    assert "*Minicurso de Buceo*" in texto and "formulario médico de curso" in texto
    assert "por persona que lo necesite" in texto
