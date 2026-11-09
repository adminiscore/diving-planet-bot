"""LAT-9 paso 2 (26-oct) daba al escritor la pregunta de la reserva al empezar el turno, y el código la corregía cuando el mensaje la
cambiaba (128 de 170 turnos de los paneles 058, 058-cl y 059c), con un «¡Perfecto!» delante. CALN-43 (decisión de Gadea, 6-nov) lo
sustituye: en un turno de la reserva el escritor no pregunta, y la pregunta la decide la tabla y la pone el código, una vez y al final."""
from src.agents import conversational_core as core
from src.agents.conversational_core import SLOT_LOCATION, _sin_la_pregunta_final
from src.flows.state import ConversationState, Step
from src.prompts import info


def _estado(**kw) -> ConversationState:
    st = ConversationState(conversation_id="lat9p2", language="es")
    st.detected_activity = "certified_diving"
    st.is_certified = True
    for k, v in kw.items():
        setattr(st, k, v)
    return st


def test_sin_la_pregunta_final_solo_quita_el_ultimo_parrafo_si_pregunta():
    assert _sin_la_pregunta_final("Cuesta 124 USD.\n\n¿Desde dónde saldrías?") == "Cuesta 124 USD."
    assert _sin_la_pregunta_final("Cuesta 124 USD.\n\nIncluye el equipo.") == "Cuesta 124 USD.\n\nIncluye el equipo."
    assert _sin_la_pregunta_final("¿Desde dónde saldrías?") == "¿Desde dónde saldrías?"  # sin otro texto, se queda


def test_en_un_turno_de_la_reserva_el_escritor_no_pregunta():
    st = _estado(core_pending_slot=SLOT_LOCATION, step=Step.FREE_TEXT)
    core.marcar_turno_de_la_reserva(st)
    assert st._turno_de_la_reserva is True
    assert core._entradas_rag(st, [], "¿incluye el almuerzo?")["sin_preguntas"] is True


def test_fuera_de_la_reserva_el_escritor_contesta_como_siempre():
    for st in (_estado(step=Step.FREE_TEXT), _estado(core_pending_slot=SLOT_LOCATION, step=Step.ESCALATE)):
        core.marcar_turno_de_la_reserva(st)
        assert st._turno_de_la_reserva is False and "sin_preguntas" not in core._entradas_rag(st, [], "hola")


def test_la_orden_no_lleva_ninguna_pregunta_y_no_cambia_con_el_turno():
    for lang in ("es", "en"):
        texto = info.sin_preguntas(lang)
        assert "?" not in texto and "{" not in texto
    assert "sin hacer ninguna pregunta" in info.sin_preguntas("es")
    assert "without asking any question" in info.sin_preguntas("en")
