"""G3-06 (18-oct, decisión de Gadea; promocionado, su flag `baru_no_es_rosario` se borró en sim-5): Barú y Playa Blanca NO son Islas del Rosario.

Conv 5572 (charla G3): "estamos en el hotel las islas, en baru" quedaba como location=island, y el bot decía a la vez
"en Barú no operamos" y "la recogida está incluida", con precios de las islas. Se fija, con el flag:
1. el extractor descarta "island" si la cita solo nombra Barú o Playa Blanca;
2. "Barú" ya no vale como respuesta "isla" a "¿desde dónde saldrías?";
3. Jev y los prompts de la red y del resolutor ya no cuentan Barú entre las islas;
sin el flag, todo como hoy.
"""

import json

import pytest

from src.agents import conversational_core as core
from src.agents import extractor_turno as ex
from src.agents import jev_router
from src.config import settings
from src.prompts import booking


def _cliente(datos: dict):
    class _C:
        async def create(self, **kw):
            msg = type("M", (), {"content": json.dumps(datos)})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()], "usage": None})()

    return type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})()


MSG = "estamos en el hotel las islas, en baru. nos pueden recoger ahi?"
ISLA = {"location": {"valor": "island", "cita": "estamos en el hotel las islas, en baru"}}


@pytest.mark.asyncio
async def test_el_extractor_no_pone_las_islas_por_baru(monkeypatch):
    monkeypatch.setattr(settings, "baru_sale_de_cartagena", False)  # con gen-6, 'cartagena' (test_gen6_*)
    out = await ex.extraer_turno(MSG, client=_cliente(ISLA))
    assert out.get("location") is None


@pytest.mark.parametrize("cita, solo", [
    ("estamos en el hotel las islas, en baru", True),
    ("nos quedamos en Playa Blanca", True),
    ("en Barú y Rosario", False),            # nombra también el Rosario: no se toca
    ("un hotel en Isla Grande", False),
])
def test_solo_baru(cita, solo):
    assert ex._solo_baru(cita) is solo


def test_baru_no_es_respuesta_isla_al_origen(monkeypatch):
    monkeypatch.setattr(settings, "baru_sale_de_cartagena", False)  # con gen-6, 'cartagena' (test_gen6_*)
    assert core._departure_place("en baru") is None


def test_una_isla_sigue_siendo_isla(monkeypatch):
    assert core._departure_place("ya estamos en la isla") == "island"


def test_jev_y_los_prompts_sin_baru():
    islas = jev_router._questions_for_turn()[jev_router.CUSTOMER_PLACE]["criteria"]["islands"]
    assert "Baru..." not in islas
    texto = booking.lugar_sin_baru(booking.slot_resolver_prompt("location", "en"))
    assert "(Barú, Isla Grande" not in texto and "NOT the islands" in texto
