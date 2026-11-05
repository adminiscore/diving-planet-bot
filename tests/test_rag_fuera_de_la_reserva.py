"""El RAG de los caminos que contestan fuera de la reserva (buceo adaptado): la búsqueda recibe el origen del cliente (rag-3)."""
from unittest.mock import patch

import pytest

from src.agents import conversational_core as core
from src.flows.state import ConversationState, Step


@pytest.mark.asyncio
async def test_el_camino_de_buceo_adaptado_busca_con_el_origen():
    llamadas = []

    async def rag(query, **kw):
        llamadas.append(kw)
        return "respuesta"

    state = ConversationState(conversation_id="rag-fuera", language="es", location="cartagena")
    state.step = Step.FREE_TEXT
    state.history = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "¡Hola!"}]
    with patch("src.agents.supervisor.rag_answer", new=rag), \
         patch("src.agents.supervisor._build_extra_context", return_value="x"):
        await core.rag_fuera_de_la_reserva(state, "¿es accesible la lancha?", state.history)
    assert llamadas[0]["origin"] == "cartagena"
