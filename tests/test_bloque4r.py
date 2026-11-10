"""Bloque 4R (Plan Gadea): el momento de reservar. Banco sin IA (docs/robustness/caln/diseno-bloque4r.md)."""
import pytest

from src.agents import conversational_core as core
from src.agents import redactor_hechos
from src.agents.compositor import _una_oferta_del_asesor
from src.agents.nucleo import entrega as pintor
from src.agents.nucleo.slotfill_close import _OFERTA_DEL_ASESOR
from src.agents.rag_agent import build_system_prompt
from src.agents.redactor_hechos import con_la_pieza
from src.flows.como_reserva import (
    ASESOR,
    ENLACE,
    HOTEL_PRIMERO,
    ORIGEN_PRIMERO,
    RECOGIDA_POR_CONFIRMAR,
    Entrega,
    entrega,
    recogida_por_confirmar,
)
from src.flows.que_preguntar import destapar_enlaces, tapar_enlaces
from src.flows.state import ConversationState
from src.prompts.info import RAG_PASE_OFRECIDO_EN, RAG_PASE_OFRECIDO_ES

URL = "https://book.divingplanet.org/book/salidas-de-buceo/1?language=es"


# --- C5: el código no rompe enlaces -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    f"Reserva aquí: {URL}. ¿Te ayudo con algo?",
    f"*Reserva:* {URL}",
    f"Link: {URL}?",
    f"({URL})",
    f"Uno: {URL}, y otro: {URL.replace('/1?', '/2?')}.",
])
def test_tapar_y_destapar_devuelve_el_texto_y_el_enlace_entero(texto):
    tapado, enlaces = tapar_enlaces(texto)
    assert "book.divingplanet.org" not in tapado and "language=es" not in tapado
    assert all(e.startswith("https://book.divingplanet.org/book/") and e.endswith("language=es") for e in enlaces)
    assert destapar_enlaces(tapado, enlaces) == texto


@pytest.mark.parametrize("oferta", list(_OFERTA_DEL_ASESOR.values()))
def test_la_oferta_del_asesor_no_rompe_el_enlace_de_delante(oferta):
    # Antes: «https://book.divingplanet.language=es» (diseño 4R, M7).
    salida = _una_oferta_del_asesor(f"Reserva aquí: {URL}. ¿Te ayudo con algo?\n\n{oferta}")
    assert URL in salida
    assert "¿Te ayudo con algo?" not in salida and salida.endswith(oferta)


def test_la_pieza_no_parte_un_enlace_con_pregunta():
    salida = con_la_pieza(f"Aquí tienes: {URL}\n\nTe va? Seguro que sí. ¿Te ayudo?", "PIEZA")
    assert URL in salida
    assert salida.index("PIEZA") < salida.index("¿Te ayudo?")


# --- C1: una sola decisión del momento de reservar ----------------------------------------------------------------------------------

def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="4r")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


@pytest.mark.parametrize(("campos", "esperado"), [
    ({}, Entrega(ORIGEN_PRIMERO)),  # nunca el enlace de un origen supuesto (#3738)
    ({"is_colombian": False}, Entrega(ORIGEN_PRIMERO)),
    ({"pending_correction": {"location": "cartagena"}}, Entrega(ORIGEN_PRIMERO)),  # se le está confirmando
    ({"location": "cartagena"}, Entrega(ENLACE, nacionalidad_por_saber=True)),  # con la línea del colombiano (#3741)
    ({"location": "cartagena", "is_colombian": False}, Entrega(ENLACE)),
    ({"location": "cartagena", "is_colombian": True, "mixed_nationality_notice": True}, Entrega(ENLACE)),  # grupo mixto: USD
    ({"location": "cartagena", "is_colombian": True}, Entrega(ASESOR)),
    ({"is_colombian": True}, Entrega(ORIGEN_PRIMERO)),  # P5 (#3747): primero el origen, también para el colombiano
    ({"detected_activity": "certified_diving", "detected_group_size": 6}, Entrega(ORIGEN_PRIMERO)),  # y para el grupo
    ({"location": "cartagena", "detected_activity": "certified_diving", "detected_group_size": 6, "is_colombian": False},
     Entrega("grupo")),
    ({"location": "island"}, Entrega(HOTEL_PRIMERO)),
    ({"pending_correction": {"location": "island"}}, Entrega(HOTEL_PRIMERO)),
    ({"location": "island", "hotel": "Casa Azul", "is_colombian": False}, Entrega(RECOGIDA_POR_CONFIRMAR)),
    ({"location": "island", "hotel": "Hotel Cocoliso", "is_colombian": False}, Entrega(ENLACE)),
])
def test_entrega(campos, esperado):
    assert entrega(_estado(**campos)) == esperado


