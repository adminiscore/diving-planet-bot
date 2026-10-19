"""ex-9b (19-oct, flag `pii_respeta_urls`, ronda ex9b-5, punto-encuentro): antes de mandar el texto a OpenRouter se tapan
los datos personales, y las coordenadas del enlace de Google Maps del punto de encuentro se tapaban como teléfono. El
respaldo del RAG (DeepSeek) devolvía el enlace roto. Con el flag no se tapan las cifras DENTRO de un enlace, salvo en
los de WhatsApp, que llevan un teléfono."""

import pytest

from src.config import settings
from src.privacy import redact_pii, redact_pii_por_lineas

MAPS = ("https://www.google.com/maps/place/Muelle+de+la+Bodeguita/@10.4199447,-75.5537609,828m/data=!3m2!1e3!4b1!4m6"
        "!3m5!1s0x8ef62f753729822d:0x1bbcdd8224d0eaaf!8m2!3d10.4199447!4d-75.551186!16s%2Fg%2F113gzkckf?entry=ttu")


@pytest.mark.parametrize("encendido, intacto", [(False, False), (True, True)])
def test_el_enlace_de_maps(monkeypatch, encendido, intacto):
    monkeypatch.setattr(settings, "pii_respeta_urls", encendido)
    texto = f"El punto de encuentro: {MAPS} a las 8"
    assert (redact_pii(texto) == texto) is intacto
    assert (redact_pii_por_lineas(texto) == texto) is intacto


def test_un_telefono_fuera_del_enlace_se_sigue_tapando(monkeypatch):
    monkeypatch.setattr(settings, "pii_respeta_urls", True)
    out = redact_pii(f"llámame al 300 123 4567, el sitio es {MAPS}")
    assert "300 123 4567" not in out and MAPS in out


def test_un_enlace_de_whatsapp_se_sigue_tapando(monkeypatch):
    monkeypatch.setattr(settings, "pii_respeta_urls", True)
    assert "573001234567" not in redact_pii("escríbeme a https://wa.me/573001234567")


def test_una_cedula_con_su_palabra_se_sigue_tapando(monkeypatch):
    monkeypatch.setattr(settings, "pii_respeta_urls", True)
    out = redact_pii("mi cédula es 1.023.456.789 y reservé en https://book.divingplanet.org/book/123456789")
    assert "1.023.456.789" not in out and "book/123456789" in out
