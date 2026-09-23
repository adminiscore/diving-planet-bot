"""l1-4: la captura de notas se calcula EN PARALELO, sin retrasar la respuesta.

Qué cuesta: el nodo `setup` (donde viven las notas) va a p50 0,748 s / p95 1,266 s
sobre 90 turnos (`docs/robustness/snapshots/2026-09-23-core-l11-B1.json`), de un
turno de ~4,2 s, y no hace ninguna otra llamada al LLM. Esa es la ganancia.

Por qué en paralelo y no "después de responder": las notas entran en
`_build_extra_context`, el contexto del RAG. Retrasarlas dejaría la respuesta de
ESE turno sin la nota de ESE mensaje — cambiaría la conducta. Lanzándolas al
principio y esperándolas justo antes de quien las usa, el bot responde igual y el
tiempo se esconde detrás del router (1,4 s) y la extracción (1,0 s).

Lo que se fija aquí:
1. con el flag OFF nada cambia (se espera en el sitio de siempre);
2. con el flag ON `_setup_phase` NO espera: deja la tarea viva;
3. `await_pending_notes` la completa, es idempotente y **la nota acaba en el estado**
   (que es lo que garantiza que el RAG y el guardado la vean);
4. la tarea NUNCA se serializa a Redis;
5. si la captura falla, el turno no se cae.
"""

import asyncio
from dataclasses import asdict

import pytest

import src.agents.conversational_core as core
from src.config import settings
from src.flows.state import ConversationState


def _state() -> ConversationState:
    s = ConversationState(conversation_id="l1-4")
    s.language = "es"
    return s


@pytest.mark.asyncio
async def test_con_el_flag_off_las_notas_se_esperan_donde_siempre(monkeypatch):
    hechas = []

    async def _notas(state, message):
        hechas.append(message)

    monkeypatch.setattr(settings, "notes_in_parallel", False)
    monkeypatch.setattr(core, "_maybe_capture_notes", _notas)

    st = _state()
    st.history.append({"role": "user", "content": "hola"})
    await core._setup_phase(st, "tengo una lesion en la rodilla", {})

    assert hechas == ["tengo una lesion en la rodilla"], "con el flag OFF se espera en setup"
    assert getattr(st, "_pending_notes_task", None) is None


@pytest.mark.asyncio
async def test_con_el_flag_on_setup_no_espera_pero_deja_la_tarea(monkeypatch):
    """La clave de la ganancia: `setup` devuelve el control SIN haber terminado."""
    terminado = []

    async def _notas_lentas(state, message):
        await asyncio.sleep(0.05)
        terminado.append(message)

    monkeypatch.setattr(settings, "notes_in_parallel", True)
    monkeypatch.setattr(core, "_maybe_capture_notes", _notas_lentas)

    st = _state()
    st.history.append({"role": "user", "content": "hola"})
    await core._setup_phase(st, "tengo una lesion", {})

    assert terminado == [], "setup no debe esperar a las notas con el flag ON"
    assert getattr(st, "_pending_notes_task", None) is not None

    await core.await_pending_notes(st)
    assert terminado == ["tengo una lesion"], "al esperar, la nota se completa"


@pytest.mark.asyncio
async def test_la_nota_acaba_en_el_estado_antes_de_que_nadie_la_use(monkeypatch):
    """Es lo que garantiza que el RAG y el guardado vean la nota del mismo turno."""
    async def _notas(state, message):
        await asyncio.sleep(0.01)
        state.remembered_facts = {**(state.remembered_facts or {}), "notes": ["lesion en la rodilla"]}

    monkeypatch.setattr(settings, "notes_in_parallel", True)
    monkeypatch.setattr(core, "_maybe_capture_notes", _notas)

    st = _state()
    st.history.append({"role": "user", "content": "hola"})
    await core._setup_phase(st, "tengo una lesion en la rodilla", {})
    await core.await_pending_notes(st)

    assert (st.remembered_facts or {}).get("notes") == ["lesion en la rodilla"]


@pytest.mark.asyncio
async def test_await_pending_notes_es_idempotente():
    st = _state()
    await core.await_pending_notes(st)          # sin tarea: no-op
    await core.await_pending_notes(st)          # dos veces: sigue sin romper


@pytest.mark.asyncio
async def test_la_tarea_nunca_se_serializa_a_redis(monkeypatch):
    """`save_state` usa `asdict()`, que solo mira campos declarados. Si alguien
    convirtiera `_pending_notes_task` en un campo del dataclass, el guardado
    explotaría al intentar serializar una Task."""
    async def _notas(state, message):
        pass

    monkeypatch.setattr(settings, "notes_in_parallel", True)
    monkeypatch.setattr(core, "_maybe_capture_notes", _notas)

    st = _state()
    st.history.append({"role": "user", "content": "hola"})
    await core._setup_phase(st, "tengo una lesion", {})

    assert "_pending_notes_task" not in asdict(st)
    await core.await_pending_notes(st)


@pytest.mark.asyncio
async def test_si_la_captura_falla_el_turno_no_se_cae(monkeypatch):
    async def _explota(state, message):
        raise RuntimeError("el LLM de notas ha fallado")

    monkeypatch.setattr(settings, "notes_in_parallel", True)
    monkeypatch.setattr(core, "_maybe_capture_notes", _explota)

    st = _state()
    st.history.append({"role": "user", "content": "hola"})
    await core._setup_phase(st, "tengo una lesion", {})
    await core.await_pending_notes(st)  # no debe lanzar
