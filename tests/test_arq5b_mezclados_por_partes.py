"""arq-5b (23-oct, flag `mezclados_por_partes`): en un mensaje mezclado, la parte de la tabla la escribe el redactor con
los hechos y el RAG, a la vez, solo lo demás (G10 nº 5: listas incompletas y el reintento que subía la p90)."""

import pytest

from src.agents import conversational_core as core
from src.agents import redactor_hechos, supervisor
from src.config import settings
from src.flows.state import ConversationState


def _estado():
    st = ConversationState(conversation_id="arq5b", language="es")
    st._hechos_del_rag = ([{"actividad": "minicourse", "incluye": {"cartagena": ["Piscina"]}}], ["incluye"])
    return st


async def _ejecutar(monkeypatch, parte, demas):
    vistos = {}

    async def redactar(state, message, history, bloques, cubiertas):
        vistos["cubiertas"] = cubiertas
        return parte

    async def rag(message, **entradas):
        vistos["entradas"] = entradas
        return demas

    monkeypatch.setattr(redactor_hechos, "redactar_parte", redactar)
    monkeypatch.setattr(supervisor, "rag_answer", rag)
    entradas = {"extra_context": "Estado", "hechos": "{}", "hechos_bloques": ([], [])}
    return await core._mezclado_por_partes(_estado(), "¿qué incluye y qué peces se ven?", [], entradas), vistos


async def test_apagado_no_hace_nada(monkeypatch):
    monkeypatch.setattr(settings, "mezclados_por_partes", False)
    assert await core._mezclado_por_partes(_estado(), "x", [], {}) is None


async def test_la_tabla_del_redactor_y_lo_demas_del_rag(monkeypatch):
    monkeypatch.setattr(settings, "mezclados_por_partes", True)
    answer, vistos = await _ejecutar(monkeypatch, "Incluye la piscina.", "Se ven peces loro.")
    assert answer == "Incluye la piscina.\n\nSe ven peces loro."
    assert vistos["cubiertas"] == ["incluye"]
    assert "hechos" not in vistos["entradas"] and "hechos_bloques" not in vistos["entradas"]
    assert "lo que incluye" in vistos["entradas"]["extra_context"] and "NADA" in vistos["entradas"]["extra_context"]


@pytest.mark.parametrize("demas", ["NADA", "", None])
async def test_si_el_rag_no_tiene_nada_mas_va_solo_la_tabla(monkeypatch, demas):
    monkeypatch.setattr(settings, "mezclados_por_partes", True)
    answer, _ = await _ejecutar(monkeypatch, "Incluye la piscina.", demas)
    assert answer == "Incluye la piscina."


async def test_sin_parte_del_redactor_contesta_el_rag_como_antes(monkeypatch):
    monkeypatch.setattr(settings, "mezclados_por_partes", True)
    answer, _ = await _ejecutar(monkeypatch, None, "Se ven peces loro.")
    assert answer is None
