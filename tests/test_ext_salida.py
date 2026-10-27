"""EXT-SALIDA (27-oct, LAT-10): el extractor escribe solo las claves con dato. Con TODAS las claves y sus null escribía
188 tokens en más de la mitad de los turnos (~2,75 ms por token: ~0,5 s en el camino crítico de cada turno). El código
ya toma por no dicho lo que falta. Sin red."""
import json

import pytest

from src.agents import extractor_turno as ex


def test_el_esquema_del_prompt_va_sin_required_ni_null():
    esquema = ex._esquema(True, True, {})
    prompt = ex._esquema_del_prompt(esquema)
    assert "required" not in prompt and "required" in esquema  # el de validar no cambia
    assert set(prompt["properties"]) == set(esquema["properties"])
    for nombre, campo in prompt["properties"].items():
        assert "null" not in campo["type"], nombre
        assert ex._SIN_DATO_NULL not in campo.get("description", "")
    assert prompt["properties"]["idioma"]["type"] == "string"  # va siempre (la instrucción lo dice)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_la_instruccion_pide_solo_las_claves_con_dato(lang):
    texto = ex._SOLO_JSON_ES if lang == "es" else ex._SOLO_JSON_EN
    assert ("SOLO las claves" if lang == "es" else "ONLY the keys") in texto
    assert ("TODAS las claves" if lang == "es" else "ALL the keys") not in texto
    assert ("\"idioma\" siempre" if lang == "es" else "\"idioma\" always") in texto


async def test_una_respuesta_sin_las_claves_que_no_dice_vale(monkeypatch):
    class _Resp:
        def __init__(self, contenido):
            self.choices = [type("C", (), {"message": type("M", (), {"content": contenido})()})()]
            self.usage = None

    class _Cliente:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**_kw):
                    return _Resp(json.dumps({"group_size": {"valor": 3, "cita": "Somos 3"}}))

    assert await ex.extraer_turno("Somos 3", lang="es", client=_Cliente()) == {"group_size": 3}
