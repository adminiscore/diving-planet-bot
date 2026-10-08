"""8-oct (cambio de modelos): el Markdown de documento que escribe GPT-6 Luna se pasa a formato de WhatsApp."""

import pytest

from src.channels.formato import a_whatsapp


@pytest.mark.parametrize("entrada, salida", [
    ("cuesta **124 USD por persona online**", "cuesta *124 USD por persona online*"),
    ("[Reservar salida de buceo — 2 inmersiones](https://book.divingplanet.org/book/salidas-de-buceo/1?language=es)",
     "Reservar salida de buceo — 2 inmersiones: https://book.divingplanet.org/book/salidas-de-buceo/1?language=es"),
    ("[https://divingplanet.org/](https://divingplanet.org/)", "https://divingplanet.org/"),
    ("### Qué incluye\n- equipo", "*Qué incluye*\n- equipo"),
    ("~~antes~~ ahora", "~antes~ ahora"),
    ("__importante__", "*importante*"),
])
def test_markdown_a_whatsapp(entrada, salida):
    assert a_whatsapp(entrada) == salida


@pytest.mark.parametrize("texto", [
    "🤿 *Curso Basico PADI (Open Water)*\n💰 *693 USD* por persona",          # tarjeta fija del bot
    "_El precio es el mismo en pesos (COP) o dólares (USD)_",
    "https://book.divingplanet.org/book/basic-course/4?language=es",
    "2 * 3 = 6 y 5 * 2 = 10",                                                 # asteriscos sueltos
    "",
])
def test_lo_que_ya_es_de_whatsapp_no_cambia(texto):
    assert a_whatsapp(texto) == texto
