"""CALN-2 paso 1 (27-oct): el grupo se guarda como lista de personas y el reparto de siempre se calcula de ella."""
import json

import pytest

from src.flows import grupo
from src.flows.state import ConversationState
from src.state_store import deserialize_state, serialize_state


@pytest.mark.parametrize("reparto", [
    None,
    {"certified_diving": 2},
    {"certified_diving": 2, "snorkel": 1, "undecided": 1},
    {"undecided": 3},
    {"minicourse": 0, "snorkel": 2},
])
def test_ida_y_vuelta_exacta(reparto):
    st = ConversationState(conversation_id="caln2")
    st.detected_group_allocation = reparto
    assert st.detected_group_allocation == reparto
    if reparto:
        assert list(st.detected_group_allocation) == list(reparto)  # el mismo orden


def test_quien_no_ha_elegido_es_una_entrada_sin_actividad():
    st = ConversationState(conversation_id="caln2")
    st.detected_group_allocation = {"certified_diving": 1, "undecided": 1}
    assert st.personas == [{"actividad": "certified_diving", "cantidad": 1}, {"actividad": None, "cantidad": 1}]


def test_se_guarda_y_se_carga_como_lista():
    st = ConversationState(conversation_id="caln2")
    st.detected_group_allocation = {"snorkel": 2}
    datos = json.loads(serialize_state(st))
    assert datos["personas"] == [{"actividad": "snorkel", "cantidad": 2}]
    assert deserialize_state(serialize_state(st), "caln2").detected_group_allocation == {"snorkel": 2}


def test_una_conversacion_guardada_antes_trae_el_reparto_de_siempre():
    st = ConversationState(conversation_id="caln2")
    datos = json.loads(serialize_state(st))
    datos.pop("personas")
    datos["detected_group_allocation"] = {"certified_diving": 2, "undecided": 1}
    cargado = deserialize_state(json.dumps(datos), "caln2")
    assert cargado.detected_group_allocation == {"certified_diving": 2, "undecided": 1}


def test_sin_nadie_el_reparto_es_none():
    assert grupo.reparto_de([]) is None


def _grupo(**campos) -> ConversationState:
    st = ConversationState(conversation_id="caln2")
    for campo, valor in campos.items():
        setattr(st, campo, valor)
    return st


def test_quien_no_esta_certificado_no_hereda_el_buceo():
    """«Quiero bucear, soy certificado. Voy con mi novia, que nunca ha buceado» (banco de grupos g02 y g18)."""
    st = _grupo(detected_activity="certified_diving", detected_group_size=2, acompanante_sin_certificar=True)
    assert grupo.sin_certificar_no_hereda(st)
    # como los deja `_take_undecided_members`: fuera del reparto, pendientes y con la recomendación marcada
    assert st.detected_group_allocation == {"certified_diving": 1}
    assert st.pending_undecided_qty == 1 and st.needs_companion_activity


@pytest.mark.parametrize("campos", [
    {"detected_activity": "snorkel", "detected_group_size": 2, "acompanante_sin_certificar": True},  # no pide certificado
    {"detected_activity": "certified_diving", "detected_group_size": 2},  # nadie dijo que no esté certificado
    {"detected_activity": "certified_diving", "acompanante_sin_certificar": True},  # sin total, se pregunta
    {"detected_activity": "certified_diving", "detected_group_size": 2, "acompanante_sin_certificar": True,
     "detected_group_allocation": {"certified_diving": 1, "snorkel": 1}},  # el reparto dicho manda
    {"detected_activity": "certified_diving", "detected_group_size": 2, "acompanante_sin_certificar": True,
     "pending_undecided_qty": 1},  # ya están pendientes de elegir
])
def test_si_no_toca_no_cambia_el_grupo(campos):
    st = _grupo(**campos)
    antes = st.detected_group_allocation
    assert not grupo.sin_certificar_no_hereda(st)
    assert st.detected_group_allocation == antes


@pytest.mark.parametrize("reparto,nuevo,total", [
    ({"certified_diving": 1}, {"certified_diving": 1, "snorkel": 1}, 2),  # «ella prefiere hacer snorkel» (g24)
    ({"certified_diving": 1, "undecided": 1}, {"certified_diving": 1, "minicourse": 1}, 2),
    ({"snorkel": 2}, {"snorkel": 2, "minicourse": 1}, 4),  # uno de los dos que faltaban
])
def test_dar_actividad_a_quien_no_la_tenia_completa_el_grupo(reparto, nuevo, total):
    assert grupo.completa(reparto, nuevo, total)


