"""ex-9b paso 5 (19-oct): tres preguntas nuevas de Jev en lugar de regex que "entendían" al cliente, cada una con su
flag. Si Jev contesta, manda Jev (también cuando dice que no); el regex solo decide si Jev calla.

- `reinicio_por_jev` (NUEVO_CASO): el reinicio de escenario borra toda la memoria. El regex (saludo + presentación +
  memoria) solo lo propone, y con el flag el grafo espera a Jev antes de borrar.
- `identidad_ia_por_jev` (PREGUNTA_SI_ES_IA): "¿eres un bot?".
- `idioma_por_jev` (CAMBIA_IDIOMA): el cambio de idioma a mitad de conversación."""

import pytest

from src.agents import jev_router as j
from src.agents import supervisor
from src.agents.nucleo.setup import _idioma_pedido
from src.agents.rutas.deflection import pregunta_si_es_ia
from src.config import settings
from src.flows.state import ConversationState
from src.orchestration import graph


def _estado(lang: str = "es") -> ConversationState:
    return ConversationState(conversation_id="ex9b-5-nuevas", language=lang)


# ── Jev: preguntas, señales y dudas ──────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("flag, nombre", [
    ("reinicio_por_jev", j.NUEVO_CASO), ("identidad_ia_por_jev", j.PREGUNTA_SI_ES_IA), ("idioma_por_jev", j.CAMBIA_IDIOMA),
])
def test_cada_pregunta_solo_se_hace_con_su_flag(monkeypatch, flag, nombre):
    monkeypatch.setattr(settings, flag, False)
    assert nombre not in j._questions_for_turn()
    monkeypatch.setattr(settings, flag, True)
    assert nombre in j._questions_for_turn()


def test_las_senales_viajan_tambien_en_false():
    s = j.answers_to_signals({
        j.NUEVO_CASO: {"type": "noul", "noul": 0.03},
        j.PREGUNTA_SI_ES_IA: {"type": "noul", "noul": 0.97},
        j.CAMBIA_IDIOMA: {"type": "choice", "choice": "english", "confidence": 1.0},
    })
    assert s[j.NUEVO_CASO] is False and s[j.PREGUNTA_SI_ES_IA] is True and s[j.CAMBIA_IDIOMA] == "english"


def test_el_idioma_con_poca_confianza_es_none():
    s = j.answers_to_signals({j.CAMBIA_IDIOMA: {"type": "choice", "choice": "english", "confidence": 0.4}})
    assert s[j.CAMBIA_IDIOMA] == "none"


def test_la_duda_en_estas_preguntas_no_manda_el_turno_al_router_llm():
    assert j.uncertain_answers({
        j.NUEVO_CASO: {"type": "noul", "noul": 0.5},
        j.PREGUNTA_SI_ES_IA: {"type": "noul", "noul": 0.5},
        j.CAMBIA_IDIOMA: {"type": "choice", "choice": "english", "confidence": 0.4},
    }) == []


# ── ¿Eres un bot? ────────────────────────────────────────────────────────────────────────────────────────────────────
REGULADOR = "qué modelo de regulador usan?"


@pytest.mark.parametrize("encendido, senales, es_ia", [
    (False, {j.PREGUNTA_SI_ES_IA: False}, True),  # hoy: el regex ve "qué modelo"
    (True, {j.PREGUNTA_SI_ES_IA: False}, False),  # con el flag manda Jev
    (True, {}, True),                             # Jev calla: el regex de siempre
])
def test_pregunta_si_es_ia(monkeypatch, encendido, senales, es_ia):
    monkeypatch.setattr(settings, "identidad_ia_por_jev", encendido)
    assert pregunta_si_es_ia(REGULADOR, senales) is es_ia


def test_jev_ve_la_pregunta_que_el_regex_no_ve(monkeypatch):
    monkeypatch.setattr(settings, "identidad_ia_por_jev", True)
    assert pregunta_si_es_ia("¿me atiende un robot?", {j.PREGUNTA_SI_ES_IA: True}) is True


# ── Idioma ───────────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("encendido, senales, pedido", [
    (False, {j.CAMBIA_IDIOMA: "none"}, "en"),  # hoy: "en inglés" cambia la conversación
    (True, {j.CAMBIA_IDIOMA: "none"}, None),   # con el flag manda Jev
    (True, {}, "en"),                          # Jev calla: el regex de siempre
])
def test_el_curso_en_ingles_no_cambia_el_idioma(monkeypatch, encendido, senales, pedido):
    monkeypatch.setattr(settings, "idioma_por_jev", encendido)
    assert _idioma_pedido(_estado("es"), "¿el curso es en inglés?", senales) == pedido