@pytest.mark.parametrize(("campos", "lugar", "esperado"), [
    ({"location": "island", "hotel": "Casa Azul"}, None, True),
    ({"location": "island", "hotel": "Hotel Cocoliso"}, None, False),
    ({"location": "island", "hotel": "Hotel Cocoliso"}, "un Airbnb en Isla Grande", True),  # quien ya reservó y pide otro sitio (4P)
    ({"location": "island"}, None, False),  # sin hotel: es HOTEL_PRIMERO, no hay recogida que confirmar
    ({"location": "cartagena", "hotel": "Casa Azul"}, None, False),  # desde Cartagena se va al muelle
])
def test_recogida_por_confirmar(campos, lugar, esperado):
    assert recogida_por_confirmar(_estado(**campos), lugar) is esperado


# --- C3: el pintor de la entrega --------------------------------------------------------------------------------------------------


URL_ISLAS = "https://book.divingplanet.org/book/salidas-de-buceo-islas/1?language=es"


def _con_hechos(monkeypatch, enlaces: dict | None):
    async def _hechos(state, message, history):
        return ([{"actividad": "certified_diving", "enlace": enlaces}], ["enlace"]) if enlaces is not None else None
    monkeypatch.setattr(redactor_hechos, "hechos_del_turno", _hechos)


async def _pintar(st, respuesta="Respuesta del escritor."):
    return await pintor.pintar_la_entrega(st, "¿me pasas el link?", respuesta, [])


async def test_sin_intencion_de_reservar_no_se_pinta_nada(monkeypatch):
    _con_hechos(monkeypatch, {"cartagena": URL})
    st = _estado(location="cartagena", is_colombian=False, _intenciones=["precio"])
    assert await _pintar(st) == "Respuesta del escritor."


async def test_el_enlace_lo_pinta_el_codigo_una_vez(monkeypatch):
    _con_hechos(monkeypatch, {"cartagena": URL})
    st = _estado(location="cartagena", is_colombian=False, _intenciones=["enlace"])
    salida = await _pintar(st)
    assert salida.count(URL) == 1 and salida.startswith("Respuesta del escritor.")
    assert await _pintar(st, salida) == salida  # si ya está, no se repite


async def test_sin_saber_la_nacionalidad_va_la_linea_del_colombiano(monkeypatch):
    _con_hechos(monkeypatch, {"cartagena": URL})
    salida = await _pintar(_estado(location="cartagena", _intenciones=["pago"]))
    assert URL in salida and "cédula de extranjería" in salida


async def test_dos_enlaces_van_con_el_nombre_de_cada_plan(monkeypatch):
    _con_hechos(monkeypatch, {"cartagena": URL, "otro": URL.replace("/1?", "/2?")})
    salida = await _pintar(_estado(location="cartagena", is_colombian=False, _intenciones=["enlace"]))
    assert salida.count("👉 *") == 2


async def test_sin_enlace_en_los_hechos_se_cuenta(monkeypatch):
    _con_hechos(monkeypatch, None)
    vistos = []
    monkeypatch.setattr("src.observability.note_turn", lambda **kw: vistos.append(kw))
    st = _estado(location="cartagena", is_colombian=False, _intenciones=["enlace"])
    assert await _pintar(st) == "Respuesta del escritor." and {"enlace_que_faltaba": True} in vistos


