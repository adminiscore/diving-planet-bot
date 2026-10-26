"""Tener un nivel PADI en tercera persona, con la persona nombrada (2026-09-15).

`_HOLDS_CERT_RE` solo conocia "tengo"/"tenemos": "mi pareja tiene el advanced y quiere
bucear" salia curso Advanced, cuando ya lo tiene. La tercera persona dice que NO se pide
el curso, pero nada del estado de quien escribe: "mi pareja tiene el advanced y yo no
tengo nada" marcaba al cliente como certificado. Quien lo tiene dentro del grupo es
cosa del reparto.
lat-11 T6d (26-oct): fuera los tests de IntentDetector.detect, `holds_padi_cert` y `certification_status` (se quitaron;
la certificacion y el reparto los decide el extractor); el nivel en tercera persona se sigue probando en `_HOLDS_CERT_RE`.
"""

import pytest

from src.agents.intent_detector import _HOLDS_CERT_RE, _WANTS_CERT_RE


def _holds_a_level(message):
    """Lo que leia `holds_padi_cert(message, about_writer=False)` (se quito con IntentDetector en lat-11 T6d): alguien
    TIENE un nivel PADI, sin querer sacarlo. Sigue vivo en `course_level_is_ambiguous`."""
    return bool(_HOLDS_CERT_RE.search(message)) and not _WANTS_CERT_RE.search(message)


@pytest.mark.parametrize("message", [
    "mi pareja tiene el advanced y quiere bucear",
    "mi novia tiene el open water y quiere bucear conmigo",
    "mis amigos tienen el advanced",
])
def test_third_person_holds_the_level(message):
    assert _holds_a_level(message)


@pytest.mark.parametrize("message", [
    "¿tienen el advanced?",
    "tiene el open water?",
    "hola, tienen el advanced disponible mañana?",
])
def test_asking_the_shop_is_not_holding(message):
    """Sin persona nombrada, "tienen el advanced" es preguntar si el centro lo ofrece."""
    assert not _holds_a_level(message)


def test_wanting_the_course_still_wins():
    assert not _holds_a_level("mi pareja quiere hacer el advanced")
