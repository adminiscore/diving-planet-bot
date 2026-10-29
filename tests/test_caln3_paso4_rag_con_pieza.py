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
    salida = core._con_la_pieza(_st(), "¿cuánto cuesta?", RAG)
    assert "dura un día" in salida                               # lo que no es precio, queda
    assert "Cuesta 655.000" not in salida and "enlace?" not in salida  # su importe y su pregunta final, fuera
    assert "*Desde Cartagena*" in salida and "*Ya en las Islas del Rosario*" in salida
    assert "475.000" in salida                                   # el de las islas, que el RAG no dio
    assert salida.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES) and core._es_pregunta_de_origen(salida)


def test_sin_origen_fuera_su_enlace_de_reserva():
    # medida caln6-B1: el enlace de Cartagena se quedaba sin saber de dónde sale
    con_enlace = ("El snorkel dura medio día. Cuesta 448.000 COP. Reserva aquí: "
                  "https://book.divingplanet.org/book/superficio/3?language=es. ¿Te ayudo?")
    st = _st(detected_activity="snorkel")
    salida = core._con_la_pieza(st, "¿cuánto cuesta?", con_enlace)
    assert "book.divingplanet.org" not in salida and "dura medio día" in salida
    assert salida.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES)
    st.location = "cartagena"  # con el origen, el enlace se queda
    assert "book.divingplanet.org" in core._con_la_pieza(st, "¿cuánto cuesta?", con_enlace)


def test_con_origen_la_pieza_de_ese_y_sin_pregunta():
    salida = core._con_la_pieza(_st("cartagena"), "¿cuánto cuesta?", RAG)
    assert "655.000" in salida and "475.000" not in salida
    assert "Desde Cartagena*" not in salida                      # un solo origen: sin rótulo
    assert not core._es_pregunta_de_origen(salida)


def test_con_el_origen_por_confirmar_se_confirma():
    salida = core._con_la_pieza(_st(pending_correction={"location": "island"}), "¿cuánto cuesta?", RAG)
    assert salida.endswith(core._CONFIRMA_ORIGEN["island"]["es"])


def test_un_importe_que_no_es_del_catalogo_no_lleva_pieza():
    assert core._con_la_pieza(_st(), "¿cuánto cuesta?", "La noche en el hotel sale por unos 380.000 COP.") is None
    assert core._con_la_pieza(_st(), "¿cuánto cuesta?", "El minicurso dura un día; la salida es a las 8:00.") is None


def test_si_cotiza_otro_plan_la_pieza_es_la_de_ese():
    # Buzo que pregunta por el refresher: el RAG da el precio del minicurso, no el del buceo (caln6-B1)
    st = _st("cartagena", detected_activity="certified_diving")
    salida = core._con_la_pieza(st, "¿cuánto cuesta?", "El refresher se reserva como el minicurso: 655.000 COP online.")
    assert "Minicurso de Buceo: 183 USD" in salida and "630.000" not in salida
    # «quiero reservar el paquete de 5 buceos» con la salida de 2 de base: el paquete, de los dos orígenes
    salida = core._con_la_pieza(_st(detected_activity="certified_diving"), "¿cuánto cuesta?", "El paquete de 5 cuesta 1.429.000 COP.")
    assert "1.429.000" in salida and "1.000.000" in salida and salida.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES)


def test_si_la_cifra_no_es_de_ningun_plan_la_puerta_de_siempre():
    assert core._con_la_pieza(_st(), "¿cuánto cuesta?", "Te sale por 999.999 COP.") is None


def test_con_la_tarjeta_no_va_la_pieza():
    salida = core._puerta_del_origen(_st("cartagena"), "¿cuánto cuesta?", RAG, sin_precio=True)
    assert salida == RAG                                         # con el origen sabido, tal cual (la puerta de siempre)


# CALN-3 paso 4 (2): lo que hacía la puerta del origen, quitada, lo hace la pieza.
def test_un_enlace_de_reserva_sin_origen_lleva_la_pieza_y_la_pregunta():
    sin_importe = "Aquí lo reservas: https://book.divingplanet.org/book/superficio/3?language=es. ¡Te va a encantar!"
    salida = core._con_la_pieza(_st(detected_activity="snorkel"), "mándame el enlace", sin_importe)
    assert "book.divingplanet.org" not in salida and "448.000" in salida and "150.000" in salida
    assert salida.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES)
    assert core._con_la_pieza(_st("island", detected_activity="snorkel"), "mándame el enlace", sin_importe) is None


def test_si_el_cliente_nombra_el_origen_la_pieza_va_sin_repreguntar():
    salida = core._con_la_pieza(_st(), "salimos desde Cartagena, ¿cuánto cuesta?", RAG)
    assert "655.000" in salida and not core._es_pregunta_de_origen(salida)
    st = _st()
    st.history = [{"role": "user", "content": "we will book our hotel on the island"}]
    assert not core._es_pregunta_de_origen(core._con_la_pieza(st, "how much is it?", RAG))
    # lo que dice el BOT no cuenta
    st.history = [{"role": "assistant", "content": "saliendo desde Cartagena o desde las propias islas"}]
    assert core._con_la_pieza(st, "¿cuánto cuesta?", RAG).endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES)


def test_con_la_tarjeta_tal_cual():
    assert core._puerta_del_origen(_st(), "¿cuánto cuesta?", RAG, sin_precio=True) == RAG
