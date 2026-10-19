"""ex-7 (fase EX, flag `extraccion_llm_grupo`): cuántos van y cómo se reparten los decide el extractor.

Banco ex7 (`docs/robustness/regex/banco-ex7/banco.json`, turno de producción): "él quiere hacer snorkel" sobre buceo de
1 acababa en {snorkel: 2} (el atajo de acompañante sumaba otra vez a quien ya traía el reparto); "3 of us will dive and
3 will snorkel" sobre {buceo: 3} no se guardaba. Aquí, con el extractor simulado: el regex es pista, un reparto que solo
suma personas es un añadido, una corrección explícita se aplica, otro cambio se confirma, y "sin decidir" sigue yendo a
la recomendación de opciones.
"""
from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents.nucleo import extractor as core_extractor
from src.flows.state import ConversationState


@pytest.fixture
def ex7(monkeypatch):

    def con(datos):
        monkeypatch.setattr(core_extractor, "datos_del_extractor", AsyncMock(return_value=datos))

    return con


def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="ex7", language="es")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


async def _entender(mensaje: str, state: ConversationState | None = None) -> ConversationState:
    state = state or _estado()
    await core._understand(state, mensaje)
    return state


@pytest.mark.asyncio
async def test_el_regex_ya_no_decide_el_grupo(ex7):
    # "soy buza advanced": el regex lo leía como grupo de 1.
    ex7({"is_certified": True})
    st = await _entender("Hola! Me llamo Ana, soy buza advanced")
    assert st.detected_group_size is None


@pytest.mark.asyncio
async def test_el_reparto_lo_pone_el_extractor(ex7):
    ex7({"group_size": 6, "group_allocation": {"certified_diving": 4, "minicourse": 2}})
    st = await _entender("4 certificados y 2 minicurso")
    assert st.detected_group_size == 6
    assert st.detected_group_allocation == {"certified_diving": 4, "minicourse": 2}


@pytest.mark.asyncio
async def test_un_reparto_que_suma_personas_es_un_anadido_sin_preguntar(ex7):
    ex7({"group_size": 6, "group_allocation": {"certified_diving": 3, "snorkel": 3}})
    st = _estado(detected_activity="certified_diving", is_certified=True, detected_group_size=3)
    st = await _entender("3 of us will dive and 3 will snorkel", st)
    assert st.detected_group_size == 6
    assert st.detected_group_allocation == {"certified_diving": 3, "snorkel": 3}
    assert not st.pending_correction


@pytest.mark.asyncio
async def test_el_acompanante_no_se_cuenta_dos_veces(ex7):
    ex7({"group_allocation": {"certified_diving": 1, "snorkel": 1}})
    st = _estado(detected_activity="certified_diving", is_certified=True, detected_group_size=1)
    st = await _entender("viene también uno que hace snorkel", st)
    assert st.detected_group_allocation == {"certified_diving": 1, "snorkel": 1}
    assert st.detected_group_size == 2


@pytest.mark.asyncio
async def test_una_correccion_explicita_cambia_el_reparto(ex7):
    ex7({"group_allocation": {"certified_diving": 3, "minicourse": 3}})
    st = _estado(detected_group_size=6, detected_group_allocation={"certified_diving": 4, "minicourse": 2})
    st = await _entender("perdón, en realidad son 3 certificados y 3 minicurso", st)
    assert st.detected_group_allocation == {"certified_diving": 3, "minicourse": 3}


@pytest.mark.asyncio
async def test_otro_total_sin_correccion_se_confirma(ex7):
    ex7({"group_size": 5})
    st = _estado(detected_activity="snorkel", detected_group_size=3)
    st = await _entender("seremos 5", st)
    assert st.detected_group_size == 3
    assert (st.pending_correction or {}).get("group_size") == 5


@pytest.mark.asyncio
async def test_los_sin_decidir_van_a_la_recomendacion(ex7):
    # Decisión del owner (15-sep): "uno no está certificado" no es un minicurso; queda sin decidir y se le recomienda.
    ex7({"group_size": 3, "group_allocation": {"certified_diving": 2, "undecided": 1}})
    st = _estado(detected_activity="certified_diving", is_certified=True)
    st = await _entender("somos 3, uno no está certificado", st)
    assert st.detected_group_size == 3
    assert st.pending_undecided_qty == 1
    assert "undecided" not in (st.detected_group_allocation or {})


@pytest.mark.asyncio
async def test_una_actividad_que_no_se_nombra_queda_sin_decidir(ex7):
    # Banco ex7: el extractor le ponía snorkel o minicurso al amigo que solo "no es buzo" (decisión del owner, 15-sep).
    ex7({"group_allocation": {"certified_diving": 1, "snorkel": 1}, "is_certified": True})
    st = _estado(detected_activity="certified_diving", detected_group_size=2)
    st = await _entender("mi amigo no es buzo, yo sí", st)
    assert "snorkel" not in (st.detected_group_allocation or {})
    assert st.pending_undecided_qty == 1


@pytest.mark.asyncio
async def test_sin_cifras_no_se_inventa_cuantos(ex7):
    # Banco ex7: "mis amigos" sin número acababa en {snorkel: 2}; sin reparto, el bot pregunta cuántos.
    ex7({"group_allocation": {"certified_diving": 1, "snorkel": 2}, "group_size": 3})
    st = _estado(is_certified=True)
    st = await _entender("yo buceo y mis amigos hacen snorkel", st)
    assert not st.detected_group_allocation


@pytest.mark.asyncio
async def test_con_ex8_el_grupo_repartido_conserva_su_actividad(ex7, monkeypatch):
    # El grupo va antes que la actividad: la regla de ex-8 del grupo repartido mira el reparto del turno, que ahora pone
    # el extractor (sin esto se repreguntaba la actividad, como en la ronda ex8-B).
    ex7({"group_size": 6, "group_allocation": {"certified_diving": 2, "minicourse": 2, "snorkel": 2}})
    st = await _entender("somos 6: 2 bucean certificados, 2 hacen minicurso y 2 snorkel")
    assert st.detected_group_allocation == {"certified_diving": 2, "minicourse": 2, "snorkel": 2}
    assert st.detected_activity in ("certified_diving", "minicourse", "snorkel")


def test_una_cita_de_varias_lineas_sin_separador_vale_si_son_trozos_del_mensaje():
    # Banco ex0 (familia-mixta-precio-descuento-refresher t1): la lista de personas en varias líneas, saltándose la
    # línea "Snorkeling", se descartaba y el grupo de 6 se perdía. Palabras sueltas no cosen una cita.
    from src.agents import extractor_turno as ex

    msg = "2 diving sessions\n2 adults (ages 42, 19)\n1 youth (age 17)\nSnorkeling\n1 Adult (Age 43)\n2 kids (Ages 14, 10)"
    assert ex.cita_verificable("2 adults (ages 42, 19) 1 youth (age 17) 1 Adult (Age 43) 2 kids (Ages 14, 10)", msg)
    assert not ex.cita_verificable("quiero bucear certificado", "quiero bucear, no estoy certificado")
    assert not ex.cita_verificable("buzo certificado", "gracias")


