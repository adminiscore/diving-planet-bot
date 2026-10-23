"""ARQ-1r (22-oct, flag `cedula_de_extranjeria_manda`): «extranjero o turista: false» (CAL-C) chocaba con la cédula de
extranjería, que tienen los extranjeros residentes (pagan en COP). Sonda con historial: 10/20 -> 20/20; banco de moneda
de gen-4 ×2 con el flag: 62/62 (los que pagan en USD, 10/10). Aquí, sin red: que la frase entra solo con el flag."""
import asyncio
import json

import pytest

from src.agents import extractor_turno as ex
from src.config import settings


@pytest.mark.parametrize("antes, despues", ex._CEDULA_DE_EXTRANJERIA_MANDA)
def test_la_frase_que_se_cambia_esta_en_la_regla(antes, despues):
    assert sum(antes in regla for regla in (ex.SIN_CEDULA_ES, ex.SIN_CEDULA_EN)) == 1


def _sistema(monkeypatch, flag: bool, lang: str) -> str:
    monkeypatch.setattr(settings, "cedula_de_extranjeria_manda", flag)
    visto = {}

    class _C:
        async def create(self, **kw):
            visto.setdefault("system", kw["messages"][0]["content"])
            msg = type("M", (), {"content": json.dumps({})})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()], "usage": None})()

    cliente = type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})()
    asyncio.run(ex.extraer_turno("tengo cédula de extranjería", lang=lang, client=cliente))
    return visto["system"]


@pytest.mark.parametrize("lang, frase", [("es", "salvo que diga que tiene cédula de extranjería"),
                                         ("en", "unless they say they have a cédula de extranjería")])
def test_solo_con_el_flag(monkeypatch, lang, frase):
    assert frase not in _sistema(monkeypatch, False, lang)
    assert frase in _sistema(monkeypatch, True, lang)