async def test_sin_origen_se_pide_una_vez_con_el_motivo_y_despues_el_asesor(monkeypatch):
    _con_hechos(monkeypatch, {})
    st = _estado(is_colombian=False, _intenciones=["enlace"])
    primera = await _pintar(st)
    assert "Para darte el enlace necesito saber desde dónde sales" in primera and "book.divingplanet" not in primera
    assert st.pending_escalation_reason is None
    segunda = await _pintar(st)
    assert "Te paso con un asesor" in segunda and st.pending_escalation_reason


async def test_sin_origen_y_sin_pedir_reservar_no_se_pregunta_aqui(monkeypatch):
    _con_hechos(monkeypatch, {})
    st = _estado(is_colombian=False, _intenciones=["disponibilidad"])
    assert await _pintar(st) == "Respuesta del escritor."


def _grupo_de_seis(**campos):
    return _estado(location="cartagena", is_colombian=False, detected_activity="certified_diving", detected_group_size=6, **campos)


async def test_el_grupo_que_quiere_reservar_pasa_con_el_asesor(monkeypatch):
    _con_hechos(monkeypatch, {"asesor": True})
    st = _grupo_de_seis(_intenciones=["enlace"])
    salida = await _pintar(st)
    assert "descuento de grupo" in salida and "Les paso con un asesor" in salida and st.pending_escalation_reason
    assert "book.divingplanet" not in salida


async def test_el_grupo_que_aun_no_reserva_lo_oye_una_vez_sin_pregunta(monkeypatch):
    _con_hechos(monkeypatch, {"asesor": True})
    st = _grupo_de_seis(_intenciones=["disponibilidad"])
    primera = await _pintar(st)
    assert "descuento de grupo" in primera and "díganmelo y les paso con un asesor" in primera and "?" not in primera
    assert st.pending_escalation_reason is None
    assert await _pintar(st) == "Respuesta del escritor."  # la segunda vez, nada


async def test_quien_ya_reservo_no_recibe_nada(monkeypatch):
    _con_hechos(monkeypatch, {"cartagena": URL})
    st = _estado(location="cartagena", is_colombian=False, ya_reservado=True, _intenciones=["enlace"])
    assert await _pintar(st) == "Respuesta del escritor."


# --- C4: con un plan en curso, el escritor no recibe la orden de ofrecer el pase ----------------------------------------------------



@pytest.mark.parametrize(("lang", "orden"), [("es", RAG_PASE_OFRECIDO_ES), ("en", RAG_PASE_OFRECIDO_EN)])
def test_con_un_plan_en_curso_el_escritor_no_recibe_la_orden_de_ofrecer_el_pase(lang, orden):
    assert orden in build_system_prompt(lang)  # fuera de la reserva se queda (#3740)
    assert orden not in build_system_prompt(lang, sin_ofrecer_el_pase=True)
    # Las dos razones de la reserva (reservar o pagar, la disponibilidad) ya no están en ningún turno: las decide el código.
    for prompt in (build_system_prompt(lang), build_system_prompt(lang, sin_ofrecer_el_pase=True)):
        assert "Intención concreta de reservar" not in prompt and "Concrete booking/payment intent" not in prompt
        assert "Disponibilidad real de una fecha" not in prompt and "Real availability for a specific date" not in prompt


@pytest.mark.parametrize(("campos", "esperado"), [
    ({"detected_activity": "snorkel"}, True),
    ({"detected_activity": "snorkel", "ya_reservado": True}, False),  # posventa: es del 4P
    ({}, False),
])
def test_plan_en_curso(campos, esperado):
    assert core._plan_en_curso(_estado(**campos)) is esperado


@pytest.mark.parametrize(("texto", "esperado"), [
    ("Would you like me to connect you with a team advisor?", True),
    ("¿Quieres que te pase con un asesor del equipo?", True),
    ("El paquete incluye el almuerzo.", False),
])
def test_cuenta_si_el_escritor_ofrece_el_pase(monkeypatch, texto, esperado):
    vistos = []
    monkeypatch.setattr("src.observability.note_turn", lambda **kw: vistos.append(kw))
    core.contar_si_el_escritor_pregunta({"sin_ofrecer_el_pase": True}, texto)
    assert ({"escritor_ofrece_el_pase": True} in vistos) is esperado
