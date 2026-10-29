"""gen-6 (21-oct; promocionado, su flag `baru_sale_de_cartagena` se borró en sim-5): quien se aloja en Barú o Playa Blanca sale desde Cartagena
(policies.json). Con G3-06 se quedaba sin origen y el bot volvía a preguntar desde dónde sale (banco gen-6 2/2)."""
import pytest

from src.agents import extractor_turno as ex
from src.agents import jev_router as jr
from src.prompts.booking import SLOT_RESOLVER_SPEC, lugar_sin_baru


@pytest.mark.parametrize("prompt", [ex.SISTEMA_ES, ex.SISTEMA_EN], ids=["es", "en"])
def test_la_frase_que_se_cambia_esta_en_el_prompt_del_extractor(prompt):
    """Si alguien reescribe la regla del origen, el cambio dejaría de aplicarse sin avisar."""
    assert sum(antes in prompt for antes, _ in ex._BARU_SALE_DE_CARTAGENA) == 1


def test_baru_es_un_lugar():
    assert ex.nombra_un_lugar("Estamos hospedados en Barú")


def test_jev_lee_baru_como_cartagena():
    criterios = jr._questions_for_turn()[jr.CUSTOMER_PLACE]["criteria"]
    assert "Barú" in criterios["cartagena"] and "Barú" in criterios["none"]
    assert "set out from Cartagena" in criterios["cartagena"]


def test_el_resolutor_de_la_pregunta_del_origen():
    texto = lugar_sin_baru(SLOT_RESOLVER_SPEC["location"]["value_meaning"], True)
    assert "sets out from Cartagena" in texto and "'cartagena'" in texto
    assert lugar_sin_baru(SLOT_RESOLVER_SPEC["location"]["value_meaning"]) == lugar_sin_baru(
        SLOT_RESOLVER_SPEC["location"]["value_meaning"], False)
def test_en_baru_es_respuesta_cartagena_al_origen():
    from src.agents import conversational_core as core

    assert core._departure_place("en baru") == "cartagena"
    assert core._departure_place("ya estamos en la isla") == "island"


async def test_el_extractor_pone_cartagena_por_baru():
    import json

    class _C:
        async def create(self, **kw):
            datos = {"location": {"valor": "island", "cita": "estamos en el hotel las islas, en baru"}}
            msg = type("M", (), {"content": json.dumps(datos)})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()], "usage": None})()

    cliente = type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})()
    out = await ex.extraer_turno("estamos en el hotel las islas, en baru. nos pueden recoger ahi?", client=cliente)
    assert out.get("location") == "cartagena"


def test_caln3b_baru_como_hotel_tambien_sale_de_cartagena():
    """CALN-3b (CALN3-P02): «we'll already be staying at Isla Barú» llegaba como hotel y sin origen (3/3 en PRE)."""
    import asyncio
    import json

    def cliente(datos):
        class _C:
            async def create(self, **kw):
                msg = type("M", (), {"content": json.dumps(datos)})()
                return type("R", (), {"choices": [type("C", (), {"message": msg})()], "usage": None})()

        return type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})()

    msg = "We're 2 and want to snorkel, we'll already be staying at Isla Barú. How much?"
    out = asyncio.run(ex.extraer_turno(msg, lang="en", client=cliente(
        {"hotel": {"valor": "Isla Barú", "cita": "staying at Isla Barú"}})))
    assert out["hotel"] == "Isla Barú" and out["location"] == "cartagena"
    otro = asyncio.run(ex.extraer_turno("We'll be staying at Bodegas de Santa Clara", lang="en", client=cliente(
        {"hotel": {"valor": "Bodegas de Santa Clara", "cita": "staying at Bodegas de Santa Clara"}})))
    assert "location" not in otro
