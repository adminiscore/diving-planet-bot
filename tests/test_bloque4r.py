"""Bloque 4R (Plan Gadea): el momento de reservar. Banco sin IA (docs/robustness/caln/diseno-bloque4r.md)."""
import json

import pytest

from src.agents import conversational_core as core
from src.agents import rag_agent, redactor_hechos
from src.agents.compositor import _una_oferta_del_asesor
from src.agents.nucleo import entrega as pintor
from src.agents.nucleo.slotfill_close import _OFERTA_DEL_ASESOR
from src.agents.rag_agent import build_system_prompt
from src.agents.redactor_hechos import con_la_pieza
from src.flows import hechos as hechos_mod
from src.flows.como_reserva import (
    ASESOR,
    ENLACE,
    HOTEL_PRIMERO,
    ORIGEN_PRIMERO,
    RECOGIDA_POR_CONFIRMAR,
    Entrega,
    entrega,
    recogida_por_confirmar,
    sin_enlaces_de_reserva,
)
from src.flows.que_preguntar import destapar_enlaces, tapar_enlaces
from src.flows.state import ConversationState, Step
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
    assert "descuento de grupo" in primera and "Cuando quieran reservar, díganmelo." in primera and "?" not in primera
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


# --- Tras la revisión del código (paso 5): los defectos que encontró, cada uno con su prueba --------------------------------------




@pytest.mark.parametrize("clave", ["es_uno", "es_grupo", "en"])
def test_las_lineas_del_pintor_no_cuentan_como_oferta_del_pase(clave):
    # D1: «ok» tras ellas no debe pasar al asesor (`acepta_la_oferta_del_asesor` busca «asesor» y un verbo de oferta).
    for texto in (pintor._SI_ERES_COLOMBIANO[clave], pintor._CUANDO_QUIERAS[clave],
                  *(pintor._POR_QUE[f][clave] for f in pintor._POR_QUE)):
        assert not core.ofrece_el_pase(texto), texto


def test_el_grupo_mixto_no_oye_que_pagara_en_pesos():
    # D8 (pago-y-reserva): un grupo mixto paga en USD con el enlace; solo si todos son colombianos, en pesos.
    assert "todos" in pintor._SI_ERES_COLOMBIANO["es_grupo"]


@pytest.mark.parametrize("campos", [
    {"step": Step.ESCALATE},  # D2: ya pasado
    {"pending_escalation_reason": "núcleo conversacional - otro"},
    {"_tarjeta_del_turno": True},  # D3: la tarjeta del turno pinta lo suyo
])
async def test_no_pinta_en_un_pase_ni_con_la_tarjeta(monkeypatch, campos):
    _con_hechos(monkeypatch, {"cartagena": URL})
    st = _estado(location="cartagena", is_colombian=True, _intenciones=["pago"], **campos)
    antes = st.pending_escalation_reason
    assert await _pintar(st) == "Respuesta del escritor." and st.pending_escalation_reason == antes


async def test_no_pinta_sobre_la_respuesta_segura(monkeypatch):
    _con_hechos(monkeypatch, {"cartagena": URL})  # D5
    st = _estado(location="cartagena", is_colombian=False, _intenciones=["enlace"])
    assert await _pintar(st, rag_agent.FALLBACK_ES) == rag_agent.FALLBACK_ES


async def test_un_plan_sin_enlace_va_con_el_asesor(monkeypatch):
    _con_hechos(monkeypatch, {"asesor": True})  # D7 (s03g): el Divemaster, las 4 diurnas…
    st = _estado(location="cartagena", is_colombian=False, _intenciones=["enlace"])
    salida = await _pintar(st)
    assert "no se reserva por la web" in salida and "Te paso con un asesor" in salida and st.pending_escalation_reason
    st2 = _estado(location="cartagena", is_colombian=False, _intenciones=["disponibilidad"])
    salida2 = await _pintar(st2)
    assert "no se reserva por la web" in salida2 and st2.pending_escalation_reason is None


async def test_si_la_respuesta_ya_pregunta_el_origen_no_va_otra(monkeypatch):
    _con_hechos(monkeypatch, {})  # D6
    st = _estado(is_colombian=False, _intenciones=["enlace"])
    con_pregunta = "Precios. ¿Saldrías *desde Cartagena* o ya estás *en las Islas del Rosario*? 🌊"
    assert await _pintar(st, con_pregunta) == con_pregunta
    assert "Te paso con un asesor" in await _pintar(st)  # la siguiente vez, el asesor


async def test_en_ingles_y_en_grupo(monkeypatch):
    _con_hechos(monkeypatch, {})
    st = _estado(is_colombian=False, language="en", _intenciones=["enlace"])
    assert "where you're leaving from" in await _pintar(st)
    st = _estado(is_colombian=False, detected_group_size=3, _intenciones=["enlace"])
    assert "Para darles el enlace" in await _pintar(st)


def test_los_hechos_sin_enlaces_siguen_siendo_json():
    # D4: el patrón se comía la comilla de cierre y el escritor recibía un JSON roto.
    texto = json.dumps({"enlace": {"cartagena": URL, "island": URL_ISLAS}}, ensure_ascii=False, indent=1)
    assert json.loads(sin_enlaces_de_reserva(texto)) == {"enlace": {"cartagena": "", "island": ""}}


async def test_los_hechos_de_verdad_llegan_al_pintor(monkeypatch):
    # Sin simular los hechos: lo que da `hechos.hechos` con el origen sabido es lo que pinta el pintor.
    st = _estado(location="cartagena", is_colombian=False, detected_activity="certified_diving", _intenciones=["enlace"])
    bloques = hechos_mod.hechos(st, ["enlace"], ["certified_diving"])
    assert any(isinstance(u, str) and u.startswith("https://book.divingplanet.org") for b in bloques for u in b["enlace"].values())

    async def _hechos(state, message, history):
        return bloques, ["enlace"]
    monkeypatch.setattr(redactor_hechos, "hechos_del_turno", _hechos)
    salida = await _pintar(st)
    assert salida.count("https://book.divingplanet.org") == 1


def test_la_pieza_no_parte_un_enlace_en_el_parrafo_de_la_pregunta():
    # Revisión del paso 5: el caso que rompía (el enlace y la pregunta final en el mismo párrafo).
    salida = con_la_pieza(f"Aquí tienes los planes.\n\nReserva en {URL} ¿Te ayudo con algo más?", "PIEZA")
    assert URL in salida and salida.endswith("¿Te ayudo con algo más?")
