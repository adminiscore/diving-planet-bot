"""G3-07a (18-oct, decisión de Gadea: una sola moneda por mensaje), flag `rag_sin_precio_con_tarjeta`.

El punto de decisión del flujo (`_slotfill_close_phase`): si el turno lleva la tarjeta del plan y la respuesta del RAG
trae un importe, se rehace con `sin_precio=True`. Aquí se fija que `_rag_answer` solo pasa `sin_precio` cuando se
pide (la llamada de siempre no cambia, ni su huella del RAG adelantado).
"""

import pytest

from src.agents import conversational_core as core
from src.agents import supervisor
from src.flows.state import ConversationState


@pytest.mark.asyncio
@pytest.mark.parametrize("sin_precio", [False, True])
async def test_rag_answer_pasa_sin_precio_solo_si_se_pide(monkeypatch, sin_precio):
    llamadas = []

    async def _rag(pregunta, **kw):
        llamadas.append(kw)
        return "respuesta"

    monkeypatch.setattr(supervisor, "rag_answer", _rag)
    st = ConversationState(conversation_id="g3-07a")
    st.language = "es"
    assert await core._rag_answer(st, "¿cuánto vale el snorkel?", history=[], sin_precio=sin_precio) == "respuesta"
    assert ("sin_precio" in llamadas[0]) is sin_precio


def test_el_importe_se_reconoce():
    assert core._IMPORTE_RE.search("cuesta 126 USD por persona")
    assert core._IMPORTE_RE.search("2 × 448.000 COP")
    assert not core._IMPORTE_RE.search("incluye equipo y almuerzo")
