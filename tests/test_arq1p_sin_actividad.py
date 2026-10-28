"""ARQ-1p (22-oct, flag `hechos_sin_actividad`): sin saber la actividad, la hora o la recogida, qué llevar y si hay sitio
salen de las políticas (son iguales para todas) y las escribe el escritor con los hechos (lat-9 paso 3: el del RAG, sin
búsqueda). Precio, qué incluye, edad y enlace siguen necesitando la actividad: con ellos contesta el RAG, como antes."""
import asyncio
from types import SimpleNamespace

import pytest

from src.agents import rag_agent, redactor_hechos
from src.agents.nucleo import extractor
from src.flows import hechos
from src.flows.state import ConversationState

MENSAJE = "ya reservamos, ¿a qué hora es y dónde nos recogen?"


def _conv(intenciones, **campos) -> ConversationState:
    st = ConversationState(conversation_id="arq1p", language="es")
    st.history = [{"role": "user", "content": MENSAJE}]
    st._intenciones = intenciones
    st._otra_cosa = False
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def _politica(clave):
    return hechos._politica(clave, "es")


@pytest.fixture
def redactor(monkeypatch):
    """El extractor no lee ninguna actividad; Luna contesta con el texto de las políticas que recibe."""
    hechas: list = []
    estado = {"texto": " ".join(_politica(k) for k in ("operating_hours", "meeting_point", "island_pickup_free"))}

    async def lectura(state, message):
        return {"location": None}

    async def generar(client, messages, pieza="rag_escritor"):
        hechas.append(messages)
        return SimpleNamespace(usage=SimpleNamespace(total_tokens=0),
                               choices=[SimpleNamespace(message=SimpleNamespace(content=estado["texto"]))])

    async def revisor(answer, context, lang="es"):
        return True, "ok"

    from src.agents import supervisor

    monkeypatch.setattr(extractor, "lectura_del_extractor", lectura)
    monkeypatch.setattr(rag_agent, "generar_con_respaldo", generar)
    monkeypatch.setattr(rag_agent, "_verify_grounding", revisor)  # lat-9 paso 3: escribe el escritor del RAG
    monkeypatch.setattr(supervisor, "rag_answer", rag_agent.rag_answer)
    return SimpleNamespace(hechas=hechas, estado=estado)


def test_el_horario_sin_origen_lleva_los_dos():
    [bloque] = hechos.hechos_sin_actividad(_conv(["horario"]), ["horario"])
    assert bloque["actividad"] is None
    assert _politica("operating_hours") in bloque["horario_general"]
    assert bloque["recogida"] == {"cartagena": [_politica("meeting_point")], "island": [_politica("island_pickup_free")]}


def test_con_origen_solo_el_suyo():
    [bloque] = hechos.hechos_sin_actividad(_conv(["horario"], location="island"), ["horario"])
    assert list(bloque["recogida"]) == ["island"]


def test_disponibilidad_y_que_llevar():
    [bloque] = hechos.hechos_sin_actividad(_conv([]), ["disponibilidad", "requisitos"])
    assert _politica("availability_always") in bloque["disponibilidad"]
    assert _politica("what_to_bring") in bloque["requisitos"]
    assert _politica("insurance_form_requirement") in bloque["requisitos"]


def test_lo_que_necesita_la_actividad_no_tiene_bloque_general():
    assert hechos.hechos_sin_actividad(_conv([]), ["precio", "incluye", "edad", "enlace"]) == []


def test_con_el_flag_lo_escribe_el_redactor(redactor, monkeypatch):
    from src import observability

    notas: dict = {}
    monkeypatch.setattr(observability, "note_turn", lambda **kw: notas.update(kw))
    st = _conv(["horario"])
    answer = asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history))
    assert answer == redactor.estado["texto"]
    assert notas["hechos_por_codigo"] == "redactor_general"  # se ve en [TURN_METRICS] `hechos`
    [messages] = redactor.hechas
    assert "9:30" in messages[-1]["content"] and "Bodeguita" in messages[-1]["content"]


def test_si_pide_tambien_el_precio_contesta_el_rag(redactor, monkeypatch):
    st = _conv(["horario", "precio"], ya_reservado=True)  # CALN-3 paso 2: sin reservar, el precio de los candidatos
    assert asyncio.run(redactor_hechos.responder(st, MENSAJE, st.history)) is None
    assert redactor.hechas == []
