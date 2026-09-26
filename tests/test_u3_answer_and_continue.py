"""u3-4: "contesta y sigue" (flag `answer_and_continue`).

Lo que se fija aquí:
1. el flag nace apagado y, apagado, Jev no recibe la pregunta nueva;
2. con "?" y un dato en el mismo mensaje: se contesta Y el dato se guarda (antes se
   perdía y se volvía a pedir);
   Los datos de un turno con pregunta los lee el LLM, no el regex (escalón 0: el regex
   lee palabras sueltas de la pregunta como si fueran datos);
3. sin "?" y sin que el regex la vea, con `asks_question` de Jev: se contesta Y la
   reserva sigue (antes la pregunta se perdía si la reserva avanzaba);
4. el "¿me recuerdas...?" sigue con su respuesta fija y la respuesta del RAG se cancela;
5. si el RAG falla, el turno sigue con la reserva;
6. el RAG recibe la foto del historial tomada al lanzarlo;
7. la duda de Jev en `asks_question` no manda el turno al router LLM, y su respuesta
   viaja también cuando Jev duda en las señales del router.
"""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from src.agents import conversational_core as core
from src.agents import escalation, jev_router, supervisor
from src.agents.supervisor import route_message
from src.config import Settings, settings
from src.flows.state import ConversationState


def _state() -> ConversationState:
    s = ConversationState(conversation_id="u3-4")
    s.language = "es"
    return s


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr(core, "fill_gaps", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "detect_special_signals", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "resolve_slot_answer", AsyncMock(return_value={}))
    monkeypatch.setattr(core, "extract_notes", AsyncMock(return_value=[]))
    monkeypatch.setattr(core, "compose_acknowledgement", AsyncMock(return_value=""))
    monkeypatch.setattr(settings, "notes_in_parallel", False)
    monkeypatch.setattr(settings, "ack_in_parallel", False)


@pytest.fixture
def signals(monkeypatch):
    """Las señales del router que 've' este turno (por defecto ninguna)."""
    box = {"value": {}}

    async def _detect(message, **_k):
        return dict(box["value"])

    monkeypatch.setattr(supervisor, "detect_routing_signals", _detect)
    return box


@pytest.fixture
def rag(monkeypatch):
    calls = []

    async def _rag(message, **kwargs):
        calls.append({"message": message, "history": list(kwargs.get("history") or [])})
        return "RESPUESTA_RAG"

    monkeypatch.setattr(supervisor, "rag_answer", _rag)
    return calls


def test_el_flag_nace_apagado():
    assert Settings().answer_and_continue is False


def test_flag_apagado_jev_no_recibe_la_pregunta(monkeypatch):
    monkeypatch.setattr(settings, "answer_and_continue", False)
    assert jev_router.ASKS_QUESTION not in jev_router._questions_for_turn()
    monkeypatch.setattr(settings, "answer_and_continue", True)
    assert jev_router.ASKS_QUESTION in jev_router._questions_for_turn()


async def test_flag_apagado_la_pregunta_con_dato_pierde_el_dato(monkeypatch, signals, rag):
    """La conducta de hoy, para que el contraste del test siguiente quede escrito."""
    monkeypatch.setattr(settings, "answer_and_continue", False)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados, desde cartagena")
    assert st.core_pending_slot == core.SLOT_QTY
    resp = await route_message(st, "somos 3, ¿qué incluye el precio?")
    assert "RESPUESTA_RAG" in resp
    assert st.detected_group_size is None
    assert st.core_pending_slot == core.SLOT_QTY


def _llm_reads(monkeypatch, message, patch):
    """El extractor LLM devuelve `patch` solo para `message` (lo demás, nada)."""
    async def _fill(msg, *_a, **_k):
        return dict(patch) if msg == message else {}

    async def _combined(fields, veto_fields, msg, *_a, **_k):  # huecos + verificación, una petición
        return (dict(patch) if msg == message else {}), {}

    monkeypatch.setattr(core, "fill_gaps", _fill)
    monkeypatch.setattr(core, "extract_and_verify", _combined)


async def test_con_flag_contesta_y_guarda_el_dato(monkeypatch, signals, rag):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    _llm_reads(monkeypatch, "somos 3, ¿qué incluye el precio?", {"group_size": 3})
    st = _state()
    await route_message(st, "queremos bucear, somos certificados, desde cartagena")
    resp = await route_message(st, "somos 3, ¿qué incluye el precio?")
    assert resp.startswith("RESPUESTA_RAG")  # primero la respuesta
    assert st.detected_group_size == 3  # el dato no se pierde
    assert st.core_pending_slot == core.SLOT_SAFETY  # y la reserva sigue
    assert "2 años" in resp
    assert len(rag) == 1
    assert st.history[-1] == {"role": "assistant", "content": resp}


