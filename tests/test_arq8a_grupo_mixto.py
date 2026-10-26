"""arq-8a (23-oct, flag `grupo_mixto_en_descuentos`; G10 nº 6, g10-043): en un grupo mixto, la lista de descuentos lleva
la regla del grupo mixto (toda la reserva en USD) en vez de «los colombianos pagan en COP»."""
import pytest

from src.flows import hechos as h
from src.flows.state import ConversationState


def _conv(lang="es", **campos) -> ConversationState:
    st = ConversationState(conversation_id="arq8a", language=lang)
    for k, v in campos.items():
        setattr(st, k, v)
    return st


@pytest.mark.parametrize("lang, todo_en_usd, cop", [("es", "toda la reserva del grupo se paga en dólares", "pagan en pesos"),
                                                    ("en", "whole group booking is paid in US dollars", "pay in Colombian")])
def test_en_un_grupo_mixto_el_descuento_lleva_la_regla_del_grupo(monkeypatch, lang, todo_en_usd, cop):
    [b] = h.hechos(_conv(lang, mixed_nationality_notice=True), ["descuento"], ["snorkel"])
    texto = " ".join(b["descuento"])
    assert todo_en_usd in texto and cop not in texto
    assert len(b["descuento"]) == 5  # online, grupo, equipo propio y que no se acumulan siguen


def test_con_los_descuentos_en_un_sitio_tambien(monkeypatch):
    """arq-8h (Álvaro): la lista sale del catálogo; la regla del grupo mixto se aplica igual."""
    [b] = h.hechos(_conv(mixed_nationality_notice=True), ["descuento"], ["snorkel"])
    texto = " ".join(b["descuento"])
    assert "toda la reserva del grupo se paga en dólares" in texto and "pagan en pesos" not in texto
    assert len(b["descuento"]) == 5


def test_sin_actividad_tambien(monkeypatch):
    [b] = h.hechos_sin_actividad(_conv(mixed_nationality_notice=True), ["descuento"])
    assert "toda la reserva del grupo se paga en dólares" in " ".join(b["descuento"])


def test_sin_grupo_mixto_la_de_siempre():
    [b] = h.hechos(_conv(mixed_nationality_notice=False), ["descuento"], ["snorkel"])
    texto = " ".join(b["descuento"])
    assert "pagan en pesos colombianos" in texto and "toda la reserva del grupo" not in texto
