"""s05b especialidad t2 y s04n suizos t2: con la tarjeta, la respuesta se rehacía sin precio y, si salía «no lo tengo a la mano», el
cierre la tiraba: el cliente preguntaba y recibía solo «¡Perfecto!» y la tarjeta (2 de 43 rehechos en las charlas guardadas)."""
from src.agents import rag_agent
from src.agents.nucleo import slotfill_close as sc

PRIMERA = "La especialidad dura una mañana. Cuesta 344 USD por persona. Sí, puedes bucear al día siguiente."


def test_si_lo_rehecho_sirve_va_lo_rehecho():
    assert sc._rehecha_o_sin_importes("Dura una mañana.", PRIMERA) == "Dura una mañana."


def test_si_lo_rehecho_es_el_no_lo_se_va_la_primera_sin_importes():
    for rehecha in (rag_agent.FALLBACK_ES, rag_agent.FALLBACK_EN, f"¡Hola! {rag_agent.FALLBACK_ES}", "", None):
        salida = sc._rehecha_o_sin_importes(rehecha, PRIMERA)
        assert "dura una mañana" in salida and "día siguiente" in salida and "344" not in salida


def test_lo_que_sale_no_es_un_fallback_que_el_cierre_vuelva_a_tirar():
    assert not sc._is_rag_fallback(sc._rehecha_o_sin_importes(rag_agent.FALLBACK_ES, PRIMERA))