async def test_con_flag_y_jev_contesta_sin_interrogacion(monkeypatch, signals, rag):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")
    assert st.core_pending_slot == core.SLOT_LOCATION
    signals["value"] = {"asks_question": True}
    resp = await route_message(st, "desde cartagena, y me cuentas lo de los hoteles")
    assert resp.startswith("RESPUESTA_RAG")
    assert st.location == "cartagena" or st.detected_location == "cartagena"
    assert st.core_pending_slot == core.SLOT_QTY


async def test_en_una_pregunta_el_regex_no_escribe_datos(monkeypatch, signals, rag, verificador):
    """"¿me recomiendas un hotel en Rosario?" no dice que se aloje allí: el regex leería
    location=island; el LLM (aquí, que se abstiene) es quien decide.

    El `verificador` NO estaba y el test dependía de una llamada de verdad: con la clave
    real del `.env` el LLM se abstenía y pasaba, y con la clave falsa de `.env.ci` (401)
    fallaba. Lo que el test quiere fijar es la conducta CUANDO el LLM se abstiene, no si la
    API responde — ver `test_si_el_llm_no_contesta_no_se_tira_nada` para el otro caso.
    """
    monkeypatch.setattr(settings, "answer_and_continue", True)
    _calls, box = verificador
    box["afirma"] = {}  # el LLM se abstiene: nadie afirma la ubicación
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")
    resp = await route_message(st, "do you have any hotel in Rosario you recommend?")
    assert resp.startswith("RESPUESTA_RAG")
    assert st.location is None and st.detected_location is None
    assert st.core_pending_slot == core.SLOT_LOCATION


async def test_sin_pregunta_no_se_lanza_nada(monkeypatch, signals, rag):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")
    resp = await route_message(st, "desde cartagena")
    assert rag == [] and "RESPUESTA_RAG" not in resp


async def test_recordar_sigue_con_su_respuesta_fija(monkeypatch, signals, rag):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    monkeypatch.setattr(core, "detect_special_signals", AsyncMock(return_value={"recall_field": "group_size"}))
    st = _state()
    await route_message(st, "quiero bucear, soy certificado, desde cartagena, somos 2")
    resp = await route_message(st, "¿cuántos te dije que éramos?")
    assert "RESPUESTA_RAG" not in resp
    assert "2" in resp
    assert getattr(st, "_pending_answer", None) is None


async def test_si_el_rag_falla_la_reserva_sigue(monkeypatch, signals):
    monkeypatch.setattr(settings, "answer_and_continue", True)

    async def _boom(message, **_k):
        raise RuntimeError("rag caído")

    monkeypatch.setattr(supervisor, "rag_answer", _boom)
    _llm_reads(monkeypatch, "somos 3, ¿qué incluye el precio?", {"group_size": 3})
    st = _state()
    await route_message(st, "queremos bucear, somos certificados, desde cartagena")
    resp = await route_message(st, "somos 3, ¿qué incluye el precio?")
    assert st.detected_group_size == 3
    assert "2 años" in resp


async def test_el_rag_ve_la_foto_del_historial(monkeypatch, rag):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    st = _state()
    st.history.append({"role": "user", "content": "¿qué incluye?"})
    core._maybe_launch_answer(st, "¿qué incluye?", {})
    st.history.append({"role": "assistant", "content": "algo escrito después"})
    assert await core._take_parallel_answer(st) == "RESPUESTA_RAG"
    assert rag[0]["history"] == [{"role": "user", "content": "¿qué incluye?"}]


async def test_una_respuesta_sin_usar_se_cancela(monkeypatch):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    started = asyncio.Event()

    async def _slow(message, **_k):
        started.set()
        await asyncio.sleep(10)
        return "tarde"

    monkeypatch.setattr(supervisor, "rag_answer", _slow)
    st = _state()
    core._maybe_launch_answer(st, "¿qué incluye?", {})
    task = st._pending_answer
    await started.wait()
    core.cancel_pending_answer(st)
    await asyncio.sleep(0)
    assert task.cancelled() and st._pending_answer is None


