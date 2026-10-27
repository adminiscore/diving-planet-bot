"""CALN-2 (27-oct, Álvaro (3)): quien viene sin elegir queda SIN DECIDIR, no con la actividad que supone la red de
señales (decisión «no asumir»: se le recomienda y elige el cliente). Banco de grupos g02, g26 y g28."""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.nucleo import extraction as core_extraction
from src.agents.nucleo import routing as core_routing
from src.agents.supervisor import route_message
from src.flows.state import ConversationState


@pytest.fixture(autouse=True)
def _sin_resolver(monkeypatch):
    monkeypatch.setattr(core_extraction, "resolve_slot_answer", AsyncMock(return_value={}))


def _estado() -> ConversationState:
    st = ConversationState(conversation_id="caln2-sin-decidir")
    st.language = "es"
    return st


async def _turno(st, mensaje, senales):
    falsa = AsyncMock(return_value=senales)
    with patch.object(core_routing, "detect_special_signals", new=falsa), \
            patch.object(core_extraction, "detect_special_signals", new=falsa):
        return await route_message(st, mensaje)


@pytest.mark.asyncio
async def test_no_ha_buceado_nunca_no_es_minicurso(extractor_dice):
    """g02: la red da minicurso a «mi novia que no ha buceado nunca» (su regla vieja); el mensaje no lo nombra."""
    mensaje = "Quiero bucear, soy certificado. Voy con mi novia que no ha buceado nunca"
    extractor_dice({mensaje: {"activity": "certified_diving", "is_certified": True, "otro_sin_certificar": True}})
    st = _estado()
    await _turno(st, mensaje, {"companion_activity": "minicourse", "mentions_other_person": True,
                               "companion_is_singular": True})
    assert "minicourse" not in (st.detected_group_allocation or {})
    assert st.pending_undecided_qty == 1 and st.detected_group_size == 2


@pytest.mark.asyncio
async def test_la_amiga_que_no_sabe_no_es_buzo(extractor_dice):
    """g28: la red da a la amiga la actividad de quien escribe; el extractor leyó el mensaje y no puso a nadie más."""
    mensaje = "Quiero bucear, soy buzo certificado. Viene también mi amiga, pero no sabe qué quiere hacer"
    extractor_dice({mensaje: {"activity": "certified_diving", "is_certified": True}})
    st = _estado()
    await _turno(st, mensaje, {"companion_activity": "certified_diving", "mentions_other_person": True,
                               "companion_is_singular": True})
    assert (st.detected_group_allocation or {}).get("certified_diving", 0) <= 1
    assert st.pending_undecided_qty == 1 and st.detected_group_size == 2


@pytest.mark.asyncio
async def test_unos_amigos_sin_numero_no_se_cuentan(extractor_dice):
    """g26: sin decidir y sin poder contarlos: nadie se suma con la actividad de quien escribe."""
    mensaje = "Quiero bucear, soy buzo certificado. Vienen también unos amigos, no sé qué querrán hacer"
    extractor_dice({mensaje: {"activity": "certified_diving", "is_certified": True}})
    st = _estado()
    await _turno(st, mensaje, {"companion_activity": "certified_diving", "mentions_other_person": True})
    assert (st.detected_group_allocation or {}).get("certified_diving", 0) <= 1
    assert not st.pending_undecided_qty


@pytest.mark.asyncio
async def test_si_el_extractor_ve_al_grupo_manda_el(extractor_dice):
    """Con el reparto del extractor en este turno, la red de señales no decide (el reparto ya resuelto)."""
    mensaje = "Somos 2 buzos certificados y queremos bucear"
    extractor_dice({mensaje: {"activity": "certified_diving", "is_certified": True, "group_size": 2}})
    st = _estado()
    await _turno(st, mensaje, {"companion_activity": "certified_diving", "mentions_other_person": True,
                               "companion_is_singular": True})
    assert st.detected_group_size == 2 and not st.pending_undecided_qty
