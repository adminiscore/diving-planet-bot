"""CALN-3 paso 4 (1) (29-oct, decisión de Gadea #2499): si la respuesta del RAG general da un precio del catálogo, sus
importes los cambia la pieza de `cotizar` (en la 5.ª, 12 de las 51 preguntas del origen eran de la puerta, que los
quitaba sin dar otros)."""
from src.agents import conversational_core as core
from src.flows.state import ConversationState, Step

RAG = ("El minicurso dura un día e incluye una inmersión en el mar con instructor. Cuesta 655.000 COP online "
       "saliendo desde Cartagena. ¿Quieres que te pase el enlace?")


def _st(location=None, **campos) -> ConversationState:
    st = ConversationState(conversation_id="caln3-p4", language="es")
    st.step = Step.FREE_TEXT
    st.location = location
    st.detected_activity = "minicourse"
    for campo, valor in campos.items():
        setattr(st, campo, valor)
    return st


def test_sin_origen_la_pieza_de_los_dos_y_la_pregunta():
    salida = core._con_la_pieza(_st(), RAG)
    assert "dura un día" in salida                               # lo que no es precio, queda
    assert "Cuesta 655.000" not in salida and "enlace?" not in salida  # su importe y su pregunta final, fuera
    assert "*Desde Cartagena*" in salida and "*Ya en las Islas del Rosario*" in salida
    assert "475.000" in salida                                   # el de las islas, que el RAG no dio
    assert salida.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES) and core._es_pregunta_de_origen(salida)


def test_con_origen_la_pieza_de_ese_y_sin_pregunta():
    salida = core._con_la_pieza(_st("cartagena"), RAG)
    assert "655.000" in salida and "475.000" not in salida
    assert "Desde Cartagena*" not in salida                      # un solo origen: sin rótulo
    assert not core._es_pregunta_de_origen(salida)


def test_con_el_origen_por_confirmar_se_confirma():
    salida = core._con_la_pieza(_st(pending_correction={"location": "island"}), RAG)
    assert salida.endswith(core._CONFIRMA_ORIGEN["island"]["es"])


def test_un_importe_que_no_es_del_catalogo_no_lleva_pieza():
    assert core._con_la_pieza(_st(), "La noche en el hotel sale por unos 380.000 COP.") is None
    assert core._con_la_pieza(_st(), "El minicurso dura un día; la salida es a las 8:00.") is None


def test_si_cotiza_otra_actividad_que_la_de_la_pieza_sigue_la_puerta():
    # Buzo que pregunta por el refresher: el RAG da el precio del minicurso y la pieza sería la del buceo.
    st = _st("cartagena", detected_activity="certified_diving")
    assert core._con_la_pieza(st, "El refresher se reserva como el minicurso: 655.000 COP online.") is None


def test_con_la_tarjeta_no_va_la_pieza():
    salida = core._puerta_del_origen(_st("cartagena"), "¿cuánto cuesta?", RAG, sin_precio=True)
    assert salida == RAG                                         # con el origen sabido, tal cual (la puerta de siempre)
