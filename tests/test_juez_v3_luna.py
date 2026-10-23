"""s4-33 (8-oct; promocionado, su flag `juez_v3_luna` se borró en sim-5): instrucciones del juez de grounding v3 para GPT-6 Luna.

Se fija: (1) el v3 para Luna es el v3 ENTERO (lo que caza los inventos) más las aclaraciones, antes del paso 2;
(2) el juez recibe esas instrucciones.
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


@pytest.mark.parametrize("lang,marca", [("es", "Aclaraciones"), ("en", "Clarifications")])
@pytest.mark.asyncio
async def test_el_juez_recibe_las_instrucciones_para_luna(monkeypatch, lang, marca):
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
    ok, _ = await grounding_check.is_grounded("Hola, soy Coral.", "CATÁLOGO OFICIAL\n- algo", lang=lang)
    assert ok
    assert marca in sistemas[0]
