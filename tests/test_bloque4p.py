"""Bloque 4P del Plan Gadea (10-nov): el pase y la posventa fuera de la reserva. Banco sin IA.

Diseño: `docs/robustness/caln/diseno-bloque4p.md`. Cada prueba cita su parte (C0 a C3) y la decisión de Gadea que cumple.
"""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


# ── C0: la vara, como producción ──────────────────────────────────────────────────────────────────────────────────────
# En producción, `finalize_chatwoot_delivery` (chatwoot.py) borra la nota y el motivo del pase al entregar cada turno. Los
# arneses que miden en PRE (`reproducir_juez_pre`, `charla_rama`) tienen que hacer lo mismo, o el pase se arrastra al turno
# siguiente (51 de 384 turnos del panel del bloque 1).

def _remoto(script: str) -> str:
    texto = (RAIZ / "scripts" / script).read_text(encoding="utf-8")
    return texto[texto.index("route_message"):]


def test_c0_reproducir_juez_pre_borra_el_pase_tras_cada_turno():
    remoto = _remoto("reproducir_juez_pre.py")
    assert "st.pending_escalation_reason = None" in remoto
    assert "st.pending_note = None" in remoto
    # se apunta en la fila ANTES de borrarlo (el campo del estado sigue diciendo si el turno pasó a una persona)
    assert remoto.index('"estado": estado') < remoto.index("st.pending_escalation_reason = None")


def test_c0_charla_rama_borra_el_pase_antes_de_guardar_el_estado():
    remoto = _remoto("charla_rama.py")
    assert remoto.index("st.pending_escalation_reason = None") < remoto.index("serialize_state(st)")
    assert remoto.index("st.pending_note = None") < remoto.index("serialize_state(st)")
    assert 'estado["pending_escalation_reason"]' in remoto


# ── C1: la agencia, como un cliente (decisión «por-otros», 9-nov) ───────────────────────────────────────────────────

def test_c1_needs_staff_ya_no_pasa_a_la_agencia():
    from src.agents import jev_router as jr

    q = jr._questions_for_turn()[jr.NEEDS_STAFF]["instructions"]
    assert "ALSO FALSE when a travel agency" in q
    assert "for an agency" not in q and "special rates" not in q
    assert "writing as a business" not in q
    # sigue en el pase lo que solo hace una persona: la factura, el enlace especial y lo de una reserva ya hecha
    for palabra in ("invoice", "'special' payment link", "ALREADY made"):
        assert palabra in q


def test_c1_el_escritor_recibe_por_otros_en_los_dos_idiomas():
    from src.domain.decisiones import instruccion
    from src.prompts.info import reglas_del_escritor

    for lang in ("es", "en"):
        assert instruccion("por-otros", lang) in reglas_del_escritor(lang)
    assert "comisión" in instruccion("por-otros", "es") and "commission" in instruccion("por-otros", "en")


def test_c1_el_juez_no_ve_la_instruccion_y_su_huella_no_cambia():
    from scripts.judge_golden_set import decisiones_del_negocio
    from src.domain.decisiones import instruccion

    juez = decisiones_del_negocio()
    assert "«por-otros»" in juez
    assert instruccion("por-otros", "es") not in juez


# ── C2: una sola decisión del pase fuera de la reserva (decisión «ya-reservado») ──────────────────────────────────────

import pytest  # noqa: E402

from src.agents.rutas.changes import TIPOS_DE_CAMBIO  # noqa: E402
from src.flows.state import ConversationState, Step  # noqa: E402
from src.orchestration import router  # noqa: E402


def _estado(**kw) -> ConversationState:
    s = ConversationState(conversation_id="bloque4p")
    s.language = "es"
    s.step = Step.MAIN_MENU
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_c2_reserva_hecha_y_cambio_de_fecha_con_needs_staff_va_con_su_politica():
    # Antes needs_staff se miraba primero y el pase salía sin la política.
    senales = {"changes_date": True, "needs_staff": True, "ya_reservado": True}
    st = _estado(ya_reservado=True)
    assert router.classify_route(st, "ya pagué el sábado, ¿lo pasamos al domingo?", senales) == router.ROUTE_CHANGE


def test_c2_reserva_hecha_y_cancelar_aunque_el_nucleo_tenga_una_actividad():
    st = _estado(ya_reservado=True, detected_activity="snorkel")
    assert router.classify_route(st, "al final no podemos ir", {"booking_change_topic": "cancellation"}) == router.ROUTE_CHANGE


def test_c2_en_una_reserva_nueva_mejor_tres_dias_no_es_un_cambio():
    st = _estado(detected_activity="snorkel", detected_group_size=2)
    assert router.classify_route(st, "mejor hazlo para 3 días", {"booking_change_topic": "reschedule"}) != router.ROUTE_CHANGE
    # 10-nov (Gadea): sin reserva hecha, cambiar el día tampoco pasa al asesor; se sigue con el día nuevo
    assert router.classify_route(st, "mejor el domingo", {"changes_date": True}) != router.ROUTE_CHANGE