@pytest.mark.parametrize("reparto,nuevo,total", [
    ({"certified_diving": 2}, {"certified_diving": 1, "snorkel": 1}, 2),  # le quita el buceo a uno: corrección
    ({"certified_diving": 1}, {"certified_diving": 1, "snorkel": 2}, 2),  # más de los que faltaban
    ({"certified_diving": 1}, {"certified_diving": 1}, 2),  # no añade nada
    ({"certified_diving": 1}, {"certified_diving": 1, "snorkel": 1}, None),  # sin total no se sabe quién falta
])
def test_lo_demas_no_completa(reparto, nuevo, total):
    assert not grupo.completa(reparto, nuevo, total)


def test_quien_se_suma_sin_elegir_queda_pendiente_y_al_elegir_no_se_cuenta_dos_veces():
    """«Mi amigo también quiere venir» sobre un grupo sabido: no entra en el reparto como «undecided» (el grupo
    contaría como completo y nadie le preguntaría)."""
    from src.agents import conversational_core as core

    st = _grupo(detected_activity="certified_diving", detected_group_size=1)
    core._merge_companion_activity(st, "undecided", 1)
    assert st.detected_group_allocation == {"certified_diving": 1}
    assert st.pending_undecided_qty == 1 and st.needs_companion_activity and st.detected_group_size == 2
    st.pending_companion_activity = "snorkel"
    assert core._merge_pending_undecided(st)
    assert st.detected_group_allocation == {"certified_diving": 1, "snorkel": 1} and st.detected_group_size == 2


def test_otro_que_se_suma_no_quita_del_total_a_quien_no_ha_elegido():
    from src.agents import conversational_core as core

    st = _grupo(detected_activity="certified_diving", detected_group_size=2, pending_undecided_qty=1,
                detected_group_allocation={"certified_diving": 1})
    core._merge_companion_activity(st, "snorkel", 1)
    assert st.detected_group_size == 3 and st.pending_undecided_qty == 1


def test_quien_no_habia_elegido_y_elige_no_se_cuenta_otra_vez(monkeypatch):
    """«El niño el Open Water» con el niño pendiente de elegir en una familia de 4 (banco g21)."""
    from src.agents.nucleo import extraction

    st = _grupo(detected_activity="certified_diving", detected_group_size=4, pending_undecided_qty=1,
                needs_companion_activity=True, detected_group_allocation={"certified_diving": 2, "companion": 1})
    monkeypatch.setattr(st, "_jev_adds_person", 0.1, raising=False)
    extraction._add_or_ask_companion(st, "y el niño el Open Water", "padi_open_water", 1)
    assert st.detected_group_allocation == {"certified_diving": 2, "companion": 1, "padi_open_water": 1}
    assert st.detected_group_size == 4 and not st.pending_undecided_qty and not st.needs_companion_activity


def test_restaurar_a_quien_escribe_no_borra_lo_que_acaba_de_decir():
    """«Quiero bucear, soy buzo certificado. Vienen también unos amigos…»: antes del turno no se sabía (banco g26)."""
    from src.agents.nucleo import extraction

    st = _grupo(detected_activity="certified_diving", is_certified=True)
    extraction._restore_main_diver_fields(st, None, None, None, None, None)
    assert st.is_certified is True
    extraction._restore_main_diver_fields(st, None, None, False, None, None)
    assert st.is_certified is False  # lo que había antes del turno, se protege como siempre


def test_el_reparto_que_completa_a_los_pendientes_no_lo_tira_el_veto_de_jev(monkeypatch):
    """Sparring contra la rama (27-oct): familia de 5, el suegro acompañante y 4 por elegir; «mi marido quiere bucear,
    yo me animo al minicurso, la de 14 también» se tiraba porque Jev dice (bien) que nadie se suma."""
    from src.agents.nucleo import extraction, extractor

    st = _grupo(detected_group_size=5, detected_group_allocation={"companion": 1}, pending_undecided_qty=4,
                needs_companion_activity=True)
    monkeypatch.setattr(extractor, "_jev_dice_que_nadie_se_suma", lambda _st: True)
    mensaje = "Mi marido quiere bucear, yo me animo al minicurso, la de 14 también minicurso"
    intent = extraction.lectura_del_turno(mensaje)
    extractor._poner_grupo(intent, st, mensaje,
                           {"group_allocation": {"certified_diving": 1, "minicourse": 2, "companion": 1}})
    assert intent.group_allocation == {"certified_diving": 1, "minicourse": 2, "companion": 1, "undecided": 1}
    assert intent.group_size in (None, 5)


def test_quien_no_se_nombra_no_se_quita_al_completar():
    """La misma familia, otra lectura del extractor: no nombra al suegro (ya iba de acompañante)."""
    assert grupo.completado({"companion": 1}, {"minicourse": 2, "undecided": 1}, 5) == {"companion": 1, "minicourse": 2}
    assert grupo.completado({"companion": 1}, {"minicourse": 5}, 5) is None  # no caben en los que faltaban
    assert not grupo.completa({"companion": 1}, {"minicourse": 2}, 5)  # lo que se GUARDA nunca quita a nadie


