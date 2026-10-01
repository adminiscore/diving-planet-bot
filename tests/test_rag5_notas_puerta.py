"""rag-5 (1-oct): puerta de Jev para el extractor de notas (flag `notas_puerta_jev`).

Por qué: Gonzalo midió el 30-sep que de 26 notas nuevas solo 7 eran buenas y 15 eran la pregunta del cliente
apuntada como hecho, o inventada ("how much would that be" -> "not Colombian"), aunque el prompt del extractor ya
lo prohíbe; y que son esas notas las que hacen rehacer la respuesta adelantada de rag-5. La puerta: Jev contesta
en la llamada del enrutador "¿cuenta algo del cliente que haya que apuntar?" y, si está SEGURO de que no, no se
llama al extractor. Calibrada con `scripts/sonda_notas.py`.

Lo que se fija aquí:
1. Jev seguro de que no hay nada -> no se llama al extractor;
2. Jev con duda o con algo que apuntar -> se llama, como hoy;
3. sin respuesta de Jev (apagado o falló) o con el flag apagado -> lo de siempre;
4. la pregunta va en la llamada de Jev solo con el flag, viaja como probabilidad y su duda no manda el turno al
   router LLM.
"""

import pytest

import src.agents.conversational_core as core
from src.agents import jev_router
from src.config import settings
from src.flows.state import ConversationState


def _state() -> ConversationState:
    s = ConversationState(conversation_id="rag5-notas")
    s.language = "es"
    s.history.append({"role": "user", "content": "hola"})
    return s


@pytest.fixture
def extractor(monkeypatch):
    llamadas = []

    async def _notas(state, message, **_):
        llamadas.append(message)

    monkeypatch.setattr(settings, "notes_in_parallel", False)
    monkeypatch.setattr(settings, "notas_puerta_jev", True)
    monkeypatch.setattr(core, "_maybe_capture_notes", _notas)
    return llamadas


@pytest.mark.asyncio
async def test_jev_seguro_de_que_no_hay_nada_no_se_llama_al_extractor(extractor):
    await core._setup_phase(_state(), "how much would that be", {jev_router.SHARES_OPEN_FACT: 0.03})
    assert extractor == []


@pytest.mark.asyncio
@pytest.mark.parametrize("p", [0.97, 0.27, jev_router.NOTES_SKIP_MAX])
async def test_con_algo_que_apuntar_o_con_duda_se_llama_como_hoy(extractor, p):
    await core._setup_phase(_state(), "soy epiléptica, puedo bucear?", {jev_router.SHARES_OPEN_FACT: p})
    assert extractor == ["soy epiléptica, puedo bucear?"]


@pytest.mark.asyncio
async def test_sin_respuesta_de_jev_lo_de_siempre(extractor):
    await core._setup_phase(_state(), "how much would that be", {})
    assert extractor == ["how much would that be"]


@pytest.mark.asyncio
async def test_con_el_flag_apagado_lo_de_siempre(extractor, monkeypatch):
    monkeypatch.setattr(settings, "notas_puerta_jev", False)
    await core._setup_phase(_state(), "how much would that be", {jev_router.SHARES_OPEN_FACT: 0.03})
    assert extractor == ["how much would that be"]


def test_la_pregunta_solo_va_con_el_flag(monkeypatch):
    monkeypatch.setattr(settings, "notas_puerta_jev", True)
    assert jev_router.SHARES_OPEN_FACT in jev_router._questions_for_turn()
    monkeypatch.setattr(settings, "notas_puerta_jev", False)
    assert jev_router.SHARES_OPEN_FACT not in jev_router._questions_for_turn()


def test_viaja_como_probabilidad_y_su_duda_no_manda_el_turno_al_llm():
    answers = {jev_router.SHARES_OPEN_FACT: {"type": "noul", "noul": 0.45}}
    assert jev_router.answers_to_signals(answers)[jev_router.SHARES_OPEN_FACT] == 0.45
    assert jev_router.uncertain_answers(answers) == []
