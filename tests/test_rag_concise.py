"""Latencia del RAG (28-sep, flag `rag_concise`): la respuesta contesta solo lo preguntado.

Se fija el prompt, no la conducta del LLM (esa se mide con el A/B):
1. con el flag, el prompt lleva la regla de longitud y la intro corta, en los dos idiomas;
2. sin el flag, el prompt es el de siempre;
3. las frases que se sustituyen siguen en el cuerpo (si alguien las reescribe, la sustitución fallaría en silencio);
4. el prompt no depende de la pregunta (el caché del prompt de OpenAI necesita que sea fijo por idioma).
"""

import pytest

from src.agents.rag_agent import build_system_prompt
from src.config import settings
from src.prompts import info


@pytest.mark.parametrize("lang,concise,long_,short", [
    ("es", info.RAG_CONCISE_ES, info.RAG_INTRO_LONG_ES, info.RAG_INTRO_SHORT_ES),
    ("en", info.RAG_CONCISE_EN, info.RAG_INTRO_LONG_EN, info.RAG_INTRO_SHORT_EN),
])
def test_con_el_flag_lleva_la_regla_y_la_intro_corta(monkeypatch, lang, concise, long_, short):
    monkeypatch.setattr(settings, "rag_concise", True)
    prompt = build_system_prompt(lang)
    assert prompt.endswith(concise)
    assert short in prompt
    assert long_ not in prompt


@pytest.mark.parametrize("lang", ["es", "en"])
def test_sin_el_flag_el_prompt_no_cambia(monkeypatch, lang):
    monkeypatch.setattr(settings, "rag_concise", False)
    prompt = build_system_prompt(lang)
    assert "Longitud — importante" not in prompt and "Length — important" not in prompt


def test_las_frases_que_se_sustituyen_siguen_en_el_cuerpo():
    assert info.RAG_INTRO_LONG_ES in info.RAG_BODY_ES
    assert info.RAG_INTRO_LONG_EN in info.RAG_BODY_EN


@pytest.mark.parametrize("lang", ["es", "en"])
def test_el_prompt_es_fijo_por_idioma(monkeypatch, lang):
    monkeypatch.setattr(settings, "rag_concise", True)
    assert build_system_prompt(lang, query="¿cuánto dura?") == build_system_prompt(lang, query="¿qué incluye?")
