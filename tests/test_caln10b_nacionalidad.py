"""CALN-10b (decisión de Gadea, 30-oct): mientras no se sabe si el cliente es colombiano, el extractor lee el mensaje dos
veces a la vez y la nacionalidad solo vale si las dos lecturas coinciden (`docs/robustness/caln/estudio-caln10-lecturas.md`).
Sin red: `extraer_turno` falso."""
import pytest

from src.agents import extractor_turno as ex
from src.agents.nucleo import extractor as core_extractor
from src.flows.state import ConversationState


def _con_lecturas(monkeypatch, *lecturas):
    """`extraer_turno` falso que devuelve las lecturas en orden (una excepción = la llamada falla)."""
    cola, llamadas = list(lecturas), []

    async def falso(message, *, history=None, sabido=None, lang="es", **kw):
        llamadas.append(message)
        lectura = cola.pop(0)
        if isinstance(lectura, Exception):
            raise lectura
        return lectura

    monkeypatch.setattr(ex, "extraer_turno", falso)
    monkeypatch.setattr(core_extractor, "campos_del_extractor", lambda: ("is_colombian",))
    monkeypatch.setattr(core_extractor, "lanzar_lector_grupo", lambda *a, **k: None)
    return llamadas


async def _lee(state, mensaje="Soy de Cali y salgo de Cartagena"):
    core_extractor.lanzar_extraccion_adelantada(state, mensaje)
    return await state._extraccion_adelantada


@pytest.mark.asyncio
async def test_si_las_dos_lecturas_coinciden_vale_la_nacionalidad(monkeypatch):
    llamadas = _con_lecturas(monkeypatch, {"is_colombian": True, "location": "cartagena"}, {"is_colombian": True})
    datos = await _lee(ConversationState(conversation_id="c10b-1"))
    assert datos == {"is_colombian": True, "location": "cartagena"} and len(llamadas) == 2


@pytest.mark.asyncio
async def test_si_no_coinciden_se_queda_sin_dato_y_lo_demas_sigue(monkeypatch):
    _con_lecturas(monkeypatch, {"is_colombian": False, "location": "cartagena"}, {"is_colombian": True})
    datos = await _lee(ConversationState(conversation_id="c10b-2"))
    assert datos == {"location": "cartagena"}


@pytest.mark.asyncio
async def test_si_una_lectura_no_la_dice_tampoco_vale(monkeypatch):
    _con_lecturas(monkeypatch, {"is_colombian": True}, {})
    assert await _lee(ConversationState(conversation_id="c10b-3")) == {}


@pytest.mark.asyncio
async def test_si_la_primera_no_trae_nacionalidad_no_hay_segunda(monkeypatch):
    """Álvaro (#2649): si la primera no la trae, la segunda no podría hacer que valga; no se paga."""
    llamadas = _con_lecturas(monkeypatch, {"location": "cartagena"})
    assert await _lee(ConversationState(conversation_id="c10b-4")) == {"location": "cartagena"}
    assert len(llamadas) == 1


@pytest.mark.asyncio
async def test_si_la_segunda_falla_vale_la_primera_como_antes(monkeypatch):
    _con_lecturas(monkeypatch, {"is_colombian": True}, RuntimeError("caída"))
    assert await _lee(ConversationState(conversation_id="c10b-4b")) == {"is_colombian": True}


@pytest.mark.asyncio
async def test_con_la_nacionalidad_sabida_o_el_grupo_mixto_una_sola_lectura(monkeypatch):
    for preparar in (lambda s: setattr(s, "is_colombian", False), lambda s: setattr(s, "mixed_nationality_notice", True)):
        llamadas = _con_lecturas(monkeypatch, {"location": "island"})
        state = ConversationState(conversation_id="c10b-5")
        preparar(state)
        assert await _lee(state, "Estamos en Isla Grande") == {"location": "island"}
        assert len(llamadas) == 1
