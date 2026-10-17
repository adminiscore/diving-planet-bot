"""G3-01 (17-oct, charla G3 de Gadea en PRE, conv 5567): familia de 4, los padres buzos certificados eligen "la salida
de 2 inmersiones para nosotros dos. y los niños qué pueden hacer?" y luego "el de 12 minicurso y el de 8 snorkel".
El bot nunca llegaba al precio. Tres flags, APAGADOS:

1. `lo_dicho_en_respuesta_fija`: la respuesta fija de edades contesta sin el núcleo y la actividad elegida se perdía.
2. `reparto_parcial_con_lo_sabido`: el reparto de solo los hijos ({minicourse: 1, snorkel: 1}) no suma 4 y se
   descartaba; ahora los no nombrados siguen con la actividad principal.
3. `actividad_principal_en_el_reparto`: "minicourse" ya no sustituye a la principal si esta sigue en el reparto.
"""

import asyncio

import pytest

from src.agents import conversational_core as core
from src.agents import supervisor
from src.config import settings
from src.flows.state import ConversationState
from tests.test_group_allocation_veto import _intent_alloc


def _familia(actividad="certified_diving"):
    s = ConversationState(conversation_id="g3-01")
    s.detected_group_size = 4
    s.detected_is_certified = s.is_certified = True
    s.detected_activity = actividad
    return s


# 1 · lo dicho en un turno con respuesta fija ---------------------------------------------------------------------

def _con_extraccion(state, datos):
    async def _datos():
        return datos

    state._extraccion_adelantada = asyncio.ensure_future(_datos())


@pytest.mark.asyncio
@pytest.mark.parametrize("flag, esperado", [(False, None), (True, "certified_diving")])
async def test_la_actividad_dicha_en_la_respuesta_fija_se_guarda(monkeypatch, flag, esperado):
    monkeypatch.setattr(settings, "lo_dicho_en_respuesta_fija", flag)
    st = _familia(actividad=None)
    _con_extraccion(st, {"activity": "certified_diving", "group_size": 2,
                         "group_allocation": {"certified_diving": 2, "minicourse": 2}})
    await core.guardar_lo_dicho_sin_nucleo(st)
    assert st.detected_activity == esperado
    # Nunca pisa lo sabido (el total 4) ni guarda el reparto: el extractor lo inventa 1 de cada 3 veces.
    assert st.detected_group_size == 4
    assert st.detected_group_allocation is None


@pytest.mark.asyncio
async def test_si_el_nucleo_uso_la_extraccion_no_hace_nada(monkeypatch):
    monkeypatch.setattr(settings, "lo_dicho_en_respuesta_fija", True)
    st = _familia(actividad=None)
    st._extraccion_adelantada = None
    await core.guardar_lo_dicho_sin_nucleo(st)
    assert st.detected_activity is None


# 2 · el reparto de una parte del grupo -----------------------------------------------------------------------------

@pytest.mark.parametrize("parcial, completo", [
    ({"minicourse": 1, "snorkel": 1}, {"minicourse": 1, "snorkel": 1, "certified_diving": 2}),
    ({"certified_diving": 1, "minicourse": 1, "snorkel": 1}, {"certified_diving": 2, "minicourse": 1, "snorkel": 1}),
])
def test_los_no_nombrados_siguen_con_la_principal(monkeypatch, parcial, completo):
    monkeypatch.setattr(settings, "reparto_parcial_con_lo_sabido", True)
    intent = _intent_alloc(dict(parcial))
    supervisor.enforce_group_allocation_consistency(intent, _familia(), "el de 12 minicurso y el de 8 snorkel")
    assert intent.group_allocation == completo


def test_sin_flag_se_descarta_como_siempre(monkeypatch):
    monkeypatch.setattr(settings, "reparto_parcial_con_lo_sabido", False)
    intent = _intent_alloc({"minicourse": 1, "snorkel": 1})
    supervisor.enforce_group_allocation_consistency(intent, _familia(), "msg")
    assert intent.group_allocation is None


@pytest.mark.parametrize("como", ["sin_principal", "con_reparto_guardado", "principal_generica"])
def test_sin_lo_sabido_claro_se_descarta(monkeypatch, como):
    monkeypatch.setattr(settings, "reparto_parcial_con_lo_sabido", True)
    st = _familia(actividad={"sin_principal": None, "principal_generica": "padi_course"}.get(como, "certified_diving"))
    if como == "con_reparto_guardado":
        st.detected_group_allocation = {"certified_diving": 2, "snorkel": 2}
    intent = _intent_alloc({"minicourse": 1, "snorkel": 1})
    supervisor.enforce_group_allocation_consistency(intent, st, "msg")
    assert intent.group_allocation is None


# 3 · la actividad principal se queda -------------------------------------------------------------------------------

@pytest.mark.parametrize("flag, principal", [(False, "minicourse"), (True, "certified_diving")])
def test_la_actividad_de_los_hijos_no_sustituye_a_la_principal(monkeypatch, flag, principal):
    monkeypatch.setattr(settings, "actividad_principal_en_el_reparto", flag)
    st = _familia()
    intent = _intent_alloc({"certified_diving": 2, "minicourse": 1, "snorkel": 1})
    intent.activity = "minicourse"
    supervisor._apply_detected_intent(intent, st, "el de 12 minicurso y el de 8 snorkel")
    assert st.detected_activity == principal


def test_un_cambio_de_idea_de_todo_el_grupo_si_sustituye(monkeypatch):
    monkeypatch.setattr(settings, "actividad_principal_en_el_reparto", True)
    st = _familia()
    intent = _intent_alloc({"snorkel": 4})
    intent.activity = "snorkel"
    supervisor._apply_detected_intent(intent, st, "mejor todos snorkel")
    assert st.detected_activity == "snorkel"
