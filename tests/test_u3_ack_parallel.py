"""u3-1 paso 3: el acuse cálido en paralelo (flag `ack_in_parallel`).

Lo que se fija aquí:
1. con el flag apagado no se lanza nada (conducta de siempre);
2. con el flag, `_setup_phase` lanza el acuse sin esperarlo y el cierre usa ESE acuse;
3. si la pregunta pendiente es de sí/no (seguridad, certificación, nacionalidad,
   refresher) NO se lanza: su resumen necesita el valor recién extraído;
4. si la pregunta pendiente cambia entre el principio y el cierre, se descarta;
5. un acuse que nadie usa se cancela al cerrar el turno;
6. la foto se toma al lanzarlo: cambios posteriores del estado no le llegan.
"""

import asyncio

import pytest

import src.agents.conversational_core as core
from src.config import settings
from src.flows.state import ConversationState, Step


def _state(pending=None) -> ConversationState:
    s = ConversationState(conversation_id="u3-ack")
    s.language = "es"
    s.step = Step.FREE_TEXT
    s.core_pending_slot = pending
    s.history.append({"role": "user", "content": "hola"})
    return s


@pytest.fixture
def acks(monkeypatch):
    calls = []

    async def _ack(message, *, state_summary="", client_name=None, lang="es", client=None):
        calls.append({"message": message, "summary": state_summary})
        await asyncio.sleep(0.01)
        return "¡Genial!"

    monkeypatch.setattr(core, "compose_acknowledgement", _ack)
    monkeypatch.setattr(settings, "notes_in_parallel", False)
    monkeypatch.setattr(core, "_maybe_capture_notes", lambda *a, **k: asyncio.sleep(0))
    return calls


async def test_flag_apagado_no_lanza_nada(monkeypatch, acks):
    monkeypatch.setattr(settings, "ack_in_parallel", False)
    st = _state(pending=core.SLOT_LOCATION)
    await core._setup_phase(st, "desde cartagena", {})
    assert getattr(st, "_pending_ack", None) is None
    assert acks == []


async def test_con_flag_se_lanza_y_el_cierre_lo_usa(monkeypatch, acks):
    monkeypatch.setattr(settings, "ack_in_parallel", True)
    st = _state(pending=core.SLOT_LOCATION)
    await core._setup_phase(st, "desde cartagena", {})
    assert st._pending_ack is not None and len(acks) == 0  # lanzado, sin esperar
    got = await core._take_parallel_ack(st, core.SLOT_LOCATION)
    assert got == "¡Genial!" and len(acks) == 1


@pytest.mark.parametrize("slot", sorted(core._JUST_ANSWERED_PHRASE))
async def test_preguntas_de_si_no_siguen_en_serie(monkeypatch, acks, slot):
    monkeypatch.setattr(settings, "ack_in_parallel", True)
    st = _state(pending=slot)
    await core._setup_phase(st, "sí", {})
    assert getattr(st, "_pending_ack", None) is None
    assert await core._take_parallel_ack(st, slot) is None  # el cierre lo calcula en serie


async def test_si_la_pregunta_pendiente_cambia_se_descarta(monkeypatch, acks):
    monkeypatch.setattr(settings, "ack_in_parallel", True)
    st = _state(pending=core.SLOT_LOCATION)
    await core._setup_phase(st, "desde cartagena", {})
    task = st._pending_ack["task"]
    assert await core._take_parallel_ack(st, core.SLOT_QTY) is None
    await asyncio.sleep(0)
    assert task.cancelled() or task.done()


async def test_un_acuse_sin_usar_se_cancela_al_cerrar(monkeypatch, acks):
    monkeypatch.setattr(settings, "ack_in_parallel", True)
    st = _state(pending=core.SLOT_LOCATION)
    await core._setup_phase(st, "desde cartagena", {})
    task = st._pending_ack["task"]
    core.cancel_pending_ack(st)
    await asyncio.sleep(0)
    assert task.cancelled()
    assert st._pending_ack is None


async def test_la_foto_se_toma_al_lanzar(monkeypatch, acks):
    monkeypatch.setattr(settings, "ack_in_parallel", True)
    st = _state(pending=core.SLOT_LOCATION)
    st.detected_activity = "snorkel"
    await core._setup_phase(st, "desde cartagena", {})
    st.detected_activity = "minicourse"  # lo que haga la extracción después
    await core._take_parallel_ack(st, core.SLOT_LOCATION)
    assert "snorkel" in acks[0]["summary"] and "minicourse" not in acks[0]["summary"]


async def test_primer_turno_no_lanza(monkeypatch, acks):
    monkeypatch.setattr(settings, "ack_in_parallel", True)
    st = _state(pending=None)
    st.step = Step.WELCOME
    await core._setup_phase(st, "hola, quiero bucear", {})
    assert getattr(st, "_pending_ack", None) is None
