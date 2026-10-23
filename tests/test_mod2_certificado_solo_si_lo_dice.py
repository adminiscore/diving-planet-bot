"""mod-2 (18-oct, decisión de Gadea; promocionado, su flag `certificado_solo_si_lo_dice` se borró en sim-5): elegir el buceo certificado ("fun dives") no
dice que el cliente esté certificado; tiene que confirmarlo. La regla del catálogo del extractor lo deducía para todos
los modelos ("paquete de 5 inmersiones" / "fun dives" → is_certified). Con el flag, no lo deduce."""

import json

import pytest

from src.agents import extractor_turno as ex


def _cliente(datos: dict):
    class _C:
        async def create(self, **kw):
            msg = type("M", (), {"content": json.dumps(datos)})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()], "usage": None})()

    return type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})()


FUN_DIVES = {"activity": {"valor": "certified_diving", "cita": "join for the fun dives"}}


@pytest.mark.asyncio
async def test_elegir_el_buceo_no_dice_que_este_certificado():
    out = await ex.extraer_turno("is it still possible to join for the fun dives?", lang="en",
                                 client=_cliente(FUN_DIVES))
    assert out["activity"] == "certified_diving"
    assert out.get("is_certified") is None


@pytest.mark.asyncio
async def test_si_lo_dice_el_cliente_vale(monkeypatch):
    datos = {**FUN_DIVES, "is_certified": {"valor": True, "cita": "I'm certified"}}
    out = await ex.extraer_turno("I'm certified, can I join for the fun dives?", lang="en", client=_cliente(datos))
    assert out["is_certified"] is True
