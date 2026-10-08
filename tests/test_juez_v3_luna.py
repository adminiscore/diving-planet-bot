"""s4-33 (8-oct), flag `juez_v3_luna`: instrucciones del juez de grounding v3 para GPT-6 Luna.

Se fija: (1) el v3 para Luna es el v3 ENTERO (lo que caza los inventos) más las aclaraciones, antes del paso 2;
(2) con el flag el juez recibe esas instrucciones y sin él las de siempre.
"""
import pytest

from src.agents import grounding_check
from src.prompts.info import (
    GROUNDING_VERIFY_V3_EN,
    GROUNDING_VERIFY_V3_ES,
    GROUNDING_VERIFY_V3_LUNA_EN,
    GROUNDING_VERIFY_V3_LUNA_ES,
)


@pytest.mark.parametrize("v3,luna,marca,paso2", [
    (GROUNDING_VERIFY_V3_ES, GROUNDING_VERIFY_V3_LUNA_ES, "Aclaraciones", "Paso 2."),
    (GROUNDING_VERIFY_V3_EN, GROUNDING_VERIFY_V3_LUNA_EN, "Clarifications", "Step 2."),
])
def test_el_v3_para_luna_es_el_v3_mas_las_aclaraciones(v3, luna, marca, paso2):
    antes, despues = v3.split(paso2, 1)
    assert luna.startswith(antes) and luna.endswith(paso2 + despues)
    assert marca in luna and marca not in v3
    assert luna.index(marca) < luna.index(paso2)


@pytest.mark.parametrize("flag,lang,marca", [(True, "es", "Aclaraciones"), (True, "en", "Clarifications"),
                                             (False, "es", None), (False, "en", None)])
@pytest.mark.asyncio
async def test_con_el_flag_el_juez_recibe_las_instrucciones_para_luna(monkeypatch, flag, lang, marca):
    sistemas = []

    class _Completions:
        async def create(self, **kwargs):
            sistemas.append(kwargs["messages"][0]["content"])
            msg = type("M", (), {"content": "- (ninguno)\n\nGROUNDED"})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    class _OpenAI:
        def __init__(self, api_key=None):
            self.chat = type("Chat", (), {"completions": _Completions()})()

    monkeypatch.setattr(grounding_check, "AsyncOpenAI", _OpenAI)
    monkeypatch.setattr(grounding_check.settings, "grounding_v3", True)
    monkeypatch.setattr(grounding_check.settings, "juez_por_tipo", False)
    monkeypatch.setattr(grounding_check.settings, "juez_v3_luna", flag)
    ok, _ = await grounding_check.is_grounded("Hola, soy Coral.", "CATÁLOGO OFICIAL\n- algo", lang=lang)
    assert ok
    if marca:
        assert marca in sistemas[0]
    else:
        assert "Aclaraciones" not in sistemas[0] and "Clarifications" not in sistemas[0]
