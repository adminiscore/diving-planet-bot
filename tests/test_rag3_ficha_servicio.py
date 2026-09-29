"""rag-3: la ficha de un servicio se construye en UN solo sitio.

Por qué existe este fichero. Hasta rag-2 la ficha vivía en `scripts/kb_v2.py` y solo la usaba la
base curada. rag-3 la necesita también en el contexto del turno (cuando ya se sabe qué servicio
mira el cliente), así que se movió a `catalog.service_fact_sheet` y `kb_v2` la llama. Dos riesgos,
uno por test:

1. **Que el texto cambiara al moverlo.** Sería un cambio silencioso de la base v2: CI regenera
   `kb_v2` en cada deploy, así que una coma de más se lleva por delante los embeddings y la
   comparabilidad con las rondas de rag-2. `tests/data/fichas_servicio_antes.json` es la foto de
   las 72 fichas ANTES del movimiento; este test exige que sigan siendo las mismas.
2. **Que la base y el contexto se separen.** Si alguien vuelve a escribir la ficha en `kb_v2`, el
   segundo test lo caza: los dos caminos tienen que devolver el mismo texto.
"""

import json
from pathlib import Path

import pytest

from src.flows import catalog

FOTO = Path(__file__).parent / "data" / "fichas_servicio_antes.json"


@pytest.fixture(scope="module")
def foto() -> dict:
    return json.loads(FOTO.read_text(encoding="utf-8"))


def test_la_foto_cubre_todos_los_servicios(foto):
    """Control: si el catálogo crece y la foto no, el test de abajo pasaría sin mirar nada."""
    esperadas = {f"{sid}|{lang}" for sid in catalog.RAW_SERVICES for lang in ("es", "en")}
    assert set(foto) == esperadas, "la foto y services.json ya no coinciden: regenerar la foto a propósito"


def test_la_ficha_no_cambio_al_moverla(foto):
    distintas = [
        clave for clave in sorted(foto)
        if catalog.service_fact_sheet(*clave.rsplit("|", 1)) != foto[clave]
    ]
    assert not distintas, (
        f"{len(distintas)} fichas cambiaron: {distintas[:5]}. Si el cambio es a propósito, "
        "regenera tests/data/fichas_servicio_antes.json Y mide, porque cambia la base v2 entera."
    )


def test_la_base_v2_y_el_contexto_usan_la_misma_ficha():
    from scripts.kb_v2 import ficha_servicio

    for sid in ("open_water", "2_dives_1_day", "referral", "minicourse_already_on_island"):
        for lang in ("es", "en"):
            de_la_base = ficha_servicio(sid, catalog.RAW_SERVICES[sid], lang)["content"]
            del_contexto = catalog.service_fact_sheet(sid, lang)
            assert de_la_base == del_contexto, f"{sid}|{lang}: la base y el contexto ya no dicen lo mismo"


def test_la_ficha_lleva_el_itinerario():
    """El caso que abrió rag-3: "¿a qué hora acaba el día 1?" con el Open Water elegido. El dato
    está en el itinerario, y sin él en la ficha inyectarla no arreglaría nada."""
    ficha = catalog.service_fact_sheet("open_water", "en")
    assert "Itinerary:" in ficha
    assert "8:00 a.m." in ficha, "la hora de encuentro tiene que viajar en la ficha"
