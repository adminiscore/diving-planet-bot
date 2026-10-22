"""ARQ-1c (22-oct): los hechos de cada intención los saca el código, con las reglas del negocio ya aplicadas."""
import pytest

from src.flows import hechos as h
from src.flows.state import ConversationState


def _conv(lang="es", **campos) -> ConversationState:
    st = ConversationState(conversation_id="arq1c", language=lang)
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def test_sin_origen_las_dos_variantes_y_la_pregunta_del_origen():
    [b] = h.hechos(_conv(), ["precio", "incluye", "enlace"], ["minicourse"])
    assert b["precio"]["cartagena"]["online"] == "183 USD" and b["precio"]["island"]["online"] == "134 USD"
    assert "Almuerzo" in b["incluye"]["cartagena"] and "Almuerzo" not in b["incluye"]["island"]
    assert set(b["enlace"]) == {"cartagena", "island"} and b["pregunta_pendiente"] == "origen"


def test_con_origen_solo_su_variante_y_sin_pregunta():
    [b] = h.hechos(_conv(location="island"), ["precio", "incluye"], ["snorkel"])
    assert set(b["precio"]) == {"island"} and "pregunta_pendiente" not in b


@pytest.mark.parametrize("campos, moneda", [({"is_colombian": True}, "COP"), ({"is_colombian": False}, "USD"),
                                            ({}, "USD"), ({"is_colombian": True, "mixed_nationality_notice": True}, "USD")])
def test_la_moneda_la_decide_el_codigo(campos, moneda):
    [b] = h.hechos(_conv(location="cartagena", **campos), ["precio"], ["minicourse"])
    assert b["moneda"] == moneda and moneda in b["precio"]["cartagena"]["online"]


def test_el_aporte_a_dive_to_heal_va_en_lo_que_incluye():
    """Decisión de Gadea (22-oct): se dice que va incluido."""
    [b] = h.hechos(_conv(location="cartagena"), ["incluye"], ["minicourse"])
    assert any("DIVE TO HEAL" in x for x in b["incluye"]["cartagena"])


def test_la_lista_completa_de_la_ficha():
    [b] = h.hechos(_conv(location="cartagena"), ["incluye"], ["padi_open_water"])
    lista = " | ".join(b["incluye"]["cartagena"])
    assert "4 inmersiones" in lista and "primer dia" in lista and "Tarjeta de certificacion" in lista


@pytest.mark.parametrize("actividad, formulario", [("minicourse", True), ("refresher", True), ("padi_open_water", True),
                                                    ("snorkel", False), ("certified_diving", False)])
def test_el_formulario_medico_solo_en_cursos_minicurso_y_refresher(actividad, formulario):
    [b] = h.hechos(_conv(location="cartagena"), ["requisitos"], [actividad])
    assert any("formulario medico" in r.lower() for r in b["requisitos"]) is formulario


def test_edad_en_cifra():
    [b] = h.hechos(_conv(), ["edad"], ["padi_advanced"])
    assert b["edad"]["minima"] == 12


def test_buceo_plan_base_y_los_demas_con_precio():
    [b] = h.hechos(_conv(location="cartagena"), ["precio"], ["certified_diving"])
    assert b["precio"]["cartagena"]["online"] == "178 USD" and len(b["otros_planes"]) >= 3


def test_colombiano_el_enlace_es_el_asesor():
    [b] = h.hechos(_conv(location="cartagena", is_colombian=True), ["enlace"], ["minicourse"])
    assert b["enlace"] == {"asesor": True}


def test_solo_las_intenciones_pedidas_y_varias_actividades():
    bloques = h.hechos(_conv(location="cartagena"), ["edad"], ["snorkel", "minicourse", "no_existe"])
    assert [b["actividad"] for b in bloques] == ["snorkel", "minicourse"]
    assert all(set(b) == {"actividad", "nombre", "origen", "edad"} for b in bloques)


def test_en_ingles():
    [b] = h.hechos(_conv("en", location="cartagena"), ["incluye"], ["minicourse"])
    assert "Lunch" in b["incluye"]["cartagena"]