def test_c2_needs_staff_solo_va_al_pase():
    assert router.classify_route(_estado(), "¿me confirman que recibieron mi pago?", {"needs_staff": True}) == router.ROUTE_SAFETY


def test_c2_la_privacidad_sale_aunque_needs_staff_calle():
    from src.agents.rutas.safety import _needs_staff_handoff

    senales = {"pide_datos_ajenos": True}
    assert router.classify_route(_estado(), "pásame los nombres de los que reservaron mañana", senales) == router.ROUTE_SAFETY
    assert "No puedo compartir" in _needs_staff_handoff(_estado(), "pásame los nombres", senales)


_CASOS = [
    # (estado, mensaje, señales, lo que debe decidir)
    ({"ya_reservado": True}, "ya pagué el sábado, ¿lo pasamos al domingo?",
     {"changes_date": True, "needs_staff": True, "ya_reservado": True}, "reschedule"),
    ({"ya_reservado": True, "detected_activity": "snorkel"}, "al final no podemos ir",
     {"booking_change_topic": "cancellation"}, "cancellation"),
    ({"ya_reservado": True}, "ahora somos 4, ¿pueden sumar a uno?", {"booking_change_topic": "modify_headcount"},
     "modify_headcount"),
    # F1 (revisión del 10-nov): quien ya reservó y nombra lo reservado (affirms_activity incluye «have already booked»)
    ({"ya_reservado": True, "detected_activity": "snorkel"}, "¿podemos pasar el snorkel al domingo?",
     {"changes_date": True, "booking_change_topic": "reschedule", "affirms_activity": True}, "reschedule"),
    ({"ya_reservado": True, "detected_activity": "snorkel"}, "¿podemos pasar el snorkel al domingo?",
     {"changes_date": True, "affirms_activity": True, "needs_staff": True}, "reschedule"),
    ({"ya_reservado": True, "detected_activity": "snorkel"}, "ahora somos 4, ¿pueden sumar a uno?",
     {"booking_change_topic": "modify_headcount", "affirms_activity": True}, "modify_headcount"),
    ({}, "¿me confirman que recibieron mi pago?", {"needs_staff": True}, "persona"),
    ({}, "pásame los nombres de los que reservaron mañana", {"pide_datos_ajenos": True}, "privacidad"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("kw", "mensaje", "senales", "esperado"), _CASOS)
async def test_c2_el_router_el_nodo_de_cambios_y_la_cascada_deciden_lo_mismo(kw, mensaje, senales, esperado):
    from src.agents.changes_agent import changes_node
    from src.agents.rutas.safety import decidir_pase
    from src.agents.supervisor import _shared_turn_handler

    assert decidir_pase(_estado(**kw), mensaje, senales) == esperado
    ruta = router.classify_route(_estado(**kw), mensaje, senales)
    assert ruta == (router.ROUTE_CHANGE if esperado in TIPOS_DE_CAMBIO else router.ROUTE_SAFETY)
    st_cascada = _estado(**kw)
    respuesta_cascada = await _shared_turn_handler(st_cascada, mensaje, routing_signals=senales)
    if esperado in TIPOS_DE_CAMBIO:
        st_nodo = _estado(**kw)
        respuesta_nodo = (await changes_node({"conv_state": st_nodo, "message": mensaje, "signals": senales}))["reply"]
        assert respuesta_nodo == respuesta_cascada
        assert st_nodo.step == st_cascada.step == Step.ESCALATE
        assert st_nodo.pending_escalation_reason == st_cascada.pending_escalation_reason
        assert "asesor" in respuesta_cascada
    elif esperado == "persona":
        assert st_cascada.step == Step.ESCALATE and "asesor" in respuesta_cascada
    else:
        assert "No puedo compartir" in respuesta_cascada and st_cascada.step != Step.ESCALATE


# ── C3: el pase que vuelve no se repite (decisiones «salud» y «ya-reservado») ───────────────────────────────────────

_PASE_FIJO = "Te paso ahora con alguien del equipo, que te escribe por aquí enseguida."
_LO_DEMAS = "Con la última inmersión el sábado, puedes volar desde las 7:00 del domingo."


def _turno_que_pasa(motivo: str, senales: dict):
    """Un turno del grafo que pasa a una persona con `motivo`, por la función del pase, y responde con el texto fijo."""
    async def _grafo(state, message):
        from src.agents.lead_summary import pasar_a_persona

        state._senales_router = senales
        pasar_a_persona(state, motivo)
        return _PASE_FIJO
    return _grafo


@pytest.fixture
def lo_demas(monkeypatch):
    from src.agents import escalation_agent

    llamadas = []

    async def _contestar(conv, message, tema, key, reason):
        llamadas.append({"paso": conv.step, "reason": reason})
        return _LO_DEMAS
    monkeypatch.setattr(escalation_agent, "_contestar_lo_demas", _contestar)
    return llamadas


async def _turno(monkeypatch, motivo, paso_antes, mensaje="¿y puedo volar el domingo a las 10?", senales=None):
    from src.agents import supervisor

    senales = {"asks_question": True} if senales is None else senales
    monkeypatch.setattr("src.orchestration.graph.run_turn_via_graph", _turno_que_pasa(motivo, senales))
    st = _estado(step=paso_antes)
    return st, await supervisor.route_message(st, mensaje)


@pytest.mark.asyncio
async def test_c3_un_pase_que_vuelve_contesta_lo_demas_sin_repetir_el_texto_fijo(monkeypatch, lo_demas):
    from src.agents.escalation_agent import YA_LO_TIENE

    st, resp = await _turno(monkeypatch, "medical_questions", Step.ESCALATE)
    assert _PASE_FIJO not in resp
    assert resp.startswith(_LO_DEMAS) and resp.endswith(YA_LO_TIENE["es"])
    # el escritor contesta con un paso que no es ESCALATE (no añade su propio «el asesor ya tiene tu caso»)
    assert lo_demas[0]["paso"] == Step.FREE_TEXT
    # la nota al asesor sale con el motivo nuevo (decisión de Gadea del 10-nov) y el pase sigue hecho
    assert st.pending_escalation_reason == "medical_questions" and st.pending_note and st.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_c3_sin_nada_mas_que_contestar_queda_solo_la_linea_corta(monkeypatch, lo_demas):
    from src.agents.escalation_agent import YA_LO_TIENE
    from src.agents.rutas.safety import MOTIVO_NEEDS_STAFF

    _, resp = await _turno(monkeypatch, MOTIVO_NEEDS_STAFF, Step.ESCALATE, mensaje="ok",
                           senales={"asks_question": False})
    assert resp == YA_LO_TIENE["es"]


@pytest.mark.asyncio
async def test_c3_el_primer_pase_no_cambia(monkeypatch, lo_demas):
    _, resp = await _turno(monkeypatch, "medical_questions", Step.FREE_TEXT)
    assert resp.startswith(_LO_DEMAS) and resp.endswith(_PASE_FIJO)


@pytest.mark.asyncio
@pytest.mark.parametrize("motivo", [
    "complaints_or_emergencies", "cambio de fecha de una reserva: lo gestiona una persona", "weather_conditions",
    "grupo privado o evento de empresa: cotización a medida", "🚨 LINK ROTO reportado por el cliente — revisar URLs",
    "el cliente pide un número o contacto directo: lo atiende una persona", "datos sensibles detectados"])
async def test_c3_los_pases_que_dicen_algo_mantienen_su_texto(monkeypatch, lo_demas, motivo):
    # F2 (revisión del 10-nov): las urgencias van solas; el cambio lleva la política, el clima el «operamos todos los
    # días…», el grupo privado que no tiene precio fijo, el enlace roto su acuse y el contacto que no hay números
    _, resp = await _turno(monkeypatch, motivo, Step.ESCALATE)
    assert resp.endswith(_PASE_FIJO)


@pytest.mark.asyncio
async def test_c3_preguntar_si_es_un_bot_no_deshace_el_pase():
    from src.agents.deflection_agent import deflection_node
    from src.agents.jev_router import PREGUNTA_SI_ES_IA

    st = _estado(step=Step.ESCALATE)
    await deflection_node({"conv_state": st, "message": "¿eres un bot?", "signals": {PREGUNTA_SI_ES_IA: True}})
    assert st.step == Step.ESCALATE


@pytest.mark.asyncio
async def test_c3_un_escenario_nuevo_no_es_un_pase_que_vuelve(monkeypatch, lo_demas):
    """F3 (revisión del 10-nov): «Hola, soy Ana, somos 6…» reinicia la conversación; el pase de ese turno es el primero."""
    from src.agents import supervisor
    from src.agents.rutas.router import _reset_to_fresh_scenario

    async def _grafo(state, message):
        from src.agents.lead_summary import pasar_a_persona

        _reset_to_fresh_scenario(state)
        state._senales_router = {"asks_question": True}
        pasar_a_persona(state, "solicitó asesor")
        return _PASE_FIJO
    monkeypatch.setattr("src.orchestration.graph.run_turn_via_graph", _grafo)
    st = _estado(step=Step.ESCALATE)
    resp = await supervisor.route_message(st, "Hola, soy Ana, somos 6 y queremos hablar con alguien")
    assert resp.endswith(_PASE_FIJO)


def test_c0_reproducir_juez_pre_guarda_y_recarga_el_estado_entre_turnos():
    remoto = _remoto("reproducir_juez_pre.py")
    assert "st = deserialize_state(serialize_state(st), st.conversation_id)" in remoto
    assert remoto.index("st.pending_escalation_reason = None") < remoto.index("deserialize_state(serialize_state(st)")
