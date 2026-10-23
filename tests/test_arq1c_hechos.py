"""ARQ-1c (22-oct): los hechos de cada intención los saca el código, con las reglas del negocio ya aplicadas."""
import pytest

from src.config import settings
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


@pytest.fixture(autouse=True)
def _flags_de_siempre(monkeypatch):
    """Estos tests miran lo de siempre; las dos monedas (arq-5c) y las listas y frases por código (arq-7a/7d) tienen los
    suyos. Sin esto, con esos flags encendidos (el G10 nº 6) fallaban por diseño."""
    for flag in ("dos_monedas_sin_nacionalidad", "listas_por_codigo", "frases_por_codigo"):
        monkeypatch.setattr(settings, flag, False, raising=False)


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
    assert "4 inmersiones" in lista and "primer día" in lista and "Tarjeta de certificación" in lista


@pytest.mark.parametrize("actividad, formulario", [("minicourse", True), ("refresher", True), ("padi_open_water", True),
                                                    ("snorkel", False), ("certified_diving", False)])
def test_el_formulario_medico_solo_en_cursos_minicurso_y_refresher(actividad, formulario):
    [b] = h.hechos(_conv(location="cartagena"), ["requisitos"], [actividad])
    # con o sin tilde: con `requisitos_coherentes` el del minicurso es solo el de su ficha («formulario médico»)
    assert any("formulario medico" in r.lower().replace("é", "e") for r in b["requisitos"]) is formulario


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


def test_lo_que_no_incluye_y_el_almuerzo_de_las_islas():
    """Banco arq-1d, v2: «¿hay almuerzo?» desde las islas; sus fichas no dicen lo que no incluyen, la política sí."""
    [b] = h.hechos(_conv(location="island"), ["incluye"], ["snorkel"])
    assert any("almuerzo" in x for x in b["no_incluye"]["island"])
    [b] = h.hechos(_conv(location="cartagena"), ["incluye"], ["minicourse"])
    assert "Propinas voluntarias" in b["no_incluye"]["cartagena"]


def test_el_plan_base_del_buceo_en_las_islas_es_el_de_2_inmersiones():
    """Banco arq-1d, p4: en las islas el primero del registro es la salida de 1 inmersión (97 USD)."""
    [b] = h.hechos(_conv(location="island"), ["precio"], ["certified_diving"])
    assert b["precio"]["island"]["online"] == "124 USD"
    assert any(p["precio"]["online"] == "97 USD" for p in b["otros_planes"])
    assert all(p["precio"]["online"] != "124 USD" for p in b["otros_planes"])


def test_cada_precio_dice_de_que_plan_es():
    """Banco arq-1d F, p4: sin el nombre del plan, el redactor no podía decir que 124 USD es la salida de 2 inmersiones."""
    [b] = h.hechos(_conv(location="island"), ["precio"], ["certified_diving"])
    assert "2" in b["precio"]["island"]["plan"]


def test_el_precio_lleva_la_regla_de_la_moneda():
    """Core arq1d-B2: «tienen un precio especial para colombianos» recibía COP sin decir que no lo hay."""
    [b] = h.hechos(_conv(location="cartagena", is_colombian=True), ["precio"], ["padi_open_water"])
    assert "no hay descuento por ser colombiano" in b["regla_moneda"]


def test_arq3_faltan_los_hechos_que_la_respuesta_no_lleva():
    """ARQ-3: el código ve lo que el redactor se deja (banco G, v6: el referido sin la carta de referido firmada)."""
    st = _conv(location="cartagena")
    bloques = h.hechos(st, ["precio", "requisitos", "edad"], ["padi_open_water_referral"])
    completa = ("Cuesta 474 USD online o 526 USD sin reserva online. Desde los 10 años. Requisitos: "
                + " ".join(bloques[0]["requisitos"]) + " " + bloques[0]["alojamiento"])
    assert h.faltan(completa, bloques, ["precio", "requisitos", "edad"]) == []
    corta = "Cuesta 474 USD online. Lleva bañador y toalla."
    perdidos = h.faltan(corta, bloques, ["precio", "requisitos", "edad"])
    assert "526 USD" in perdidos and "edad 10" in perdidos
    assert any("referido" in p for p in perdidos)


def test_arq3_una_parafrasis_corta_cuenta(monkeypatch):
    # Solo la lista y la recogida de siempre (con arq-8d/8e van además lo que se hace y cómo se coordina).
    monkeypatch.setattr(h.settings, "incluye_lo_que_se_hace", False)
    monkeypatch.setattr(h.settings, "recogida_se_coordina", False)
    st = _conv(location="island")
    bloques = h.hechos(st, ["incluye"], ["snorkel"])
    lista = bloques[0]["incluye"]["island"]
    recogida = bloques[0]["recogida"]["island"][0]
    assert h.faltan("Incluye: " + "; ".join(x.lower() for x in lista) + ". " + recogida, bloques, ["incluye"]) == []


def test_la_recogida_y_el_alojamiento_van_en_los_hechos():
    """G10 de control (22-oct): faltaban «en Cartagena no se recoge en el hotel», «el regreso va incluido sin cargo» y
    «el alojamiento no está incluido» en los planes de varios días."""
    [b] = h.hechos(_conv(), ["incluye"], ["minicourse"])
    assert "no hay recogida en el hotel" in b["recogida"]["cartagena"][0]
    assert "sin cargo" in b["recogida"]["island"][0] and "alojamiento" not in b
    [b] = h.hechos(_conv(location="cartagena"), ["precio"], ["padi_advanced"])
    assert "no está incluido" in b["alojamiento"] and "recogida" not in b
    assert any("Muelle" in p for p in h.faltan("Cuesta 0 USD.", h.hechos(_conv(location="cartagena"), ["horario"],
                                                                          ["minicourse"]), ["horario"]))


def test_arq1m_con_la_disponibilidad_va_el_enlace(monkeypatch):
    from src.config import settings

    monkeypatch.setattr(settings, "enlace_con_disponibilidad", False)
    [b] = h.hechos(_conv(location="cartagena"), ["disponibilidad"], ["minicourse"])
    assert "enlace" not in b
    monkeypatch.setattr(settings, "enlace_con_disponibilidad", True)
    [b] = h.hechos(_conv(location="cartagena"), ["disponibilidad"], ["minicourse"])
    assert "book.divingplanet.org" in b["enlace"]["cartagena"]
    assert h.faltan("Siempre hay disponibilidad.", [b], ["disponibilidad"])
    [b] = h.hechos(_conv(location="cartagena", is_colombian=True), ["disponibilidad"], ["minicourse"])
    assert b["enlace"] == {"asesor": True}
