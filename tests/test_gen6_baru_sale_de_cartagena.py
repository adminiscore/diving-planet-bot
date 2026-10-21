"""gen-6 (21-oct, flag `baru_sale_de_cartagena`): quien se aloja en Barú o Playa Blanca sale desde Cartagena
(policies.json). Con G3-06 se quedaba sin origen y el bot volvía a preguntar desde dónde sale (banco gen-6 2/2)."""
import pytest

from src.agents import extractor_turno as ex
from src.agents import jev_router as jr
from src.config import settings
from src.prompts.booking import SLOT_RESOLVER_SPEC, lugar_sin_baru


@pytest.fixture
def con_flag(monkeypatch):
    monkeypatch.setattr(settings, "baru_no_es_rosario", True)
    monkeypatch.setattr(settings, "baru_sale_de_cartagena", True)


@pytest.mark.parametrize("prompt", [ex.SISTEMA_ES, ex.SISTEMA_EN], ids=["es", "en"])
def test_la_frase_que_se_cambia_esta_en_el_prompt_del_extractor(prompt):
    """Si alguien reescribe la regla del origen, el cambio dejaría de aplicarse sin avisar."""
    assert sum(antes in prompt for antes, _ in ex._BARU_SALE_DE_CARTAGENA) == 1


def test_baru_es_un_lugar_solo_con_el_flag(monkeypatch):
    monkeypatch.setattr(settings, "baru_sale_de_cartagena", False)
    assert not ex.nombra_un_lugar("Estamos hospedados en Barú")
    monkeypatch.setattr(settings, "baru_sale_de_cartagena", True)
    assert ex.nombra_un_lugar("Estamos hospedados en Barú")


def test_jev_lee_baru_como_cartagena(con_flag):
    criterios = jr._questions_for_turn()[jr.CUSTOMER_PLACE]["criteria"]
    assert "Barú" in criterios["cartagena"] and "Barú" in criterios["none"]
    assert "set out from Cartagena" in criterios["cartagena"]


def test_el_resolutor_de_la_pregunta_del_origen(con_flag):
    texto = lugar_sin_baru(SLOT_RESOLVER_SPEC["location"]["value_meaning"], True)
    assert "sets out from Cartagena" in texto and "'cartagena'" in texto
    assert lugar_sin_baru(SLOT_RESOLVER_SPEC["location"]["value_meaning"]) == lugar_sin_baru(
        SLOT_RESOLVER_SPEC["location"]["value_meaning"], False)


_RAG_CON_LISTA = ("¡Claro que sí! 🌊\n\nLa **salida de 2 inmersiones** cuesta:\n\n- **178 USD online** / **197 USD normal**\n"
                  "- **630.000 COP online** / **700.000 COP normal**\n\nEso es para la opción **saliendo desde Cartagena**.  "
                  "\nSi ya están en las Islas del Rosario, también existe la opción de **124 USD online**.\n\n"
                  "¿Quieres que te comparta el link de reserva del plan que te aplica?")


def test_la_puerta_del_origen_no_deja_el_titulo_colgado(monkeypatch):
    """Respuesta real del RAG (banco gen-6, g6-precio-sin-origen): el título de la lista va separado por una línea en
    blanco."""
    from src.agents.conversational_core import _sin_importes

    monkeypatch.setattr(settings, "origen_sin_titulo_suelto", False)
    assert "cuesta:" in _sin_importes(_RAG_CON_LISTA + "\n\nCuéntame qué día te viene mejor para organizarlo todo.")
    monkeypatch.setattr(settings, "origen_sin_titulo_suelto", True)
    resto = _sin_importes(_RAG_CON_LISTA + "\n\nCuéntame qué día te viene mejor para organizarlo todo.")
    assert "cuesta:" not in resto and "USD" not in resto and "Cuéntame qué día" in resto


def test_en_baru_es_respuesta_cartagena_al_origen(con_flag):
    from src.agents import conversational_core as core

    assert core._departure_place("en baru") == "cartagena"
    assert core._departure_place("ya estamos en la isla") == "island"


async def test_el_extractor_pone_cartagena_por_baru(con_flag):
    import json

    class _C:
        async def create(self, **kw):
            datos = {"location": {"valor": "island", "cita": "estamos en el hotel las islas, en baru"}}
            msg = type("M", (), {"content": json.dumps(datos)})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()], "usage": None})()

    cliente = type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})()
    out = await ex.extraer_turno("estamos en el hotel las islas, en baru. nos pueden recoger ahi?", client=cliente)
    assert out.get("location") == "cartagena"


def test_apagado_todo_igual(monkeypatch):
    monkeypatch.setattr(settings, "baru_no_es_rosario", True)
    monkeypatch.setattr(settings, "baru_sale_de_cartagena", False)
    assert jr._questions_for_turn()[jr.CUSTOMER_PLACE] is jr._CUSTOMER_PLACE_Q_SIN_BARU
