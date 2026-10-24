"""lat-B (24-oct, fase LAT, corte B de Gadea #1713/#1720): salió la «pregunta sola» de G3-05 (una llamada más en el
62 % de los turnos de real-1). La búsqueda doble vuelve a ir con el mensaje tal cual junto a la consulta reescrita
(como el 1-oct); la reescritura ya escribe la consulta en el idioma de la respuesta si el mensaje viene en otro."""
from unittest.mock import AsyncMock

import pytest

from src.agents import query_rewriter as qr
from src.agents import rag_agent


@pytest.mark.asyncio
async def test_la_busqueda_doble_va_con_el_mensaje_y_la_reescrita(monkeypatch):
    buscar = AsyncMock(return_value=[])
    monkeypatch.setattr(rag_agent, "search_knowledge_base", buscar)
    monkeypatch.setattr(rag_agent, "condense_query", AsyncMock(return_value="How do I pay for the Fun Dives?"))
    await rag_agent.rag_answer("great, how do i pay", lang="en", verify_grounding=False)
    assert {c.args[0] for c in buscar.await_args_list} == {"How do I pay for the Fun Dives?", "great, how do i pay"}


def test_ya_no_hay_pregunta_sola():
    assert not hasattr(qr, "pregunta_sola") and not hasattr(rag_agent, "pregunta_sola")


def test_un_mensaje_en_otro_idioma_se_reescribe_siempre():
    assert qr._should_condense("saímos de Cartagena, dia 30. Precisa saber nadar?", [], "en")
