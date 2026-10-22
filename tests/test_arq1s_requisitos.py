"""ARQ-1s (22-oct, flag `requisitos_coherentes`): requisitos coherentes en los hechos. En un curso, un solo formulario (el
médico de curso; decisión de Gadea: el Advanced recibía también el de buzo certificado y el G10 lo vio contradictorio), el
requisito previo (el nivel anterior del registro) y la edad mínima en cifra. Sin red."""
import pytest

from src.config import settings
from src.flows import hechos
from src.flows.state import ConversationState

CURSO = "exoneracion-curso"
BUZO = "exoneracion-buzo"


def _requisitos(actividad: str, lang: str = "es") -> list[str]:
    st = ConversationState(conversation_id="arq1s", language=lang)
    st.location = "cartagena"
    return hechos.hechos(st, ["requisitos"], [actividad])[0]["requisitos"]


@pytest.mark.parametrize("lang", ["es", "en"])
def test_el_corte_de_la_politica_existe(lang):
    """Si alguien reescribe la política médica sin la frase del buzo certificado, el corte dejaría de aplicarse."""
    assert hechos._CORTE_FORMULARIO[lang] in hechos._politica("medical_restrictions", lang)


def test_apagado_como_antes(monkeypatch):
    monkeypatch.setattr(settings, "requisitos_coherentes", False)
    texto = " ".join(_requisitos("padi_advanced"))
    assert CURSO in texto and BUZO in texto


@pytest.mark.parametrize("lang", ["es", "en"])
def test_el_advanced_un_formulario_su_previo_y_su_edad(monkeypatch, lang):
    monkeypatch.setattr(settings, "requisitos_coherentes", True)
    req = _requisitos("padi_advanced", lang)
    texto = " ".join(req)
    assert CURSO in texto and BUZO not in texto
    assert any("Open Water" in r and "Advanced" not in r for r in req)  # el previo, no el propio curso
    assert any("12" in r for r in req)


def test_el_rescue_pide_el_advanced(monkeypatch):
    monkeypatch.setattr(settings, "requisitos_coherentes", True)
    assert any("Advanced Open Water" in r for r in _requisitos("padi_rescue", "en"))


def test_el_open_water_no_tiene_previo(monkeypatch):
    monkeypatch.setattr(settings, "requisitos_coherentes", True)
    assert not any(r.startswith("Requisito previo") for r in _requisitos("padi_open_water"))


def test_el_minicurso_no_repite_el_formulario(monkeypatch):
    monkeypatch.setattr(settings, "requisitos_coherentes", True)
    assert sum(CURSO in r for r in _requisitos("minicourse")) == 1


def test_sin_actividad_el_certificado_lleva_el_carne(monkeypatch):
    """«Soy buzo certificado, ¿qué requisitos hay?» sin actividad dicha va al bloque general (arq-1p): con arq-1s, el carné."""
    monkeypatch.setattr(settings, "requisitos_coherentes", True)
    st = ConversationState(conversation_id="arq1s", language="es")
    st.is_certified = True
    [bloque] = hechos.hechos_sin_actividad(st, ["requisitos"])
    assert bloque["requisitos"][0] == hechos._politica("certification_required", "es")
    st.is_certified = None
    [bloque] = hechos.hechos_sin_actividad(st, ["requisitos"])
    assert hechos._politica("certification_required", "es") not in bloque["requisitos"]
