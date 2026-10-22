"""arq-2a (22-oct, flag `rag_sin_reglas_del_codigo`): fuera del prompt del RAG las reglas que el código ya pone en el
contexto que el RAG lee siempre (catálogo y políticas). Se fija: (1) cada regla que se quita está en el prompt (si
alguien la reescribe, el cambio dejaría de aplicarse sin avisar); (2) el dato que la sustituye sigue en el contexto;
(3) las reglas que solo vigila un guarda se quedan."""
import pytest

from src.agents.rag_agent import build_system_prompt
from src.config import settings
from src.flows.catalog import catalog_facts, policies_facts
from src.prompts import info

REGLAS = {"es": info.RAG_SIN_REGLAS_DEL_CODIGO_ES, "en": info.RAG_SIN_REGLAS_DEL_CODIGO_EN}
# Lo que dice el contexto en lugar de cada regla que se quita (catálogo + políticas).
EN_EL_CONTEXTO = {
    "es": ("Moneda:", "25 de diciembre", "suspend"),
    "en": ("Currency:", "December 25", "weather"),
}
# Reglas con un guarda en rag_agent (importes, enlaces, teléfono, datos personales): se quedan. Las dos de descuentos
# también: el catálogo solo dice "no calcules totales" y sin la regla el guarda de importes tiraba el precio por persona
# con el descuento (test_rag_safety, 17-jul).
SE_QUEDAN = {
    "es": ("NUNCA des un número de teléfono", "No inventes ni reconstruyas links", "Nunca inventes precios",
           "NUNCA gestiones la reserva recogiendo datos", "nombra las opciones con su precio", "equipo parcial",
           "NUNCA calcules ni afirmes el precio final"),
    "en": ("NEVER give a phone or WhatsApp number", "Do not invent or reconstruct payment", "Never invent prices",
           "NEVER process a booking by collecting data", "name the options with their price", "partial gear",
           "NEVER calculate or state the final discounted price"),
}


@pytest.mark.parametrize("lang", ["es", "en"])
def test_cada_regla_que_se_quita_esta_en_el_prompt(monkeypatch, lang):
    monkeypatch.setattr(settings, "rag_sin_reglas_del_codigo", False)
    prompt = build_system_prompt(lang)
    for antes, _ in REGLAS[lang]:
        assert antes in prompt, antes[:60]


@pytest.mark.parametrize("lang", ["es", "en"])
def test_con_el_flag_salen_y_el_dato_sigue_en_el_contexto(monkeypatch, lang):
    monkeypatch.setattr(settings, "rag_sin_reglas_del_codigo", True)
    prompt = build_system_prompt(lang)
    for antes, despues in REGLAS[lang]:
        assert antes not in prompt or antes in despues
    contexto = catalog_facts(lang) + policies_facts(lang)
    for dato in EN_EL_CONTEXTO[lang]:
        assert dato in contexto, dato
    for regla in SE_QUEDAN[lang]:
        assert regla in prompt, regla
    corta = info.RAG_DISPONIBILIDAD_CORTA_ES if lang == "es" else info.RAG_DISPONIBILIDAD_CORTA_EN
    assert corta in prompt


@pytest.mark.parametrize("lang", ["es", "en"])
def test_apagado_el_prompt_no_cambia(monkeypatch, lang):
    monkeypatch.setattr(settings, "rag_sin_reglas_del_codigo", False)
    assert info.RAG_DISPONIBILIDAD_CORTA_ES not in build_system_prompt(lang)
    assert info.RAG_DISPONIBILIDAD_CORTA_EN not in build_system_prompt(lang)