def test_saludo_no_es_pregunta():
    assert core._turn_has_question("hola, ¿qué tal?", {"asks_question": True}) is False
    assert core._turn_has_question("perfecto, como pago", {"asks_question": True}) is True
    assert core._turn_has_question("perfecto, como pago", {}) is False


def test_la_duda_en_asks_question_no_manda_al_router_llm():
    answers = {jev_router.ASKS_QUESTION: {"type": "noul", "noul": 0.5}, "wants_human": {"type": "noul", "noul": 0.0}}
    assert jev_router.uncertain_answers(answers) == []


def _mock_http(monkeypatch, answers):
    sent = {}

    def handler(request: httpx.Request):
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"answers": answers})

    monkeypatch.setattr(jev_router, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-test")
    return sent


async def test_jev_marca_la_pregunta_en_las_senales(monkeypatch):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    monkeypatch.setattr(settings, "jev_router_enabled", True)
    sent = _mock_http(monkeypatch, {jev_router.ASKS_QUESTION: {"type": "noul", "noul": 0.92}})
    got = await escalation.detect_routing_signals("perfecto, como pago")
    assert got == {"asks_question": True}
    assert jev_router.ASKS_QUESTION in sent["questions"]


async def test_por_debajo_de_07_no_es_pregunta(monkeypatch):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    monkeypatch.setattr(settings, "jev_router_enabled", True)
    _mock_http(monkeypatch, {jev_router.ASKS_QUESTION: {"type": "noul", "noul": 0.65}})
    assert await escalation.detect_routing_signals("desde cartagena") == {}


async def test_si_jev_duda_en_el_router_la_pregunta_viaja_igual(monkeypatch):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    monkeypatch.setattr(settings, "jev_router_enabled", True)
    _mock_http(monkeypatch, {
        jev_router.ASKS_QUESTION: {"type": "noul", "noul": 0.9},
        "wants_human": {"type": "noul", "noul": 0.5},  # duda -> router LLM
    })

    class _NoTool:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**_k):
                    raise RuntimeError("sin LLM en tests")

    monkeypatch.setattr(escalation, "AsyncOpenAI", lambda **_k: _NoTool())
    monkeypatch.setattr(escalation, "trace_openai", lambda c: c)
    got = await escalation.detect_routing_signals("perfecto, como pago")
    assert got == {"asks_question": True}


# ── Arreglo 1 (25-sep): si el RAG no sabe, su respuesta va SOLA ──────────────
#
# Regresión leída en el escalón 1 del 24-sep: el RAG contestaba "eso no lo tengo a
# la mano, ¿te paso con un asesor?" y detrás se le pegaba "¿desde dónde saldrías?".
# El cliente recibía DOS preguntas y la segunda tapaba la oferta de asesor. El
# camino antiguo (`_answer_question`) no encadenaba nada cuando la respuesta ya
# acababa preguntando; al mover esto a `_slotfill_close_phase` se relajó a "solo si
# el siguiente paso es el menú de actividades" y el caso se coló.


@pytest.fixture
def rag_sin_respuesta(monkeypatch):
    """El RAG devuelve su fallback de "no lo tengo a la mano"."""
    from src.agents.rag_agent import FALLBACK_ES

    async def _rag(message, **_kwargs):
        return FALLBACK_ES

    monkeypatch.setattr(supervisor, "rag_answer", _rag)
    return FALLBACK_ES


async def test_si_el_rag_no_sabe_no_se_pega_la_pregunta_de_la_reserva(
    monkeypatch, signals, rag_sin_respuesta
):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")
    assert st.core_pending_slot == core.SLOT_LOCATION

    resp = await route_message(st, "¿tenéis convenio con alguna aerolínea?")

    assert rag_sin_respuesta in resp
    assert "¿desde dónde" not in resp.lower() and "saldrías" not in resp.lower(), (
        "dos preguntas en el mismo mensaje: la de la reserva tapa la oferta de asesor"
    )
    # La reserva no se pierde: sigue pendiente para el turno siguiente, igual que
    # hacía el camino antiguo.
    assert st.core_pending_slot == core.SLOT_LOCATION
    assert st.history[-1] == {"role": "assistant", "content": resp}


async def test_si_el_rag_si_sabe_la_pregunta_de_la_reserva_sigue_yendo_detras(
    monkeypatch, signals, rag
):
    """Control del test anterior: el arreglo 1 NO puede cargarse el "y sigue" de
    u3-4, que es justo lo que aporta. Sin él, el test de arriba pasaría aunque la
    pregunta de la reserva no se encadenara nunca."""
    monkeypatch.setattr(settings, "answer_and_continue", True)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")

    resp = await route_message(st, "¿qué incluye el precio?")

    assert resp.startswith("RESPUESTA_RAG")
    assert len(resp) > len("RESPUESTA_RAG") + 10, "falta la parte de la reserva"
    assert st.core_pending_slot == core.SLOT_LOCATION


