"""Tests para la red de precisión LLM de los gates de enrutado/seguridad
(auditoría 2026-07-22): escalado a humano, menú/volver, y temas sensibles —
las 3 listas de palabras clave (ESCALATION_KEYWORDS, MENU_KEYWORDS/
BACK_KEYWORDS, SENSITIVE_RULES) no reconocían variantes regionales reales
("estoy embarazadita", "soy epiléptica", "tengo una condición cardiaca").

lat-11 T2 (26-oct): el router LLM de respaldo se quitó; las señales son de Jev (tests/test_u3_jev_router.py). Aquí
queda el texto de la respuesta sensible y el mensaje vacío.
"""

import pytest

from src.agents import jev_router
from src.agents.escalation import (
    SENSITIVE_RULES,
    detect_routing_signals,
    sensitive_response_for,
)


def test_sensitive_response_for_matches_keyword_path_text():
    """El texto de respuesta de la señal LLM debe ser IDÉNTICO al de la lista
    de palabras clave — mismo caso, misma respuesta, venga de donde venga."""
    from src.agents.escalation import _rule_message

    # El texto del camino de palabras clave sale de `_rule_message` (lleva el pase, 13-oct).
    keyword_reason, keyword_text = ("medical_questions", _rule_message(SENSITIVE_RULES["medical_questions"], "es"))
    llm_reason, llm_text = sensitive_response_for("medical_questions", "es")
    assert llm_reason == keyword_reason
    assert llm_text == keyword_text


def test_sensitive_response_for_unknown_category_returns_none():
    assert sensitive_response_for("no_existe", "es") is None


@pytest.mark.asyncio
async def test_mensaje_vacio_sin_llamar_a_jev(monkeypatch):
    async def _no(*_a, **_k):
        raise AssertionError("con el mensaje vacío no se llama a Jev")

    monkeypatch.setattr(jev_router, "detect_routing_signals_jev_full", _no)
    assert await detect_routing_signals("   ") == {}
