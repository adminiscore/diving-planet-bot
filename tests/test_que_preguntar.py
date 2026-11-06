"""CALN-43 P11 (decisión de Gadea, 6-nov): la tabla de qué preguntar. Nunca una 3.ª vez, tampoco si pide el enlace; en su lugar, lo que hay.

Los tres casos del panel 059c (PRE 0.59) con la misma pregunta por 3.ª vez salieron en el turno de «¿cómo reservo?», por la excepción del
enlace: a02 (el origen), a03 (la actividad) y a06 (cuántos son). Aquí se reproducen con sus textos, sin IA.
"""
import pytest

from src.agents import conversational_core as core
from src.agents.compositor import componer
from src.agents.nucleo.slotfill_close import _siguiente_pregunta
from src.flows import que_preguntar as qp
from src.flows.state import ConversationState

# ─── La tabla ───

@pytest.mark.parametrize("slot", ["location", "qty", "activity", "nationality", "safety", None])
@pytest.mark.parametrize("hay_respuesta", [True, False])
def test_las_dos_primeras_veces_se_pregunta(slot, hay_respuesta):
    assert qp.que_hacer(slot, 0, hay_respuesta=hay_respuesta) == qp.PREGUNTAR
    assert qp.que_hacer(slot, 1, hay_respuesta=hay_respuesta) == qp.PREGUNTAR


@pytest.mark.parametrize("veces", [2, 3, 7])
@pytest.mark.parametrize("slot", ["qty", "activity", "nationality", "safety", "companion_activity_choice", None])
@pytest.mark.parametrize("hay_respuesta", [True, False])
def test_a_la_tercera_nunca_sale(veces, slot, hay_respuesta):
    assert qp.que_hacer(slot, veces, hay_respuesta=hay_respuesta) == qp.SIN_ELLA


def test_el_origen_sin_nada_que_decir_da_las_dos_salidas():
    assert qp.que_hacer("location", 2, hay_respuesta=False) == qp.LAS_DOS_SALIDAS
    assert qp.que_hacer("location", 2, hay_respuesta=True) == qp.SIN_ELLA


def test_agotadas_son_las_que_ya_salieron_dos_veces():
    assert qp.agotadas({"qty": 2, "location": 1, "nationality": 3, None: 5}) == {"qty", "nationality"}
    assert qp.agotadas(None) == set() and qp.agotadas({}) == set()


def test_el_recordatorio_no_pregunta():
    assert all("?" not in texto for texto in qp.RECORDATORIO.values())
    assert qp.recordatorio("es") == qp.RECORDATORIO["es"] and qp.recordatorio("en") == qp.recordatorio(None) == qp.RECORDATORIO["en"]


# ─── Los tres del panel 059c, en el compositor ───

def _estado(slot, pregunta, *, veces, intenciones, lang="es"):
    estado = ConversationState(conversation_id="caln43-p11", language=lang)
    estado.core_pending_slot = slot
    estado._preguntas_del_turno = [(slot, pregunta)] if slot else []
    estado._intenciones = intenciones
    estado.preguntas_hechas = {slot or "location": veces}
    return estado


ACTIVIDAD = "¿Te animas con el *minicurso*, el *snorkel* o el *curso Open Water*? 🌊"
PAGO_MEXICANOS = ("Como son mexicanos y salen desde Cartagena, la reserva se hace en la página web y se paga el 100% al reservar, con "
                  "tarjeta extranjera; se usa el pasaporte como documento de identificación.")
CUANTOS = "How many people would this be for: just you, or more? 😊"
MINICURSO = ("The Dive Mini Course is from 10 years old. You can book it here: https://book.divingplanet.org/book/minicurso-de-buceo/2"
             "?language=en. The online discount is applied automatically.")
LLEVA_EL_ENLACE = ("Lunch is included. You can book the 2-dive trip online: https://book.divingplanet.org/book/salidas-de-buceo/1"
                   "?language=en")


def test_a03_la_actividad_por_tercera_vez_no_sale_aunque_pida_reservar():
    estado = _estado("activity", ACTIVIDAD, veces=2, intenciones=["enlace", "pago"])
    texto = componer(estado, f"{PAGO_MEXICANOS}\n\n{ACTIVIDAD}", escribio=True)
    assert texto == PAGO_MEXICANOS
    assert estado.preguntas_hechas["activity"] == 2 and estado.core_pending_slot == "activity"  # sigue pendiente, por si contesta


def test_a06_cuantos_son_por_tercera_vez_no_sale_aunque_pida_reservar():
    estado = _estado("qty", CUANTOS, veces=2, intenciones=["enlace", "precio", "edad"], lang="en")
    assert componer(estado, f"{MINICURSO}\n\n{CUANTOS}", escribio=True) == MINICURSO


def test_a02_la_confirmacion_del_origen_por_tercera_vez_no_sale_aunque_pida_reservar():
    fija = core._CONFIRMA_ORIGEN["cartagena"]["en"]
    estado = _estado(None, "", veces=2, intenciones=["incluye", "enlace"], lang="en")
    assert componer(estado, f"{LLEVA_EL_ENLACE}\n\n{fija}", escribio=True) == LLEVA_EL_ENLACE


def test_la_segunda_vez_si_sale_aunque_pida_reservar_y_se_cuenta():
    estado = _estado("activity", ACTIVIDAD, veces=1, intenciones=["enlace"])
    assert componer(estado, f"{PAGO_MEXICANOS}\n\n{ACTIVIDAD}", escribio=True).endswith(ACTIVIDAD)
    assert estado.preguntas_hechas["activity"] == 2


def test_sin_nada_mas_que_decir_va_el_recordatorio_y_no_la_pregunta():
    estado = _estado("qty", CUANTOS, veces=2, intenciones=[], lang="en")
    assert componer(estado, CUANTOS, escribio=False) == qp.RECORDATORIO["en"]
    estado = _estado("qty", CUANTOS, veces=2, intenciones=[], lang="en")
    assert componer(estado, f"Perfect! 🙌\n\n{CUANTOS}", escribio=False) == f"Perfect! 🙌\n\n{qp.RECORDATORIO['en']}"


# ─── El flujo: si falta otro dato, pregunta ese ───

def _sin_el_numero(**campos):
    estado = ConversationState(conversation_id="caln43-p11", language="es", detected_activity="minicourse", location="cartagena",
                               is_certified=False, **campos)
    estado.core_pending_slot = core.SLOT_QTY
    return estado


def test_la_agotada_cede_el_turno_a_otro_dato_que_falta():
    estado = _sin_el_numero()
    estado.preguntas_hechas = {core.SLOT_QTY: 2}
    assert core.next_missing_slot(estado) == core.SLOT_QTY
    assert _siguiente_pregunta(estado, core.SLOT_QTY) == core.SLOT_NATIONALITY


def test_si_no_falta_otro_la_devuelve_el_flujo_y_la_frena_el_compositor():
    estado = _sin_el_numero(is_colombian=False)
    estado.preguntas_hechas = {core.SLOT_QTY: 2}
    assert _siguiente_pregunta(estado, core.SLOT_QTY) == core.SLOT_QTY


def test_antes_de_dos_veces_el_flujo_no_cambia():
    estado = _sin_el_numero()
    estado.preguntas_hechas = {core.SLOT_QTY: 1}
    assert _siguiente_pregunta(estado, None) == core.SLOT_QTY