def test_no_cambia_si_ya_es_ese_idioma(monkeypatch):
    monkeypatch.setattr(settings, "idioma_por_jev", True)
    assert _idioma_pedido(_estado("en"), "can we continue in english please", {j.CAMBIA_IDIOMA: "english"}) is None
    assert _idioma_pedido(_estado("en"), "I don't speak spanish", {j.CAMBIA_IDIOMA: "english"}) is None
    assert _idioma_pedido(_estado("es"), "I don't speak spanish", {j.CAMBIA_IDIOMA: "english"}) == "en"


# ── Reinicio de escenario (nodo router del grafo) ────────────────────────────────────────────────────────────────────
VUELVE = "Hola buenos días, soy Ana, ya hablamos ayer, al final somos 3"


def _con_memoria() -> ConversationState:
    st = _estado()
    st.history = [{"role": "user", "content": "somos 2 y queremos bucear el sábado"},
                  {"role": "assistant", "content": "¡Genial! ¿Ya son buzos certificados?"},
                  {"role": "user", "content": "no"}, {"role": "assistant", "content": "Entonces el minicurso."}]
    st.detected_group_size = 2
    return st


@pytest.fixture
def router_sin_red(monkeypatch):
    from src.agents import conversational_core as core

    monkeypatch.setattr(core, "lanzar_rag_adelantado", lambda *a, **k: None)
    monkeypatch.setattr(core, "lanzar_extraccion_adelantada", lambda *a, **k: None)

    def poner(senales: dict):
        llamadas = []

        async def detect(message, **kw):
            llamadas.append(len(kw.get("history") or []))
            return dict(senales)

        monkeypatch.setattr(supervisor, "detect_routing_signals", detect)
        return llamadas

    return poner


@pytest.mark.parametrize("encendido, senales, borra", [
    (False, {j.NUEVO_CASO: False, "asks_question": False}, True),  # hoy: el regex borra la memoria
    (True, {j.NUEVO_CASO: False, "asks_question": False}, False),  # con el flag manda Jev
    (True, {j.NUEVO_CASO: True, "asks_question": False}, True),
    (True, {}, True),                                              # Jev calla: el regex de siempre
])
async def test_reinicio_de_escenario(monkeypatch, router_sin_red, encendido, senales, borra):
    monkeypatch.setattr(settings, "reinicio_por_jev", encendido)
    llamadas = router_sin_red(senales)
    st = _con_memoria()
    await graph._router_node({"conv_state": st, "message": VUELVE})
    assert (st.detected_group_size is None) is borra
    assert len(llamadas) == 1  # las señales se piden una sola vez
    if encendido:
        assert llamadas[0] == 4  # con el flag, Jev ve el historial de antes de borrar


async def test_sin_propuesta_del_regex_no_cambia_nada(monkeypatch, router_sin_red):
    monkeypatch.setattr(settings, "reinicio_por_jev", True)
    llamadas = router_sin_red({j.NUEVO_CASO: True, "asks_question": False})
    st = _con_memoria()
    await graph._router_node({"conv_state": st, "message": "¿a qué hora sale la lancha?"})
    assert st.detected_group_size == 2 and len(llamadas) == 1


# ── Deliberación (flag `deliberacion_por_jev`) ───────────────────────────────────────────────────────────────────────
DUDA_CON_CIFRA = "somos 3 y no tenemos claro si hacer snorkel o el minicurso"
COMPARA = {"comparing_options": {"comparing": True, "options": []}, "asks_question": False}


@pytest.mark.parametrize("encendido, senales, mensaje, delibera", [
    (False, COMPARA, DUDA_CON_CIFRA, False),                        # hoy: el veto de la cifra gana a la IA
    (True, COMPARA, DUDA_CON_CIFRA, True),                          # con el flag manda la IA
    (False, {"asks_question": False}, "no sé si buceo o snorkel", True),  # hoy: la frase de duda basta
    (True, {"asks_question": False}, "no sé si buceo o snorkel", False),  # la IA contesta y no compara
    (True, {}, "no sé si buceo o snorkel", True),                   # la IA calla: la frase de duda, como hoy
    (True, COMPARA, "quiero el minicurso", False),                  # una sola oferta nunca es deliberación
])
def test_deliberacion(monkeypatch, encendido, senales, mensaje, delibera):
    from src.agents.nucleo.routing import _is_deliberation_between_options

    monkeypatch.setattr(settings, "deliberacion_por_jev", encendido)
    assert _is_deliberation_between_options(mensaje, senales) is delibera