def test_el_fallback_se_reconoce_desde_un_solo_sitio():
    """`rag_agent.is_fallback_answer` es la única comprobación: antes el patrón
    `FALLBACK_ES in x or FALLBACK_EN in x` estaba copiado en el núcleo (comparación
    desde catálogo), en el supervisor (métrica de negocio de m0-5) y habría hecho
    falta un cuarto aquí."""
    from src.agents.rag_agent import FALLBACK_EN, FALLBACK_ES, is_fallback_answer

    assert is_fallback_answer(FALLBACK_ES)
    assert is_fallback_answer(FALLBACK_EN)
    assert is_fallback_answer(f"¡Hola! {FALLBACK_EN}\n\nOtra cosa"), "debe valer concatenado"
    assert not is_fallback_answer("El plan de 2 inmersiones cuesta 178 USD.")
    assert not is_fallback_answer("")
    assert not is_fallback_answer(None)


# ── Arreglo 2 (25-sep): en un turno con pregunta, el regex LEE y el LLM VERIFICA ──
#
# Regresión leída en el escalón 1 del 24-sep: la primera versión borraba lo que leía el
# regex y dejaba al LLM RELLENAR esos campos. Pero rellenar es una pregunta abierta e
# invita a suponer: "Transportation to rosario is included, in case I decided to do the
# Open Water course?" guardaba location=island, y dos turnos después el RAG decía "como
# ya estás en las islas, tu punto de encuentro es el hotel".
#
# Ahora el regex conserva lo que leyó, el LLM lo VERIFICA (pregunta cerrada: "¿el cliente
# AFIRMA esto?") y no se rellena ningún hueco ese turno.


@pytest.fixture
def verificador(monkeypatch):
    """El LLM que verifica en un turno con pregunta. Con `as_answers` devuelve su
    respuesta TAL CUAL: `box["afirma"]` es lo que el cliente afirma segun el LLM.
    Un campo que NO este ahi es un campo que nadie afirmo (y se cae)."""
    calls = []
    box = {"afirma": {}}

    async def _verify(fields, message, values, **kwargs):
        calls.append({"fields": list(fields), "message": message, "values": dict(values)})
        if kwargs.get("as_answers"):
            return {f: v for f, v in box["afirma"].items() if f in fields}
        return {}

    monkeypatch.setattr(core, "verify_fields", _verify)
    return calls, box


@pytest.fixture
def no_rellena(monkeypatch):
    """Cuenta si alguien pide rellenar huecos. En un turno con pregunta debe ser 0."""
    calls = []

    async def _fill(message, *_a, **_k):
        calls.append(message)
        return {}

    async def _combined(fields, veto_fields, message, *_a, **_k):
        calls.append(message)
        return {}, {}

    monkeypatch.setattr(core, "fill_gaps", _fill)
    monkeypatch.setattr(core, "extract_and_verify", _combined)
    return calls


async def test_en_un_turno_con_pregunta_no_se_rellenan_huecos(
    monkeypatch, signals, rag, verificador, no_rellena
):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")
    no_rellena.clear()

    await route_message(st, "¿me recomiendas un hotel en Rosario?")

    assert no_rellena == [], (
        "rellenar es una pregunta abierta al LLM e invita a suponer: en un turno con "
        "pregunta solo se verifica lo que el cliente afirma"
    )


async def test_lo_que_el_cliente_afirma_se_verifica_y_se_guarda(
    monkeypatch, signals, rag, verificador, no_rellena
):
    """"reservaremos hotel en la isla" SÍ es un dato: el regex lo lee y el LLM lo confirma
    (no discrepa), así que se guarda."""
    monkeypatch.setattr(settings, "answer_and_continue", True)
    calls, box = verificador
    box["afirma"] = {"location": "island"}
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")

    await route_message(st, "reservaremos hotel en la isla, ¿el transporte está incluido?")

    assert calls, "el turno con pregunta tiene que pasar por la verificación"
    assert "location" in calls[-1]["fields"], "se verifica lo que leyó el regex"
    assert (st.location or st.detected_location) == "island"


