"""CALN-43 P9 y P10 (decisiones de Gadea, 6-nov): el grupo de 5 o más reserva con un asesor antes del enlace, para no perder el descuento
de grupo; un grupo con una parte del plan sin enlace reserva todo por el asesor. Cuentan para los 5 los que hacen una actividad con
descuento (buceo recreativo, minicurso, snorkel, acompañante; no cursos PADI ni Bubble Makers). Sin IA."""
import pytest

from src.agents.nucleo import slotfill_close
from src.flows import hechos
from src.flows.como_reserva import (
    ASESOR,
    ENLACE,
    GRUPO,
    HOTEL_PRIMERO,
    PARTE_SIN_ENLACE,
    como_reserva,
    minimo_del_grupo,
    partes_del_plan,
    personas_con_descuento_de_grupo,
    por_que_el_asesor,
)
from src.flows.state import ConversationState, Step


def _grupo(reparto=None, *, actividad=None, n=None, lang="es", **campos) -> ConversationState:
    st = ConversationState(conversation_id="caln43-grupos", language=lang, location="cartagena", is_colombian=False)
    st.detected_group_allocation = reparto or {}
    st.detected_activity = actividad or (next(iter(reparto)) if reparto else None)
    st.detected_group_size = n if n is not None else (sum(reparto.values()) if reparto else None)
    if reparto and "certified_diving" in reparto:
        st.is_certified = True
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def test_el_minimo_sale_de_discounts_json():
    assert minimo_del_grupo() == 5


@pytest.mark.parametrize(("estado", "esperado"), [
    # b03 (panel 059c): 6 amigos, 4 al minicurso y 2 a bucear, grupo mixto que paga en dólares: pagaban online sin pedir el descuento.
    (lambda: _grupo({"minicourse": 4, "certified_diving": 2}, mixed_nationality_notice=True), GRUPO),
    (lambda: _grupo({"minicourse": 2, "certified_diving": 2}), ENLACE),  # 4: sin descuento de grupo
    (lambda: _grupo({"certified_diving": 2, "snorkel": 2, "companion": 1}), GRUPO),  # el acompañante cuenta
    (lambda: _grupo(actividad="snorkel", n=5), GRUPO),  # sin reparto: todos en la actividad
    (lambda: _grupo(actividad="padi_open_water", n=5), ENLACE),  # cursos PADI: no hay descuento de grupo
    (lambda: _grupo({"minicourse": 6}, is_colombian=True), ASESOR),  # colombianos: ya los cierra un asesor
    (lambda: _grupo({"minicourse": 6}, location="island"), HOTEL_PRIMERO),  # primero el hotel
    (lambda: _grupo(), ENLACE),  # sin actividad, nada que contar
])
def test_p9_el_grupo_de_cinco_o_mas(estado, esperado):
    assert como_reserva(estado()) == esperado


@pytest.mark.parametrize(("estado", "esperado"), [
    # 6951 (tanda s05f): los padres al minicurso por el enlace y el niño de 9 (Bubble Makers) por un asesor: dos caminos.
    (lambda: _grupo({"minicourse": 3}, detected_ages=[9]), PARTE_SIN_ENLACE),
    # Bubble Makers no cuenta para el descuento: 3 adultos y 2 niños de 9 son 3, no 5; pero hay una parte sin enlace.
    (lambda: _grupo({"minicourse": 5}, detected_ages=[9, 9]), PARTE_SIN_ENLACE),
    # Un buzo y su acompañante desde las islas: la salida tiene enlace y el acompañante no.
    (lambda: _grupo({"certified_diving": 1, "companion": 1}, location="island", hotel="cocoliso"), PARTE_SIN_ENLACE),
    # Una persona con un plan sin enlace (las 4 diurnas): como hoy, la tarjeta lo pasa al asesor.
    (lambda: _grupo({"certified_diving": 1}, detected_cert_days=2), ENLACE),
    # Todo con enlace: por el enlace.
    (lambda: _grupo({"certified_diving": 2, "snorkel": 1}), ENLACE),
])
def test_p10_una_parte_sin_enlace(estado, esperado):
    assert como_reserva(estado()) == esperado


