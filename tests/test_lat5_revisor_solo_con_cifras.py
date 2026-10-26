"""lat-5 (26-oct, fase LAT; Gadea #1792): el revisor del RAG solo se llama si la respuesta afirma algo comprobable que no
está en el contexto: una cifra (hora, edad, días, importe) o un día de la semana. Los importes, los enlaces y las
capacidades ya los comprueban las guardas de código antes; si todo lo demás está en el contexto, el revisor sobra
(0,5 s por turno del RAG en lat7-B). Sin red."""
import pytest

from src.agents.rag_agent import _hay_algo_que_revisar

CONTEXTO = "Salida a las 8:00 desde el Muelle de la Bodeguita. Precio 126 USD por persona. Edad mínima: 10 años."


@pytest.mark.parametrize("respuesta", [
    "Sales a las 8:00 desde el Muelle y cuesta 126 USD.",
    "Puedes hacerlo desde los 10 años.",
    "¡Es una experiencia increíble! Te ayudo a reservar.",
])
def test_sin_nada_nuevo_no_se_revisa(respuesta):
    assert _hay_algo_que_revisar(respuesta, CONTEXTO) is False


@pytest.mark.parametrize("respuesta", [
    "Sales a las 9:00.",  # una hora que el contexto no dice
    "Son 3 días de curso.",  # una cifra nueva
    "El sábado hay cupo.",  # un día de la semana que el contexto no dice
    "On Sunday we leave at 8:00.",
])
def test_una_cifra_o_un_dia_nuevo_se_revisa(respuesta):
    assert _hay_algo_que_revisar(respuesta, CONTEXTO) is True


def test_las_cifras_se_comparan_sin_separadores():
    assert _hay_algo_que_revisar("Son 1.429.000 COP.", "Precio: 1429000 COP") is False