async def test_si_el_llm_dice_que_no_lo_afirma_el_dato_no_se_guarda(
    monkeypatch, signals, rag, verificador, no_rellena
):
    """La hipótesis del escalón 1: "in case I decided to..." no es un dato. El regex lo
    lee, el LLM discrepa y el valor se cae."""
    monkeypatch.setattr(settings, "answer_and_continue", True)
    calls, box = verificador
    box["afirma"] = {}  # no lo afirma nadie
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")

    await route_message(
        st, "is transportation to rosario included, in case I decided to do the course?"
    )

    assert calls, "tiene que haberse consultado"
    assert st.location is None and st.detected_location is None


async def test_lo_que_no_se_puede_verificar_no_se_guarda(monkeypatch, signals, rag, verificador):
    """`hotel`/`island`/`ages`/`last_dive_over_2_years` no tienen verificador en
    `_VETO_FIELD_SPECS`. La regla del arreglo es "solo lo que el cliente afirma Y el LLM
    confirma": si no se puede confirmar, no se guarda."""
    from src.agents import supervisor

    verificables = set(supervisor._VETO_FIELD_SPECS)
    assert "hotel" not in verificables and "island" not in verificables

    monkeypatch.setattr(settings, "answer_and_continue", True)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")

    await route_message(st, "¿me podéis recoger en el hotel Pao Pao?")

    assert st.hotel is None, "un hotel nombrado dentro de una pregunta no es dónde se aloja"


async def test_sin_pregunta_se_siguen_rellenando_huecos(monkeypatch, signals, rag, no_rellena):
    """Control: el arreglo 2 solo toca los turnos CON pregunta. Sin este test, los de
    arriba pasarían aunque hubiéramos apagado el relleno en todos los turnos."""
    monkeypatch.setattr(settings, "answer_and_continue", True)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")
    no_rellena.clear()

    await route_message(st, "somos 3")

    assert no_rellena, "en un turno normal se siguen pidiendo los huecos"


# --- La pregunta que faltaba: ¿lo AFIRMA o solo lo NOMBRA en su pregunta? (u3-4, 25-sep) ---
# Verificar no bastaba: `verify_fields` vuelve a EXTRAER, y para un extractor "¿me recomiendas
# hoteles en la isla?" es una señal clara de `location=island`. La contesta Jev, en la misma
# llamada del router. Medida y por qué: `docs/robustness/u3-4-diseno.md`.


def test_flag_apagado_jev_no_recibe_las_preguntas_de_afirmacion(monkeypatch):
    monkeypatch.setattr(settings, "answer_and_continue", False)
    preguntas = jev_router._questions_for_turn()
    assert jev_router.AFFIRMS_LOCATION not in preguntas
    assert jev_router.AFFIRMS_ACTIVITY not in preguntas
    monkeypatch.setattr(settings, "answer_and_continue", True)
    preguntas = jev_router._questions_for_turn()
    assert jev_router.AFFIRMS_LOCATION in preguntas
    assert jev_router.AFFIRMS_ACTIVITY in preguntas


def test_la_afirmacion_viaja_tambien_en_falso():
    """`False` ("Jev dice que NO lo afirma") y ausente ("no lo sé") son cosas distintas y el
    núcleo las trata distinto: sin esto, la duda y la negación se confundirían."""
    alto = jev_router.answers_to_signals({
        jev_router.AFFIRMS_LOCATION: {"type": "noul", "noul": 0.97},
    })
    bajo = jev_router.answers_to_signals({
        jev_router.AFFIRMS_LOCATION: {"type": "noul", "noul": 0.08},
    })
    assert alto[jev_router.AFFIRMS_LOCATION] is True
    assert bajo[jev_router.AFFIRMS_LOCATION] is False, "tiene que salir, no omitirse"
    assert jev_router.AFFIRMS_LOCATION not in jev_router.answers_to_signals({})


def test_la_duda_en_la_afirmacion_no_manda_el_turno_al_router_llm():
    """Mismo trato que `asks_question`: no es una señal del router."""
    medio = {
        jev_router.AFFIRMS_LOCATION: {"type": "noul", "noul": 0.5},
        jev_router.AFFIRMS_ACTIVITY: {"type": "noul", "noul": 0.45},
        jev_router.ACTIVITY_HYPOTHESIS: {"type": "noul", "noul": 0.5},
    }
    assert jev_router.uncertain_answers(medio) == []


