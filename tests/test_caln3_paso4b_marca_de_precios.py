"""CALN-3 paso 4 (b) (29-oct, idea de Gadea #2504): el escritor no ve importes (en su contexto, «(precio)») y, si su
respuesta necesita un precio, deja la marca; el código pone ahí la pieza de `cotizar`."""
import re

from src.agents import conversational_core as core
from src.agents.rag_agent import sin_importes
from src.flows.catalog import catalog_facts
from src.flows.state import ConversationState, Step
from src.prompts.info import MARCA_PRECIOS

CON_MARCA = (f"El minicurso dura un día e incluye una inmersión en el mar con instructor.\n\n{MARCA_PRECIOS}\n\n"
             "¿Quieres que te pase el enlace?")


def _st(location=None, **campos) -> ConversationState:
    st = ConversationState(conversation_id="caln3-p4b", language="es")
    st.step = Step.FREE_TEXT
    st.location = location
    st.detected_activity = "minicourse"
    for campo, valor in campos.items():
        setattr(st, campo, valor)
    return st


def test_el_escritor_no_ve_importes():
    assert not re.search(r"\d[\d.,]*\s*(?:USD|COP)", sin_importes(catalog_facts("es")))
    assert sin_importes("2 inmersiones: 178 USD / 630.000 COP online, 197 USD / 700.000 COP normal") == \
        "2 inmersiones: (precio) online, (precio) normal"
    assert sin_importes("Cuesta $124 USD.") == "Cuesta (precio)."
    # lo que no es un importe, queda
    assert sin_importes("Sale a las 8:00, 18 horas antes de volar, 2 inmersiones, 10 % online") == \
        "Sale a las 8:00, 18 horas antes de volar, 2 inmersiones, 10 % online"


def test_sin_origen_la_pieza_en_la_marca_y_la_pregunta_del_origen():
    salida = core.con_los_precios(_st(), CON_MARCA)
    assert MARCA_PRECIOS not in salida and salida.startswith("El minicurso dura un día")
    assert "*Desde Cartagena*" in salida and "655.000" in salida and "475.000" in salida
    assert "enlace?" not in salida                               # su pregunta la sustituye la del origen
    assert salida.endswith(core.ORIGEN_TRAS_LAS_VARIANTES_ES) and core._es_pregunta_de_origen(salida)


def test_con_origen_la_pieza_de_ese_y_su_pregunta():
    salida = core.con_los_precios(_st("island"), CON_MARCA)
    assert "475.000" in salida and "655.000" not in salida
    assert salida.endswith("¿Quieres que te pase el enlace?")


def test_con_el_origen_por_confirmar_se_confirma():
    salida = core.con_los_precios(_st(pending_correction={"location": "cartagena"}), CON_MARCA)
    assert salida.endswith(core._CONFIRMA_ORIGEN["cartagena"]["es"])


def test_con_la_tarjeta_la_marca_sale_sin_mas():
    salida = core._puerta_del_origen(_st(), "¿qué incluye?", CON_MARCA, sin_precio=True)
    assert MARCA_PRECIOS not in salida and "(online · normal)" not in salida
    assert salida == "El minicurso dura un día e incluye una inmersión en el mar con instructor.\n\n" \
                     "¿Quieres que te pase el enlace?"


def test_sin_pregunta_la_pone_quien_llama():
    salida = core.con_los_precios(_st(), CON_MARCA, con_pregunta=False)
    assert "655.000" in salida and salida.endswith("¿Quieres que te pase el enlace?")


def test_sin_marca_la_puerta_de_siempre():
    assert core._puerta_del_origen(_st("cartagena"), "¿qué incluye?", "Incluye el equipo.") == "Incluye el equipo."
