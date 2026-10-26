"""lat-11 T6c (26-oct): los lugares de `lugares.json` que daban falsos «está en las islas».

1. Nombrar el archipiélago («las Islas del Rosario», «Rosario Islands», «el Rosario») dice «en las islas», no Isla
   Rosario: antes daba island=isla_rosario, que llegaba al resumen del lead y al contexto del RAG.
2. Los alias de hotel que son palabras corrientes o lugares de Cartagena (`alias_si_nombra_un_hotel`: «san pedro»,
   «secreto», «flores», «pelícano»…) solo cuentan cuando se sabe que el texto nombra un hotel: la cita del hotel que
   trae el extractor (`_hotel_del_catalogo`) o la respuesta a «¿en qué hotel te hospedas?» (`_lugar_del_catalogo`).
"""

import pytest

from src.agents.intent_detector import DetectedIntent, detect_location
from src.agents.nucleo.extractor import _hotel_del_catalogo
from src.agents.nucleo.routing import _lugar_del_catalogo


def _lugar(texto: str, **kw) -> tuple:
    intent = DetectedIntent()
    detect_location(texto.lower(), intent, **kw)
    return intent.location, intent.island, intent.hotel


@pytest.mark.parametrize("texto", [
    "Estamos alojados en las Islas del Rosario",
    "We're staying on the Rosario Islands",
    "quiero bucear en el rosario",
    "ya estoy en las islas del rosario",
])
def test_el_archipielago_es_en_las_islas_sin_isla(texto):
    assert _lugar(texto) == ("island", None, None)


def test_isla_rosario_sigue_siendo_esa_isla():
    assert _lugar("nos quedamos en Isla Rosario") == ("island", "isla_rosario", None)


def test_rezar_el_rosario_no_es_un_lugar():
    assert _lugar("vamos a rezar el rosario") == (None, None, None)


def test_el_archipielago_desde_cartagena_sale_de_cartagena():
    assert _lugar("quiero ir a los corales del rosario desde cartagena")[0] == "cartagena"


def test_un_hotel_del_archipielago_trae_su_isla():
    assert _lugar("estamos en el rosario ecohotel") == ("island", "isla_rosario", "rosario_ecohotel")


@pytest.mark.parametrize("texto", [
    "nos quedamos cerca de San Pedro Claver",
    "te cuento un secreto: nunca he buceado",
    "ayer vimos un pelícano en la playa",
    "llevamos flores para un cumpleaños",
    "San Pedro",
])
def test_una_palabra_corriente_en_el_mensaje_no_es_el_hotel(texto):
    assert _lugar(texto)[2] is None


@pytest.mark.parametrize("texto,hotel,isla", [
    ("San Pedro", "san_pedro_majagua", "isla_grande"),
    ("hostal Secreto", "secreto", "isla_grande"),
    ("Fragata", "fragata", "isla_grande"),
    ("Las Flores", "ecohotel_flores", "isla_grande"),
    ("el pelícano", "isla_pelicano_hotel", "isla_pelicano"),
])
def test_si_se_sabe_que_es_un_hotel_cuentan(texto, hotel, isla):
    assert _hotel_del_catalogo(texto) == (hotel, isla)
    assert _lugar_del_catalogo(texto) == (hotel, isla)


@pytest.mark.parametrize("texto,hotel", [
    ("Secreto Hostel", "secreto"),
    ("estamos en el hotel secreto", "secreto"),
    ("nos hospedamos en el San Pedro de Majagua", "san_pedro_majagua"),
    ("bora bora", "bora_bora"),
])
def test_el_nombre_entero_del_hotel_cuenta_en_el_mensaje(texto, hotel):
    assert _lugar(texto)[2] == hotel