def test_con_el_flag_jev_recibe_tambien_la_pregunta_de_hipotesis(monkeypatch):
    monkeypatch.setattr(settings, "answer_and_continue", False)
    assert jev_router.ACTIVITY_HYPOTHESIS not in jev_router._questions_for_turn()
    monkeypatch.setattr(settings, "answer_and_continue", True)
    assert jev_router.ACTIVITY_HYPOTHESIS in jev_router._questions_for_turn()


@pytest.mark.parametrize("p_afirma, p_hipotesis, esperado", [
    (0.93, 0.05, True),    # seguro de que la afirma ("Yo soy open y me gustaría salir un día…")
    (0.66, 0.17, True),    # bastante probable y sin pinta de hipótesis ("regalarle una experiencia de buceo")
    (0.66, 0.60, False),   # probable, pero con pinta de hipótesis → la conducta prudente
    (0.35, 0.75, False),   # "is it possible for my son a PADI certificate?"
    (0.35, 0.05, False),   # poco probable aunque no parezca hipótesis
    (0.55, None, False),   # sin la pregunta de hipótesis solo vale la afirmación segura
])
def test_regla_de_actividad_afirmada(p_afirma, p_hipotesis, esperado):
    assert jev_router.activity_affirmed(p_afirma, p_hipotesis) is esperado


def test_la_actividad_la_deciden_las_dos_preguntas():
    """26-sep: la afirmativa sola tiraba actividades dichas de verdad (0,66 en "quería
    regalarle a mi esposo una experiencia de buceo"); con la de hipótesis baja, se queda."""
    sin_hipotesis = jev_router.answers_to_signals({
        jev_router.AFFIRMS_ACTIVITY: {"type": "noul", "noul": 0.66},
    })
    con_hipotesis_baja = jev_router.answers_to_signals({
        jev_router.AFFIRMS_ACTIVITY: {"type": "noul", "noul": 0.66},
        jev_router.ACTIVITY_HYPOTHESIS: {"type": "noul", "noul": 0.17},
    })
    assert sin_hipotesis[jev_router.AFFIRMS_ACTIVITY] is False
    assert con_hipotesis_baja[jev_router.AFFIRMS_ACTIVITY] is True
    assert jev_router.ACTIVITY_HYPOTHESIS not in con_hipotesis_baja, "no es una señal para el núcleo"


async def test_si_jev_dice_que_no_lo_afirma_el_dato_se_cae_sin_preguntar_al_llm(
    monkeypatch, signals, rag, verificador, no_rellena
):
    """El caso del escalón 0 que el verificador NO arreglaba: el regex lee `island`, el
    verificador lo CONFIRMA (vuelve a extraer, y la isla está en la frase) y el dato inventado
    sobrevivía. Jev dice que no lo afirma → se cae, y encima se ahorra la verificación.

    El contraste se hace con **el mismo mensaje** a los dos lados: si se usaran mensajes
    distintos, la diferencia podría venir del mensaje y no de la señal, y el test pasaría sin
    probar nada.
    """
    monkeypatch.setattr(settings, "answer_and_continue", True)
    calls, box = verificador
    box["afirma"] = {"location": "island"}  # el verificador SÍ lo confirmaría: da igual
    msg = "¿el transporte está incluido si nos quedamos en la isla?"

    signals["value"] = {}  # -- lado A: sin la respuesta de Jev, la conducta de antes
    antes = _state()
    await route_message(antes, "queremos bucear, somos certificados")
    await route_message(antes, msg)
    assert (antes.location or antes.detected_location) == "island", (
        "el control: sin Jev el dato SÍ se guardaba (si no, el test de abajo no prueba nada)"
    )

    calls.clear()
    signals["value"] = {"affirms_location": False}  # -- lado B: Jev dice que no lo afirma
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")
    await route_message(st, msg)

    assert st.location is None and st.detected_location is None
    assert all("location" not in c["fields"] for c in calls), "no hace falta verificar lo descartado"


async def test_si_jev_dice_que_si_lo_afirma_el_dato_sigue_su_camino(
    monkeypatch, signals, rag, verificador, no_rellena
):
    """Control del test anterior: sin él pasaría igual con un mecanismo que borrase SIEMPRE."""
    monkeypatch.setattr(settings, "answer_and_continue", True)
    calls, box = verificador
    box["afirma"] = {"location": "island"}
    signals["value"] = {"affirms_location": True}
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")

    await route_message(st, "reservaremos hotel en la isla, ¿el transporte está incluido?")

    assert (st.location or st.detected_location) == "island"
    assert any("location" in c["fields"] for c in calls), "se sigue verificando el valor"


