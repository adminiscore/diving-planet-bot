"""Sparring s04h (4-nov, australianos y Toronto): «two dives» salía como 2 días de buceo: varios días se comía la salida de
2 inmersiones y la cifra llegaba a `cert_days`. Valores y citas, los de la sonda ×5 contra el extractor real.
CALN-25 (decisión de Gadea, 4-nov): lo decide Jev (`son_dias_de_buceo`) y no 2 regex."""
import json

import pytest

from src.agents import extractor_turno as ex
from src.agents.jev_router import SON_DIAS_DE_BUCEO
from src.agents.nucleo.extractor import dias_de_buceo_de, duracion_del_extractor
from src.flows.state import ConversationState


def _estado(p=None):
    estado = ConversationState(conversation_id="s04h")
    estado._senales_router = {} if p is None else {SON_DIAS_DE_BUCEO: p}
    return estado


def test_jev_seguro_de_que_no_son_dias_se_descartan():
    datos = {"dias_de_buceo": 2, "_dias_citan_inmersiones": True}
    assert dias_de_buceo_de(datos, _estado(0.06)) is None
    assert duracion_del_extractor(datos, _estado(0.06)) == (None, False)


@pytest.mark.parametrize("p", [0.41, 0.82, 0.95])  # «2 inmersiones en 2 días», «two dives on Saturday and Sunday»
def test_si_jev_no_esta_seguro_de_que_no_se_quedan(p):
    assert dias_de_buceo_de({"dias_de_buceo": 2, "_dias_citan_inmersiones": True}, _estado(p)) == 2


def test_si_la_cita_no_cuenta_inmersiones_jev_no_los_quita():
    # «2» contestando a «¿cuántos días?», o «tres días seguidos»: la cita no cuenta inmersiones
    assert dias_de_buceo_de({"dias_de_buceo": 3}, _estado(0.05)) == 3


def test_si_jev_calla_vale_lo_del_extractor():
    assert dias_de_buceo_de({"dias_de_buceo": 2, "_dias_citan_inmersiones": True}, _estado()) == 2


def test_la_duracion_con_dias_de_buceo():
    assert duracion_del_extractor({"dias_de_buceo": 3}, _estado()) == ("multi_day", True)


def _cliente(datos: dict):
    class _C:
        class chat:
            class completions:
                @staticmethod
                async def create(**_):
                    mensaje = type("M", (), {"content": json.dumps(datos)})
                    return type("R", (), {"choices": [type("Ch", (), {"message": mensaje})], "usage": None})

    return _C()


@pytest.mark.parametrize("cita, marca", [
    ("for two dives", True),
    ("Five of us will do the two dives", True),
    ("we want to dive for two days", False),
])
@pytest.mark.asyncio
async def test_el_extractor_marca_la_cita_que_cuenta_inmersiones(cita, marca):
    salida = await ex.extraer_turno(cita, history=[], sabido={},
                                    client=_cliente({"dias_de_buceo": {"valor": 2, "cita": cita}}))
    assert salida["dias_de_buceo"] == 2
    assert bool(salida.get("_dias_citan_inmersiones")) is marca
