"""arq-7a (23-oct, flag `listas_por_codigo`, latencia): las listas largas del redactor las pone el código donde el modelo
deja su marca (G10 nº 5: el redactor escribía dos veces en 53 de 79 turnos porque el borrador resumía las listas)."""

import pytest

from src.agents import redactor_hechos as rh
from src.config import settings

_B = [{"nombre": "Minicurso", "incluye": {"cartagena": ["Seguro de buceo", "Equipo", "Almuerzo"],
                                          "island": ["Recogida en hotel", "Seguro de buceo"]}}]


def test_la_marca_se_cambia_por_la_lista_entera_con_sus_origenes():
    answer = rh._poner_listas("El minicurso incluye:\n[[incluye]]\n\nNos vemos.", _B, ["incluye"], "es")
    assert "[[incluye]]" not in answer and "• Almuerzo" in answer and "• Recogida en hotel" in answer
    assert "*Desde Cartagena:*" in answer and answer.endswith("Nos vemos.")


def test_sin_marca_ni_lista_va_al_final():
    answer = rh._poner_listas("Incluye seguro.", _B, ["incluye"], "es")
    assert answer.startswith("Incluye seguro.") and "• Equipo" in answer


def test_si_el_modelo_la_escribio_se_queda_la_suya():
    escrita = "Incluye: seguro de buceo, equipo, almuerzo; en las islas recogida en hotel y seguro de buceo."
    assert rh._poner_listas(escrita, _B, ["incluye"], "es") == escrita


def test_una_lista_que_no_se_pidio_no_se_pone():
    assert rh._poner_listas("Cuesta 183 USD.", _B, ["precio"], "es") == "Cuesta 183 USD."


@pytest.mark.parametrize("flag", [False, True])
def test_el_prompt_pide_la_marca_solo_con_el_flag(monkeypatch, flag):
    monkeypatch.setattr(settings, "listas_por_codigo", flag)
    assert ("[[incluye]]" in rh._mensajes("es", [], "¿qué incluye?", "[]")[0]["content"]) is flag


_C = [{"nombre": "Snorkel", "recogida": {"cartagena": ["Muelle de la Bodeguita, a 5 minutos del centro, a las 8:00."],
                                         "island": ["Recogida en el hotel entre las 9:30 y las 9:45, sin cargo."]},
       "alojamiento": "Hay que dormir una noche en las islas; el alojamiento no está incluido."}]


def test_arq7d_la_recogida_y_el_alojamiento_por_codigo(monkeypatch):
    monkeypatch.setattr(settings, "frases_por_codigo", True)
    answer = rh._poner_listas("Así llegas:\n[[recogida]]\n\n[[alojamiento]]", _C, ["horario"], "es")
    assert "[[" not in answer and "Bodeguita" in answer and "9:30 y las 9:45" in answer
    assert "*Desde Cartagena:*" in answer and "el alojamiento no está incluido" in answer


def test_arq7d_sin_el_flag_no_toca_las_frases(monkeypatch):
    monkeypatch.setattr(settings, "frases_por_codigo", False)
    assert rh._poner_listas("Así llegas: [[recogida]]", _C, ["horario"], "es") == "Así llegas: [[recogida]]"
