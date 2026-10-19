"""ex-9b paso 3: el regex deja de ser la "pista" de los campos del extractor.

Primero, la regla (sin flag): la actividad principal de un grupo repartido sale del reparto del extractor (la regla de
CAL-F), no de la primera lista del regex que casa ("somos 6: 2 bucean certificados, 2 hacen minicurso y 2 snorkel"
acababa en minicurso).
"""
from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents.extractor_turno import actividad_principal_del_reparto
from src.agents.nucleo import extractor as core_extractor
from src.flows.state import ConversationState

GRUPO_6 = "somos 6: 2 bucean certificados, 2 hacen minicurso y 2 snorkel"
REPARTO_6 = {"certified_diving": 2, "minicourse": 2, "snorkel": 2}


@pytest.fixture
def extractor(monkeypatch):
    """Simula lo que devuelve el extractor del turno (None = la llamada falló, también su respaldo)."""

    def con(datos):
        monkeypatch.setattr(core_extractor, "datos_del_extractor", AsyncMock(return_value=datos))

    return con


def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="ex9b-3", language="es")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


async def _entender(mensaje: str, state: ConversationState | None = None) -> ConversationState:
    state = state or _estado()
    await core._understand(state, mensaje)
    return state


# --- 0. la regla del reparto (la de CAL-F, ahora en una función) ---------------------------------------------------


def test_actividad_principal_del_reparto():
    assert actividad_principal_del_reparto({"certified_diving": 1, "minicourse": 2}) == "certified_diving"
    assert actividad_principal_del_reparto({"minicourse": 2, "snorkel": 3}) == "snorkel"
    assert actividad_principal_del_reparto({"undecided": 3}) is None
    assert actividad_principal_del_reparto({}) is None
    assert actividad_principal_del_reparto(None) is None


# --- 4. grupo repartido: la actividad principal sale del reparto ------------------------------------------------------


@pytest.mark.asyncio
async def test_grupo_repartido_principal_del_reparto(extractor):
    # Antes, con la pista: la primera lista del regex que casa (el minicurso), aunque haya buzos certificados.
    extractor({"group_size": 6, "group_allocation": REPARTO_6})
    st = await _entender(GRUPO_6)
    assert st.detected_group_allocation == REPARTO_6
    assert st.detected_activity == "certified_diving"


@pytest.mark.asyncio
async def test_grupo_repartido_sin_buceo_certificado_la_parte_mas_grande(extractor):
    extractor({"group_size": 5, "group_allocation": {"minicourse": 2, "snorkel": 3}})
    st = await _entender("somos 5: 2 hacen el minicurso y 3 snorkel")
    assert st.detected_activity == "snorkel"


@pytest.mark.asyncio
async def test_grupo_repartido_la_actividad_elegida_manda(extractor):
    extractor({"activity": "minicourse", "group_size": 3, "group_allocation": {"minicourse": 2, "snorkel": 1}})
    st = await _entender("somos 3, queremos el minicurso 2 y uno snorkel")
    assert st.detected_activity == "minicourse"


@pytest.mark.asyncio
async def test_el_acompanante_no_le_quita_la_principal_a_quien_escribe(extractor):
    # Replay del golden (acompanante-goteo t4): "hola quiero bucear con mi amigo", "yo soy certificado", "el no es
    # certificado", "el quiere hacer snorkel" con el reparto {buceo: 1, snorkel: 1}. Antes el regex leía snorkel y la
    # principal pasaba a ser el snorkel del amigo.
    extractor({"group_allocation": {"certified_diving": 1, "snorkel": 1}})
    st = _estado(is_certified=True, detected_is_certified=True, detected_group_size=2)
    st = await _entender("el quiere hacer snorkel", st)
    assert st.detected_activity == "certified_diving"
    assert st.detected_group_allocation == {"certified_diving": 1, "snorkel": 1}
