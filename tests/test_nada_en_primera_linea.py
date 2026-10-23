"""22-oct (flag `nada_en_primera_linea`): la palabra de control «NADA» de contestar antes del pase no llega al cliente
aunque `rag_answer` haya pegado el aviso al final detrás. Caso real: ronda core arq2a-A, clima-y-cancelacion t2."""
import pytest

from src.agents.escalation_agent import _es_nada

# El texto real que le llegó al cliente (sin el saludo), con el aviso al final pegado detrás.
CASO_REAL = ("NADA\n\nOperamos todos los días salvo el 25 de diciembre y el 1 de enero; la seguridad va primero y, si el "
             "mar no está apto, la salida se reprograma.")


@pytest.mark.parametrize("respuesta", [CASO_REAL, "NADA", "NADA.", "**NADA**", "nada", "  NADA  \n\nOtra línea"])
def test_con_el_flag_la_palabra_de_control_se_detecta_aunque_lleve_el_aviso(monkeypatch, respuesta):
    assert _es_nada(respuesta)


@pytest.mark.parametrize("respuesta", [
    "Nada, no hace falta saber nadar para el snorkel: llevas chaleco.",
    "No hace falta nada especial: el equipo va incluido.",
    "El minicurso cuesta 183 USD online.\nNADA",
])
def test_una_respuesta_de_verdad_no_es_la_palabra_de_control(monkeypatch, respuesta):
    assert not _es_nada(respuesta)
