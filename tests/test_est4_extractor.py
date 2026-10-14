"""EX-EST-2 (14-oct, flag `extractor_todo_lo_dicho`): los cuatro arreglos del prompt del extractor son reemplazos de
frases del prompt de hoy. Si alguien cambia una de esas frases, el reemplazo dejaría de aplicarse sin avisar: este test
lo vigila, y que con el flag el prompt lleve las frases nuevas (y sin él, las de hoy)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents import extractor_turno as et
from src.config import settings

PARES = [
    (et.TODO_LO_DICHO_HOY_ES, et.TODO_LO_DICHO_ES, et.TODO_LO_DICHO_HOY_EN, et.TODO_LO_DICHO_EN),
    (et.GRUPO_HOY_ES, et.GRUPO_NUMERO_ES, et.GRUPO_HOY_EN, et.GRUPO_NUMERO_EN),
    (et.ACTIVIDAD_EJEMPLOS_HOY_ES, et.ACTIVIDAD_EJEMPLOS_ES, et.ACTIVIDAD_EJEMPLOS_HOY_EN, et.ACTIVIDAD_EJEMPLOS_EN),
    (et.RESIDENTE_HOY_ES, et.RESIDENTE_ES, et.RESIDENTE_HOY_EN, et.RESIDENTE_EN),
    (et.ELIGE_HOY_ES, et.ELIGE_ES, et.ELIGE_HOY_EN, et.ELIGE_EN),
]


@pytest.mark.parametrize("hoy_es,nuevo_es,hoy_en,nuevo_en", PARES)
def test_cada_frase_de_hoy_esta_una_vez_en_el_prompt(hoy_es, nuevo_es, hoy_en, nuevo_en):
    assert et.SISTEMA_ES.count(hoy_es) == 1
    assert et.SISTEMA_EN.count(hoy_en) == 1


async def _sistema(monkeypatch, flag: bool, lang: str) -> str:
    monkeypatch.setattr(settings, "extractor_todo_lo_dicho", flag)
    client = MagicMock()
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content="{}"))]
    client.chat.completions.create = AsyncMock(return_value=resp)
    await et.extraer_turno("Un solo buzo avanzado", lang=lang, client=client)
    return client.chat.completions.create.call_args.kwargs["messages"][0]["content"]


@pytest.mark.parametrize("lang", ["es", "en"])
async def test_con_el_flag_el_prompt_lleva_las_frases_nuevas(monkeypatch, lang):
    sistema = await _sistema(monkeypatch, True, lang)
    for hoy_es, nuevo_es, hoy_en, nuevo_en in PARES:
        hoy, nuevo = (hoy_es, nuevo_es) if lang == "es" else (hoy_en, nuevo_en)
        assert nuevo in sistema
        if hoy not in nuevo:  # la de la nacionalidad empieza igual que la de hoy: solo se le añade
            assert hoy not in sistema


@pytest.mark.parametrize("lang", ["es", "en"])
async def test_sin_el_flag_el_prompt_es_el_de_hoy(monkeypatch, lang):
    sistema = await _sistema(monkeypatch, False, lang)
    for hoy_es, _, hoy_en, _ in PARES:
        assert (hoy_es if lang == "es" else hoy_en) in sistema