async def test_si_jev_no_contesta_se_sigue_con_la_conducta_de_hoy(
    monkeypatch, signals, rag, verificador, no_rellena
):
    """Jev apagado, o dudó en una señal del router: la respuesta no llega. AUSENTE no es
    `False` — se verifica como antes, en vez de tirar el dato."""
    monkeypatch.setattr(settings, "answer_and_continue", True)
    calls, box = verificador
    box["afirma"] = {"location": "island"}
    signals["value"] = {}  # ninguna afirmación en las señales
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")

    await route_message(st, "reservaremos hotel en la isla, ¿el transporte está incluido?")

    assert (st.location or st.detected_location) == "island"
    assert any("location" in c["fields"] for c in calls)


async def test_si_el_llm_no_contesta_no_se_tira_nada(monkeypatch, signals, rag, no_rellena):
    """El otro lado del contrato defensivo: si la verificación FALLA (API caída, 401, red),
    `verify_fields` devuelve `None` y no se toca nada — un corte de red no puede tirar datos
    buenos. El precio es que el dato hipotético sobrevive ese turno, y es a propósito.

    Con Jev contestando no hace falta llegar aquí: su `False` descarta el campo sin LLM (ver
    `test_si_jev_dice_que_no_lo_afirma_el_dato_se_cae_sin_preguntar_al_llm`), así que el
    mecanismo nuevo cubre también el turno degradado.
    """
    monkeypatch.setattr(settings, "answer_and_continue", True)

    async def _falla(*_a, **kwargs):
        return None if kwargs.get("as_answers") else {}

    monkeypatch.setattr(core, "verify_fields", _falla)
    st = _state()
    await route_message(st, "queremos bucear, somos certificados")

    await route_message(st, "¿el transporte está incluido si nos quedamos en la isla?")

    assert (st.location or st.detected_location) == "island", (
        "con la verificación caída se conserva lo que leyó el regex, no se tira"
    )


# ---------------------------------------------------------------------------
# u3-5 (26-sep): la misma puerta para certificado, grupo y nacionalidad, y el
# "¿lo cambio?" fantasma de la ronda B2 ("listo, como pago").
# ---------------------------------------------------------------------------


def test_con_el_flag_jev_recibe_las_preguntas_de_u35(monkeypatch):
    nuevas = (jev_router.AFFIRMS_CERTIFICATION, jev_router.AFFIRMS_GROUP, jev_router.AFFIRMS_NATIONALITY)
    monkeypatch.setattr(settings, "answer_and_continue", False)
    assert not any(q in jev_router._questions_for_turn() for q in nuevas)
    monkeypatch.setattr(settings, "answer_and_continue", True)
    assert all(q in jev_router._questions_for_turn() for q in nuevas)
    assert jev_router.uncertain_answers({q: {"type": "noul", "noul": 0.5} for q in nuevas}) == []


def test_las_senales_de_u35_viajan_tambien_en_falso():
    out = jev_router.answers_to_signals({
        jev_router.AFFIRMS_CERTIFICATION: {"type": "noul", "noul": 0.03},
        jev_router.AFFIRMS_GROUP: {"type": "noul", "noul": 0.92},
        jev_router.AFFIRMS_NATIONALITY: {"type": "noul", "noul": 0.10},
    })
    assert out["affirms_certification"] is False
    assert out["affirms_group"] is True
    assert out["affirms_nationality"] is False


def _con_pregunta(st, afirma):
    """Estado de un turno con pregunta: respuesta en marcha + lo que dijo Jev."""
    loop = asyncio.get_event_loop()
    st._pending_answer = loop.create_future()
    st._answer_affirms = afirma
    return st


async def test_el_lo_cambio_fantasma_se_descarta_si_jev_dice_que_no_lo_afirma():
    """Ronda B2: "listo, como pago" -> la revisión de datos guardados dice "no certificado" ->
    "¿lo cambio?". Con Jev diciendo que el mensaje no habla de certificación, no se pregunta."""
    st = _con_pregunta(_state(), {"is_certified": False})
    st.is_certified = True
    intent = core._detector.detect("listo, como pago", st)
    core._route_contradictions(st, "listo, como pago", intent, {"is_certified": False})
    assert not st.pending_correction
    assert st.is_certified is True


async def test_sin_turno_con_pregunta_la_contradiccion_se_confirma_como_siempre():
    """Control: fuera del turno con pregunta (o sin la señal de Jev) no cambia nada."""
    st = _state()
    st.is_certified = True
    st._answer_affirms = {"is_certified": False}  # restos de otro turno: no cuentan
    intent = core._detector.detect("ah no, no soy certificado", st)
    core._route_contradictions(st, "ah no, no soy certificado", intent, {"is_certified": False})
    assert st.pending_correction == {"is_certified": False}


