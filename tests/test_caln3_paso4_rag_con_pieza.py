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


def test_sin_origen_fuera_su_enlace_de_reserva():
    # medida caln6-B1: el enlace de Cartagena se quedaba sin saber de dónde sale
    con_enlace = ("El snorkel dura medio día. Cuesta 448.000 COP. Reserva aquí: "
                  "https://book.divingplanet.org/book/superficio/3?language=es. ¿Te ayudo?")
    st = _st(detected_activity="snorkel")
    salida = core._con_la_pieza(st, con_enlace)
    assert "book.divingplanet.org" not in salida and "dura medio día" in salida
    assert salida.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES)
    st.location = "cartagena"  # con el origen, el enlace se queda
    assert "book.divingplanet.org" in core._con_la_pieza(st, con_enlace)


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


def test_si_cotiza_otro_plan_la_pieza_es_la_de_ese():
    # Buzo que pregunta por el refresher: el RAG da el precio del minicurso, no el del buceo (caln6-B1)
    st = _st("cartagena", detected_activity="certified_diving")
    salida = core._con_la_pieza(st, "El refresher se reserva como el minicurso: 655.000 COP online.")
    assert "Minicurso de Buceo: 183 USD" in salida and "630.000" not in salida
    # «quiero reservar el paquete de 5 buceos» con la salida de 2 de base: el paquete, de los dos orígenes
    salida = core._con_la_pieza(_st(detected_activity="certified_diving"), "El paquete de 5 cuesta 1.429.000 COP.")
    assert "1.429.000" in salida and "1.000.000" in salida and salida.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES)


def test_si_la_cifra_no_es_de_ningun_plan_la_puerta_de_siempre():
    assert core._con_la_pieza(_st(), "Te sale por 999.999 COP.") is None


def test_con_la_tarjeta_no_va_la_pieza():
    salida = core._puerta_del_origen(_st("cartagena"), "¿cuánto cuesta?", RAG, sin_precio=True)
    assert salida == RAG                                         # con el origen sabido, tal cual (la puerta de siempre)


# CALN-19 (4-nov, sparring s04g, holanda t1): en un mensaje mezclado, se le dice ANTES al escritor que no escriba importes.
def _bloques():
    from src.flows import hechos

    return hechos.hechos(_st(), ["precio"], ["minicourse"])


def test_mezclado_que_pide_precio_el_escritor_no_escribe_importes():
    st = _st()
    st._jev_pide_precio = True
    bloques = _bloques()
    entradas = {"hechos_bloques": (bloques, ["precio", "edad"])}
    assert core._precios_por_codigo(st, entradas) is True
    assert entradas["precios_por_codigo"] is True and entradas["hechos_bloques"] == (bloques, ["edad"])


def test_sin_precio_o_sin_pedirlo_no_cambia_nada():
    st = _st()
    st._jev_pide_precio = True
    entradas = {"hechos_bloques": (_bloques(), ["incluye"])}
    assert core._precios_por_codigo(st, entradas) is False and "precios_por_codigo" not in entradas
    assert core._precios_por_codigo(st, {}) is False
    # arq-8f: «precio» guardado a la espera del origen en un turno que pregunta otra cosa: como `pide_ahora`
    st._jev_pide_precio = False
    entradas = {"hechos_bloques": (_bloques(), ["precio"])}
    assert core._precios_por_codigo(st, entradas) is False and "precios_por_codigo" not in entradas


def test_con_la_pieza_pedida_va_aunque_el_texto_no_traiga_importes():
    st = _st()
    st._hechos_del_rag = (_bloques(), ["precio"])
    texto = "El minicurso dura un día e incluye una inmersión con instructor. Te dejo el precio a continuación."
    assert core._con_la_pieza(st, texto) is None  # sin pedirla, como hasta hoy
    salida = core._con_la_pieza(st, texto, pieza_pedida=True)
    assert salida.startswith("El minicurso dura un día") and "655.000" in salida and "475.000" in salida
    assert salida.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES)


def test_al_recoger_con_el_origen_ya_guardado_no_se_repregunta():
    # u3-4: la respuesta en paralelo se recoge cuando la extracción ya guardó el origen que los hechos no sabían
    st = _st("cartagena")
    st._hechos_del_rag = (_bloques(), ["precio"])
    salida = core._con_la_pieza(st, "El minicurso dura un día.", pieza_pedida=True)
    assert "655.000" in salida and "475.000" not in salida and not core._es_pregunta_de_origen(salida)


async def test_el_escritor_recibe_la_regla_y_la_pieza_va_debajo(monkeypatch):
    from unittest.mock import AsyncMock

    from src.agents import supervisor

    st = _st()
    st._jev_pide_precio = True
    bloques = _bloques()

    async def hechos_rag(state, message, history, **_k):
        state._hechos_del_rag = (bloques, ["precio", "edad"])
        return "[hechos]"

    recibido = {}

    async def escritor(message, **kw):
        recibido.update(kw)
        return "El minicurso es para mayores de 10 años. Te dejo el precio a continuación."

    monkeypatch.setattr(core, "_con_hechos", AsyncMock(return_value=None))
    monkeypatch.setattr(core, "_hechos_para_el_rag", hechos_rag)
    monkeypatch.setattr(supervisor, "rag_answer", escritor)
    salida = await core._rag_answer(st, "¿cuánto cuesta y desde qué edad?", history=[])
    assert recibido["precios_por_codigo"] is True and recibido["hechos_bloques"][1] == ["edad"]
    assert salida.startswith("El minicurso es para mayores") and "*Precios por persona*" in salida
