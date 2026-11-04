"""Sparring s04h (4-nov, australianos y Toronto): «two dives» salía como 2 días de buceo: varios días se comía la salida de
2 inmersiones y la cifra llegaba a `cert_days`. Valores y citas, los de la sonda ×5 contra el extractor real."""
import json

import pytest

from src.agents import extractor_turno as ex
from src.agents.intent_detector import inmersiones_leidas_como_dias


@pytest.mark.parametrize("dias, cita, mensaje", [
    (2, "for two dives", "Can you pick us up there for two dives? Is lunch included?"),
    (2, "two dives", "Can you pick us up there for two dives? Is lunch included?"),
    (2, "Five of us will do the two dives", "Five of us will do the two dives and the other two the mini course."),
    (3, "tres buceos", "Queremos hacer tres buceos"),
    (2, "two dives", "We're here for 5 days and want two dives"),  # los días que dice son otros
])
def test_son_inmersiones(dias, cita, mensaje):
    assert inmersiones_leidas_como_dias(dias, cita, mensaje)


@pytest.mark.parametrize("dias, cita, mensaje", [
    (3, "Queremos bucear 3 días", "Queremos bucear 3 días"),
    (2, "we want to dive for two days", "we want to dive for two days"),
    (2, "over 2 days", "I'd like 4 dives over 2 days"),
    (2, "4 dives over 2 days", "I'd like 4 dives over 2 days"),
    (2, "2 inmersiones en 2 días", "Quiero 2 inmersiones en 2 días"),
    (2, "2 inmersiones", "Quiero 2 inmersiones en 2 días"),                    # 1 de 5 cita solo esto
    (2, "Two days of diving", "Two days of diving, two dives each day"),
    (2, "We want two dives on Saturday and two dives on Sunday", "We want two dives on Saturday and two dives on Sunday"),
    (2, "dos inmersiones el sábado y dos el domingo", "dos inmersiones el sábado y dos el domingo"),
    (3, "the 3-day dive package", "the 3-day dive package please"),
    (1, "dos buceos el sábado", "Somos certificados y queremos hacer dos buceos el sábado"),
    (1, "Solo un día", "Solo un día, dos inmersiones"),
])
def test_son_dias(dias, cita, mensaje):
    assert not inmersiones_leidas_como_dias(dias, cita, mensaje)


def _cliente(datos: dict):
    class _C:
        class chat:
            class completions:
                @staticmethod
                async def create(**_):
                    mensaje = type("M", (), {"content": json.dumps(datos)})
                    return type("R", (), {"choices": [type("Ch", (), {"message": mensaje})], "usage": None})

    return _C()


@pytest.mark.asyncio
async def test_el_extractor_no_deja_pasar_la_cifra():
    mensaje = "Can you pick us up there for two dives?"
    salida = await ex.extraer_turno(mensaje, history=[], sabido={},
                                    client=_cliente({"dias_de_buceo": {"valor": 2, "cita": "for two dives"}}))
    assert "dias_de_buceo" not in salida
    assert ex.extraer_turno.ultimo_motivo["dias_de_buceo"].startswith("son inmersiones")


@pytest.mark.asyncio
async def test_el_extractor_deja_pasar_los_dias():
    mensaje = "we want to dive for two days"
    salida = await ex.extraer_turno(mensaje, history=[], sabido={},
                                    client=_cliente({"dias_de_buceo": {"valor": 2, "cita": mensaje}}))
    assert salida["dias_de_buceo"] == 2