async def test_si_jev_dice_que_si_lo_afirma_la_contradiccion_se_confirma():
    st = _con_pregunta(_state(), {"is_certified": True})
    st.is_certified = True
    intent = core._detector.detect("no soy certificado, ¿qué me recomiendas?", st)
    core._route_contradictions(st, "no soy certificado, ¿qué me recomiendas?", intent, {"is_certified": False})
    assert st.pending_correction == {"is_certified": False}


async def test_la_puerta_tira_nacionalidad_y_grupo_nombrados_dentro_de_la_pregunta():
    """"¿cuál es el precio para colombianos, para 2?" no dice que sean colombianos ni cuántos van."""
    st = _con_pregunta(_state(), {"is_colombian": False, "group_size": False, "group_allocation": False})
    intent = core._detector.detect("somos colombianos y vamos 2", st)
    assert intent.is_colombian is True and intent.group_size == 2, "el regex lo lee (control)"
    core._question_turn_fields(intent, st)
    assert intent.is_colombian is None
    assert intent.group_size is None
    assert "is_colombian" not in intent.detected_fields


# ---------------------------------------------------------------------------
# u3-4 paso 3 (26-sep): relleno CON PUERTA en el turno con pregunta. Solo los
# huecos que Jev dice que el cliente afirma, y solo con el mensaje actual.
# ---------------------------------------------------------------------------


@pytest.fixture
def relleno(monkeypatch):
    """Registra cada petición de relleno (campos e historial) y contesta lo que se le diga."""
    calls, box = [], {"patch": {}}

    async def _fill(message, *_a, only_fields=None, history=None, **_k):
        calls.append({"fields": list(only_fields or []), "history": history})
        return {f: v for f, v in box["patch"].items() if f in (only_fields or [])}

    async def _combined(fields, veto_fields, message, *_a, **_k):
        calls.append({"fields": list(fields), "history": "combinada"})
        return {}, {}

    monkeypatch.setattr(core, "fill_gaps", _fill)
    monkeypatch.setattr(core, "extract_and_verify", _combined)
    return calls, box


async def test_con_el_si_de_jev_se_rellena_solo_ese_campo_y_sin_historial(
    monkeypatch, signals, rag, verificador, relleno
):
    """"costo de un fundive": el regex no lo lee y en un turno con pregunta no se rellenaba."""
    monkeypatch.setattr(settings, "answer_and_continue", True)
    calls, box = relleno
    st = _state()
    await route_message(st, "hola")
    calls.clear()
    box["patch"] = {"activity": "certified_diving"}
    signals["value"] = {"asks_question": True, "affirms_activity": True}
    await route_message(st, "quería averiguar por el costo de un fundive para este finde")
    assert calls, "tenía que pedir el relleno"
    assert all(c["fields"] == ["activity"] for c in calls), calls
    assert all(c["history"] is None for c in calls), "solo el mensaje actual: Jev no ve el historial"
    assert st.detected_activity == "certified_diving"


async def test_con_el_no_de_jev_no_se_rellena(monkeypatch, signals, rag, verificador, relleno):
    monkeypatch.setattr(settings, "answer_and_continue", True)
    calls, box = relleno
    st = _state()
    await route_message(st, "hola")
    calls.clear()
    box["patch"] = {"activity": "padi_open_water"}
    signals["value"] = {"asks_question": True, "affirms_activity": False}
    await route_message(st, "in case I decided to do the Open Water course, is transport included?")
    assert calls == []
    assert st.detected_activity is None


async def test_el_si_de_un_campo_no_abre_la_puerta_a_los_demas(monkeypatch, signals, rag, verificador, relleno):
    """Control: con el "sí" solo para la actividad, grupo y nacionalidad no viajan al relleno."""
    monkeypatch.setattr(settings, "answer_and_continue", True)
    calls, box = relleno
    st = _state()
    await route_message(st, "hola")
    calls.clear()
    box["patch"] = {"activity": "certified_diving", "group_size": 2, "is_colombian": True}
    signals["value"] = {"asks_question": True, "affirms_activity": True}
    await route_message(st, "cuánto cuesta un fundive para colombianos, para 2?")
    assert calls and all(c["fields"] == ["activity"] for c in calls), calls
    assert st.detected_group_size is None