@pytest.mark.parametrize("edades,esperadas", [
    ([], ["minicourse", "snorkel", "companion"]),
    ([9, 14], ["minicourse", "snorkel", "bubble_makers", "companion"]),  # sparring CALN1-04: la de 9, Bubble Makers
    ([40], ["minicourse", "snorkel", "companion"]),
])
def test_la_recomendacion_mira_las_edades_del_grupo(edades, esperadas):
    from src.agents import conversational_core as core

    # Quien falta por elegir no está certificado («nunca ha buceado»): sin buceo certificado (ver test_caln2_buzo_sin_elegir).
    st = _grupo(detected_ages=edades, detected_duration="single_day", acompanante_sin_certificar=True)
    assert core._companion_activity_options(st) == esperadas


def test_el_escritor_recibe_los_hechos_de_todo_el_grupo():
    """Sparring CALN1-04: «¿cuánto todo junto?» llevaba solo los hechos de Bubble Makers («no tengo aquí los precios de
    las otras actividades»). El reparto de este mensaje viene de la lectura del extractor (el del estado va después)."""
    from src.agents import redactor_hechos

    st = _grupo(detected_group_allocation={"companion": 1})
    datos = {"actividad_preguntada": "bubble_makers",
             "group_allocation": {"certified_diving": 1, "minicourse": 2, "bubble_makers": 1, "companion": 1}}
    assert redactor_hechos._actividades(st, datos) == ["bubble_makers", "companion", "certified_diving", "minicourse"]
    assert redactor_hechos._actividades(_grupo(), {"actividad_preguntada": "snorkel"}) == ["snorkel"]  # sin grupo, igual


def test_quien_hace_que_va_antes_que_el_origen():
    """Paso 3a: el orden aprobado (quién hace qué, el origen, seguridad y edades, la nacionalidad); si no contesta dos
    veces, se aplaza hasta antes del resumen como las demás."""
    from src.agents import conversational_core as core

    st = _grupo(detected_activity="certified_diving", is_certified=True, needs_companion_activity=True)
    assert core.next_missing_slot(st) == core.SLOT_COMPANION_ACTIVITY
    assert core.next_missing_slot(st, saltar={core.SLOT_COMPANION_ACTIVITY}) == core.SLOT_LOCATION


def test_sin_contestar_el_origen_no_hay_acuse():
    """«Voy con una amiga que no está certificada» a la pregunta del origen: la de ella sale delante, pero el origen
    sigue sin contestar y no toca «¡Perfecto!» (banco g18 y g24)."""
    from src.agents import conversational_core as core
    from src.agents.nucleo import slotfill_close

    st = _grupo(detected_activity="certified_diving", is_certified=True, needs_companion_activity=True,
                core_pending_slot=core.SLOT_COMPANION_ACTIVITY)
    assert slotfill_close._acuse_por_codigo(st, core.SLOT_LOCATION) == ""
    st.location = "cartagena"
    assert slotfill_close._acuse_por_codigo(st, core.SLOT_LOCATION) != ""


@pytest.mark.parametrize("reparto, queda", [
    # conserva a quien ya eligió y da actividad a quien faltaba: completa, aunque empiece por «No wait»
    ({"certified_diving": 1, "minicourse": 1}, {"minicourse": 1, "certified_diving": 1}),
    # cambia lo que ya estaba elegido: es una corrección, no se completa aquí
    ({"snorkel": 1, "undecided": 1}, None),
])
def test_una_correccion_que_solo_completa_a_quien_faltaba_completa(monkeypatch, reparto, queda):
    """Sparring s03 con el lector del grupo (28-oct): ella minicurso y él sin elegir; «No wait, he's a certified diver,
    he wants the fun dives… Only I'm doing the mini course» se tiraba por el veto de Jev y él seguía sin elegir."""
    from src.agents.nucleo import extraction, extractor

    st = _grupo(detected_group_size=2, detected_group_allocation={"minicourse": 1}, pending_undecided_qty=1,
                needs_companion_activity=True, detected_activity="minicourse")
    st._jev_corrects = True
    monkeypatch.setattr(extractor, "_jev_dice_que_nadie_se_suma", lambda _st: True)
    mensaje = "No wait, he's a certified diver, he wants the fun dives with a refresher. Only I'm doing the mini course."
    intent = extraction.lectura_del_turno(mensaje)
    extractor._poner_grupo(intent, st, mensaje, {"group_allocation": reparto})
    if queda:
        assert intent.group_allocation == queda
    else:
        assert intent.group_allocation != {"minicourse": 1, "snorkel": 1}