def test_contar_las_partes_no_toca_el_estado():
    st = _grupo({"minicourse": 3}, detected_ages=[9])
    partes = partes_del_plan(st)
    assert st.mixed_cart == [] and [p["actividad"] for p in partes] == ["minicourse", "bubble_makers"]
    assert personas_con_descuento_de_grupo(partes) == 2


def test_el_porque_lleva_las_cifras_de_la_base_y_no_pregunta():
    assert "5 o más" in por_que_el_asesor(GRUPO, "es") and "10 %" in por_que_el_asesor(GRUPO, "es")
    assert "10%" in por_que_el_asesor(GRUPO, "en")
    assert all("?" not in por_que_el_asesor(f, lang) for f in (GRUPO, PARTE_SIN_ENLACE) for lang in ("es", "en"))
    assert por_que_el_asesor(ENLACE, "es") is None and por_que_el_asesor(ASESOR, "es") is None


# ─── El cierre ───

def test_si_solo_cotiza_ve_el_precio_sin_enlaces_y_se_le_ofrece_el_asesor():
    st = _grupo({"minicourse": 4, "certified_diving": 2}, mixed_nationality_notice=True)
    texto = slotfill_close._finalize(st, pasar_al_asesor=False)
    assert "book.divingplanet.org" not in texto and "USD" in texto
    assert por_que_el_asesor(GRUPO, "es") in texto and texto.endswith(slotfill_close._OFERTA_DEL_ASESOR["es_grupo"])
    assert st.step != Step.ESCALATE and not st.pending_escalation_reason


def test_si_pide_reservar_pasa_directo():
    st = _grupo({"minicourse": 3}, detected_ages=[9], lang="en")
    texto = slotfill_close._finalize(st, pasar_al_asesor=True)
    assert "book.divingplanet.org" not in texto and por_que_el_asesor(PARTE_SIN_ENLACE, "en") in texto
    assert texto.endswith(slotfill_close._PASE_DEL_GRUPO["en"])
    assert st.step == Step.ESCALATE and "parte del plan sin enlace" in st.pending_escalation_reason


def test_con_la_tarjeta_ya_vista_solo_el_pase():
    st = _grupo({"minicourse": 4, "certified_diving": 2}, mixed_nationality_notice=True)
    slotfill_close._finalize(st, pasar_al_asesor=False)
    assert slotfill_close._finalize(st, pasar_al_asesor=True) == slotfill_close._PASE_DEL_GRUPO["es"]


def test_el_si_a_la_oferta_se_reconoce():
    st = _grupo({"minicourse": 4, "certified_diving": 2}, mixed_nationality_notice=True)
    st.history = [{"role": "assistant", "content": slotfill_close._finalize(st, pasar_al_asesor=False)}]
    st._senales_router = {}
    assert slotfill_close._quiere_reservar_o_pagar(st, "Sí, por favor")


def test_el_grupo_de_cuatro_cierra_con_el_enlace_como_hoy():
    texto = slotfill_close._finalize(_grupo({"minicourse": 2, "certified_diving": 2}), pasar_al_asesor=False)
    assert "book.divingplanet.org" in texto


# ─── Lo que recibe el escritor ───

def test_el_escritor_recibe_el_asesor_y_el_porque_sin_enlaces():
    st = _grupo({"minicourse": 4, "certified_diving": 2}, mixed_nationality_notice=True)
    [bloque, *_] = hechos.hechos(st, ["enlace"], ["minicourse"])
    assert bloque["enlace"] == {"asesor": True} and bloque["por_el_asesor"] == por_que_el_asesor(GRUPO, "es")
