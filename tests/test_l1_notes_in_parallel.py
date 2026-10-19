"""l1-4: la captura de notas se calcula EN PARALELO, sin retrasar la respuesta.

Qué cuesta: el nodo `setup` (donde viven las notas) va a p50 0,748 s / p95 1,266 s
sobre 90 turnos (`docs/robustness/snapshots/2026-09-23-core-l11-B1.json`), de un
turno de ~4,2 s, y no hace ninguna otra llamada al LLM. Esa es la ganancia.

Por qué en paralelo y no "después de responder": las notas entran en
`_build_extra_context`, el contexto del RAG. Retrasarlas dejaría la respuesta de
ESE turno sin la nota de ESE mensaje — cambiaría la conducta. Lanzándolas al
principio y esperándolas justo antes de quien las usa, el bot responde igual y el
tiempo se esconde detrás del router (1,4 s) y la extracción (1,0 s).

Lo que se fija aquí (el flag `notes_in_parallel` se quitó en s4-25: en paralelo es lo de siempre):
1. (era: con el flag OFF se esperaba en `setup`; ese camino ya no existe);
2. `_setup_phase` NO espera: deja la tarea viva;
3. `await_pending_notes` la completa, es idempotente y **la nota acaba en el estado**
   (que es lo que garantiza que el RAG y el guardado la vean);
4. la tarea NUNCA se serializa a Redis;
5. si la captura falla, el turno no se cae.
"""

import asyncio
from dataclasses import asdict

import pytest

import src.agents.conversational_core as core
from src.agents.nucleo import setup as core_setup
from src.flows.state import ConversationState


def _state() -> ConversationState:
    s = ConversationState(conversation_id="l1-4")
    s.language = "es"
    return s


@pytest.mark.asyncio
async def test_setup_no_espera_pero_deja_la_tarea(monkeypatch):
    """La clave de la ganancia: `setup` devuelve el control SIN haber terminado."""
    terminado = []

    async def _notas_lentas(state, message, **_):
        await asyncio.sleep(0.05)
        terminado.append(message)

    monkeypatch.setattr(core_setup, "_maybe_capture_notes", _notas_lentas)

    st = _state()
    st.history.append({"role": "user", "content": "hola"})
    await core._setup_phase(st, "tengo una lesion", {})

    assert terminado == [], "setup no debe esperar a las notas"
    assert getattr(st, "_pending_notes_task", None) is not None

    await core.await_pending_notes(st)
    assert terminado == ["tengo una lesion"], "al esperar, la nota se completa"


@pytest.mark.asyncio
async def test_la_nota_acaba_en_el_estado_antes_de_que_nadie_la_use(monkeypatch):
    """Es lo que garantiza que el RAG y el guardado vean la nota del mismo turno."""
    async def _notas(state, message, **_):
        await asyncio.sleep(0.01)
        state.remembered_facts = {**(state.remembered_facts or {}), "notes": ["lesion en la rodilla"]}

    monkeypatch.setattr(core_setup, "_maybe_capture_notes", _notas)

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
    async def _notas(state, message, **_):
        pass

    monkeypatch.setattr(core_setup, "_maybe_capture_notes", _notas)

    st = _state()
    st.history.append({"role": "user", "content": "hola"})
    await core._setup_phase(st, "tengo una lesion", {})

    assert "_pending_notes_task" not in asdict(st)
    await core.await_pending_notes(st)


@pytest.mark.asyncio
async def test_si_la_captura_falla_el_turno_no_se_cae(monkeypatch):
    async def _explota(state, message, **_):
        raise RuntimeError("el LLM de notas ha fallado")

    monkeypatch.setattr(core_setup, "_maybe_capture_notes", _explota)

    st = _state()
    st.history.append({"role": "user", "content": "hola"})
    await core._setup_phase(st, "tengo una lesion", {})
    await core.await_pending_notes(st)  # no debe lanzar


# --- La carrera del A/B del 23-sep (HISTORY 0.29.13) ------------------------------
# En paralelo, la tarea no arranca hasta que el turno espera algo. En los turnos sin
# más llamadas al LLM eso es el final del turno, cuando las fases ya han metido la
# respuesta del BOT en `state.history`: `extract_notes` la leía y sacaba notas de
# ella. La foto se toma en `_setup_phase`, antes de lanzar la tarea.


def _fake_extract(recibido: list, notas: list[str]):
    async def _extract(message, *, history, existing_notes, lang):
        recibido.append({"history": list(history), "existing": list(existing_notes), "lang": lang})
        return notas
    return _extract


@pytest.mark.asyncio
async def test_en_paralelo_las_notas_no_ven_la_respuesta_del_bot(monkeypatch):
    recibido = []
    monkeypatch.setattr(core, "extract_notes", _fake_extract(recibido, []))

    st = _state()
    await core._setup_phase(st, "tengo una lesion en la rodilla", {})
    # Lo que hacen las fases del turno antes de que la tarea llegue a arrancar:
    st.history.append({"role": "assistant", "content": "el enlace no te ha funcionado"})
    await core.await_pending_notes(st)

    assert len(recibido) == 1
    roles = [m["role"] for m in recibido[0]["history"]]
    assert "assistant" not in roles, "la nota debe calcularse sobre lo mismo que en serie"
    assert recibido[0]["history"][-1]["content"] == "tengo una lesion en la rodilla"


@pytest.mark.asyncio
async def test_en_paralelo_lee_lo_mismo_que_en_serie(monkeypatch):
    """`extract_notes` recibe lo que había al terminar `setup`, que es lo que leía el camino en serie (quitado en
    s4-25; hasta entonces este test comparaba los dos caminos)."""
    recibido = []
    monkeypatch.setattr(core, "extract_notes", _fake_extract(recibido, []))
    st = _state()
    st.remembered_facts = {"notes": ["luna de miel"]}
    st.history.append({"role": "user", "content": "hola"})
    st.history.append({"role": "assistant", "content": "hola, ¿en qué te ayudo?"})
    await core._setup_phase(st, "tengo una lesion en la rodilla", {})
    st.history.append({"role": "assistant", "content": "respuesta del turno"})
    await core.await_pending_notes(st)
    assert recibido == [{
        "history": [{"role": "user", "content": "hola"},
                    {"role": "assistant", "content": "hola, ¿en qué te ayudo?"},
                    {"role": "user", "content": "tengo una lesion en la rodilla"}],
        "existing": ["luna de miel"],
        "lang": "es",
    }]


@pytest.mark.asyncio
async def test_en_paralelo_la_nota_se_suma_al_estado_actual(monkeypatch):
    """Si el turno escribe notas mientras la tarea corre, no se pisan."""
    monkeypatch.setattr(core, "extract_notes", _fake_extract([], ["lesion en la rodilla"]))

    st = _state()
    await core._setup_phase(st, "tengo una lesion en la rodilla", {})
    st.remembered_facts = {"notes": ["es su luna de miel"], "otro": 1}
    await core.await_pending_notes(st)

    assert st.remembered_facts["notes"] == ["es su luna de miel", "lesion en la rodilla"]
    assert st.remembered_facts["otro"] == 1
