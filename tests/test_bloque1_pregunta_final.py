"""Bloque 1 (10-nov): `_sin_la_pregunta_final` se cuenta (`[CORE][B1]` en la traza y `pregunta_final` en [TURN_METRICS])
y no quita un párrafo que lleve un importe o un enlace: con la pregunta se iba el precio o el enlace. Frases nuestras, sin
IA."""
import logging

import pytest

import src.observability as obs
from src.agents.nucleo.origen_precio import _sin_la_pregunta_final


@pytest.fixture
def apuntado(monkeypatch):
    notas = {}
    monkeypatch.setattr(obs, "note_turn", lambda **k: notas.update(k))
    return notas


def test_quita_la_pregunta_suelta_y_lo_cuenta(apuntado, caplog):
    texto = "El snorkel incluye las gafas y el tubo.\n\n¿Ya sabes qué día te viene mejor?"
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        assert _sin_la_pregunta_final(texto) == "El snorkel incluye las gafas y el tubo."
    assert apuntado == {"pregunta_final": "quitada"}
    assert "[CORE][B1]" in caplog.text


@pytest.mark.parametrize("final", [
    "Para los dos sale en 190 USD por persona, ¿te lo aparto?",
    "Son 380.000 COP cada uno. ¿Quieres reservarlo?",
    "Reserva aquí: https://book.divingplanet.org/book/minicurso/12 ¿Te sirve el sábado?",
    "Lo tienes en https://book.divingplanet.org/book/snorkel/7?origen=cartagena",  # el «?» del enlace no es pregunta
])
def test_un_parrafo_con_importe_o_enlace_se_queda(apuntado, caplog, final):
    texto = f"El minicurso dura medio día.\n\n{final}"
    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        assert _sin_la_pregunta_final(texto) == texto
    assert apuntado == {"pregunta_final": "conservada"}
    assert "[CORE][B1]" in caplog.text


@pytest.mark.parametrize("texto", [
    "El minicurso dura medio día.\n\nIncluye el equipo.",  # sin pregunta
    "¿Desde dónde saldrías?",  # sin otro texto, se queda como antes
])
def test_sin_pregunta_final_no_cambia_ni_cuenta(apuntado, texto):
    assert _sin_la_pregunta_final(texto) == texto
    assert apuntado == {}


def test_el_contador_sale_en_las_metricas_del_turno():
    linea = obs.turn_metrics_line("c", {"pregunta_final": "quitada"}, "2026-11-10T09:00:00Z", 1.0)
    assert '"pregunta_final": "quitada"' in linea
