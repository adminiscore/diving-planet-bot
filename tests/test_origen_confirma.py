"""ORIGEN-CONFIRMA (27-oct, idea de Álvaro #2080, decisión de Gadea #2082): cuando el extractor lee un origen con su cita
y Jev, seguro, dice que el mensaje no lo da (CAL-C3c), no se tira en silencio para volver a preguntar «¿desde dónde
saldrías?» («Va quiero comprar sin ir de cartagena» → la misma pregunta: repregunta en paquete-5-buceos-islas-residente):
se confirma UNA vez lo leído, sin cotizar ese origen hasta que conteste. Sin red."""
import pytest

from src.agents import conversational_core as core
from src.agents.nucleo import routing
from src.flows.state import ConversationState

JEV_NONE = {"choice": "none", "confidence": 0.9}


def _intent():
    return type("I", (), {"location": None, "hotel": None, "island": None, "detected_fields": []})()


def _st(**kw):
    st = ConversationState(conversation_id="origen-confirma", language=kw.pop("language", "es"), **kw)
    st._jev_lugar = JEV_NONE
    return st


def test_lo_leido_queda_por_confirmar_y_no_se_guarda():
    st, it = _st(), _intent()
    core._poner_ubicacion(it, st, "Va quiero comprar sin ir de cartagena", {"location": "island"}, {})
    assert it.location is None and st.pending_correction == {"location": "island"}


def test_se_confirma_una_sola_vez():
    st = _st()
    core._poner_ubicacion(_intent(), st, "sin ir de cartagena", {"location": "island"}, {})
    st.pending_correction = None  # contestó otra cosa: no confirmado
    core._poner_ubicacion(_intent(), st, "sin ir de cartagena", {"location": "island"}, {})
    assert st.pending_correction is None


def test_con_un_origen_guardado_no_se_confirma_nada():
    st = _st(location="cartagena")
    core._poner_ubicacion(_intent(), st, "bucear en islas del rosario", {"location": "island"}, {})
    assert st.pending_correction is None and st.location == "cartagena"


@pytest.mark.parametrize("lang, origen, dice", [
    ("es", "island", "¿ya estarás en las *Islas del Rosario*"),
    ("en", "island", "will you already be on the *Rosario Islands*"),
    ("es", "cartagena", "¿saldrías *desde Cartagena*"),
])
def test_la_pregunta_confirma_lo_leido(lang, origen, dice):
    st = _st(language=lang, pending_correction={"location": origen})
    pregunta = core.ask_slot(st, core.SLOT_CONFIRM_CORRECTION)
    assert dice in pregunta and "→" not in pregunta  # no es el «¿lo cambio? X → Y» de un cambio
    assert [q["value"] for q in st.quick_replies] in (["sí", "no"], ["yes", "no"])


def test_un_cambio_de_origen_sigue_con_el_lo_cambio():
    st = _st(location="cartagena", pending_correction={"location": "island"})
    assert "→" in core.ask_slot(st, core.SLOT_CONFIRM_CORRECTION)


def test_si_lo_guarda_por_el_camino_de_siempre():
    st = _st(pending_correction={"location": "island"})
    assert routing._accept_pending_correction(st, "sí")
    assert st.pending_correction is None and (st.location or st.detected_location) == "island"


def test_la_puerta_del_precio_pregunta_la_confirmacion():
    msg = "Va quiero comprar sin ir de cartagena, cuanto cuesta?"
    st = _st(pending_correction={"location": "island"})
    st.history = [{"role": "user", "content": msg}]
    st._jev_pide_precio = True
    puerta = core._origen_antes_del_precio(st, msg, "El paquete cuesta 500 USD por persona.")
    assert puerta == core._CONFIRMA_ORIGEN["island"]["es"]  # sin cotizar, y no «¿desde dónde saldrías?»


# CALN-3b (28-oct, decisión de Gadea #2286): el extractor calla el lugar y Jev se inclina por uno → se confirma.
def test_caln3b_jev_se_inclina_y_el_extractor_calla_se_confirma():
    from src.agents.nucleo.extractor import origen_por_confirmar

    st = ConversationState(conversation_id="caln3b", language="es")
    st._jev_lugar = {"choice": "cartagena", "confidence": 0.3}
    assert origen_por_confirmar(st, {}) == "cartagena"
    st._jev_lugar = {"choice": "none", "confidence": 0.98}
    assert origen_por_confirmar(st, {}) is None  # sin lugar en el mensaje: Jev dice none
    st._jev_lugar = {"choice": "islands", "confidence": 0.3}
    assert origen_por_confirmar(st, {"location": "cartagena"}) is None  # el extractor lo dice: se guarda, no se confirma
    st.asked_corrections = {"location": "island"}
    assert origen_por_confirmar(st, {}) is None  # una vez
    st.asked_corrections, st.location = {}, "cartagena"
    assert origen_por_confirmar(st, {}) is None  # ya sabido
