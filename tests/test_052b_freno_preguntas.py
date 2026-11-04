"""0.52b: la misma pregunta de la reserva no sale una 3.ª vez (grave por criterio de Álvaro, #2716)."""
from src.agents import conversational_core as core
from src.agents.compositor import componer
from src.flows.state import ConversationState

PREGUNTA = "¿Desde dónde saldrías? Puedes salir *desde Cartagena* o, si ya estás *en las islas*, coordinamos la recogida."
RESPUESTA = "El alojamiento se reserva directamente con el hotel y no está incluido en el plan de buceo."


def _estado(veces=0, slot="location", intenciones=None):
    estado = ConversationState(conversation_id="052b", language="es")
    estado.core_pending_slot = slot
    estado._preguntas_del_turno = [(slot, PREGUNTA)]
    estado._intenciones = intenciones or []
    estado.preguntas_hechas = {slot: veces} if veces else {}
    return estado


def _turno(estado, cuerpo=RESPUESTA):
    return componer(estado, f"{cuerpo}\n\n{PREGUNTA}", escribio=True)


def test_las_dos_primeras_veces_sale_y_se_cuenta():
    estado = _estado()
    assert PREGUNTA in _turno(estado)
    assert estado.preguntas_hechas["location"] == 1
    estado._preguntas_del_turno = [("location", PREGUNTA)]
    assert PREGUNTA in _turno(estado)
    assert estado.preguntas_hechas["location"] == 2


def test_la_tercera_no_sale_y_se_queda_la_respuesta():
    estado = _estado(veces=2)
    texto = _turno(estado)
    assert "Desde dónde" not in texto and "alojamiento" in texto
    assert estado.core_pending_slot == "location"  # sigue pendiente, por si contesta
    assert estado.preguntas_hechas["location"] == 2


def test_si_pide_el_enlace_si_sale_porque_hace_falta():
    assert PREGUNTA in _turno(_estado(veces=2, intenciones=["enlace"]))


def test_sin_nada_mas_que_decir_si_sale():
    assert PREGUNTA in _turno(_estado(veces=2), cuerpo="¡Perfecto! 🙌")


def _estado_sin_slot(veces=0, intenciones=None):
    estado = _estado(veces=veces, intenciones=intenciones)
    estado._preguntas_del_turno = []
    estado.core_pending_slot = None
    return estado


def test_el_origen_tras_la_lista_de_precios_cuenta_y_a_la_tercera_no_sale():
    fija = core.ORIGEN_TRAS_LAS_VARIANTES_ES
    estado = _estado_sin_slot()
    assert fija in componer(estado, f"{RESPUESTA}\n\n{fija}", escribio=True)
    assert fija in componer(estado, f"{RESPUESTA}\n\n{fija}", escribio=True)
    assert estado.preguntas_hechas["location"] == 2
    assert componer(estado, f"{RESPUESTA}\n\n{fija}", escribio=True) == RESPUESTA


def test_la_confirmacion_del_origen_es_la_misma_pregunta():
    fija = core._CONFIRMA_ORIGEN["island"]["es"]
    assert componer(_estado_sin_slot(veces=2), f"{RESPUESTA}\n\n{fija}", escribio=True) == RESPUESTA


def test_tras_los_dos_enlaces_se_queda_la_indicacion_y_no_la_pregunta():
    fija = core.ORIGEN_TRAS_LOS_ENLACES_ES
    texto = componer(_estado_sin_slot(veces=2), f"{RESPUESTA}\n\n{fija}", escribio=True)
    assert "Reserva con el de tu punto de salida." in texto and "¿Saldrías" not in texto


def test_el_origen_si_sale_si_pide_el_enlace():
    fija = core.ORIGEN_TRAS_LAS_VARIANTES_ES
    assert fija in componer(_estado_sin_slot(veces=2, intenciones=["enlace"]), f"{RESPUESTA}\n\n{fija}", escribio=True)


def test_cada_pregunta_lleva_su_cuenta():
    estado = _estado(veces=2, slot="nationality")
    estado.preguntas_hechas = {"location": 2}
    assert PREGUNTA in _turno(estado)
    assert estado.preguntas_hechas == {"location": 2, "nationality": 1}
