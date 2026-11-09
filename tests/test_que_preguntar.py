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


def test_si_no_falta_otro_y_no_para_la_reserva_se_cierra_con_lo_que_hay():
    estado = _sin_el_numero(is_colombian=False)
    estado.preguntas_hechas = {core.SLOT_QTY: 2}
    assert core.next_missing_slot(estado, saltar=qp.se_sigue_sin(estado.preguntas_hechas)) is None  # la tarjeta, por persona


@pytest.mark.parametrize("slot", sorted(qp.SE_SIGUE_SIN_ELLA))
def test_las_que_no_paran_la_reserva_son_huecos_que_el_flujo_sabe_saltar(slot):
    from src.agents.conversational_core import _SLOTS_APLAZABLES

    assert slot in _SLOTS_APLAZABLES and slot != core.SLOT_LOCATION and slot != core.SLOT_SAFETY


def test_antes_de_dos_veces_el_flujo_no_cambia():
    estado = _sin_el_numero()
    estado.preguntas_hechas = {core.SLOT_QTY: 1}
    assert _siguiente_pregunta(estado, None) == core.SLOT_QTY


# ─── Todas las combinaciones (CALN-43: cientos de casos, sin IA) ───

import itertools  # noqa: E402

from src.agents.nucleo import slotfill_close  # noqa: E402

_DATOS = {  # lo que falta si está a None
    "location": "cartagena", "detected_group_size": 2, "last_dive_over_2_years": False, "is_colombian": False,
}
_PREGUNTA_DE = {"location": core.SLOT_LOCATION, "detected_group_size": core.SLOT_QTY,
                "last_dive_over_2_years": core.SLOT_SAFETY, "is_colombian": core.SLOT_NATIONALITY}
_COMBINACIONES = list(itertools.product(itertools.product([True, False], repeat=4), itertools.product(range(4), repeat=4)))


def _caso(sabidos, veces):
    st = ConversationState(conversation_id="caln43-tabla", language="es", detected_activity="certified_diving", is_certified=True)
    for (campo, valor), sabido in zip(_DATOS.items(), sabidos):
        setattr(st, campo, valor if sabido else None)
    st.preguntas_hechas = {slot: n for slot, n in zip(_PREGUNTA_DE.values(), veces) if n}
    return st


def _lo_que_hace_el_turno(st, prev_pending):
    """Lo que decide `_slotfill_close_phase` (sin el hotel, el acompañante ni la despedida): cerrar, la tarjeta con el aviso de seguridad,
    o una pregunta."""
    nxt = core.next_missing_slot(st, saltar=qp.se_sigue_sin(st.preguntas_hechas))
    if nxt is None:
        return "cierra", None
    if slotfill_close._tarjeta_sin_seguridad(st, nxt, prev_pending):
        return "tarjeta", None
    return "pregunta", slotfill_close._siguiente_pregunta(st, nxt)


def test_son_cientos_de_casos():
    assert len(_COMBINACIONES) == 4096


@pytest.mark.parametrize("prev_pending", [None, core.SLOT_SAFETY])
def test_en_ningun_caso_sale_una_pregunta_por_3a_vez(prev_pending):
    for sabidos, veces in _COMBINACIONES:
        st = _caso(sabidos, veces)
        que, slot = _lo_que_hace_el_turno(st, prev_pending)
        faltan = {_PREGUNTA_DE[c] for c, sabido in zip(_DATOS, sabidos) if not sabido}
        hechas = st.preguntas_hechas
        if que == "cierra":
            # Solo se cierra si lo que falta se puede saltar (ya salió 2 veces) o no falta nada.
            assert faltan <= qp.se_sigue_sin(hechas), (sabidos, veces)
        elif que == "tarjeta":
            assert faltan - qp.se_sigue_sin(hechas) == {core.SLOT_SAFETY}, (sabidos, veces)
        else:
            assert slot in faltan, (sabidos, veces)
            assert slot not in qp.se_sigue_sin(hechas), (sabidos, veces)  # nunca una que se salta
            if not qp.se_puede_preguntar(hechas.get(slot, 0)):
                # Ya salió 2 veces: solo si no queda otra que preguntar, y es de las que paran la reserva. El compositor no la pone.
                assert all(not qp.se_puede_preguntar(hechas.get(s, 0)) for s in faltan), (sabidos, veces)
                assert slot not in qp.SE_SIGUE_SIN_ELLA, (sabidos, veces)
                assert qp.que_hacer(slot, hechas[slot], hay_respuesta=True) == qp.SIN_ELLA


# ─── Paso 5: todas las preguntas fijas del origen cuentan como la del origen ───

def test_la_pregunta_del_origen_antes_del_precio_cuenta_y_a_la_tercera_no_sale():
    from src.agents.nucleo.origen_precio import ORIGEN_ANTES_DEL_PRECIO_ES

    estado = _estado(None, "", veces=0, intenciones=["precio"])
    estado.preguntas_hechas = {}
    respuesta = f"El minicurso incluye la lancha y el almuerzo.\n\n{ORIGEN_ANTES_DEL_PRECIO_ES}"
    assert componer(estado, respuesta, escribio=True) == respuesta
    assert componer(estado, respuesta, escribio=True) == respuesta
    assert estado.preguntas_hechas[core.SLOT_LOCATION] == 2
    assert componer(estado, respuesta, escribio=True) == "El minicurso incluye la lancha y el almuerzo."


def test_la_lista_de_las_preguntas_del_origen_es_una_sola():
    from src.agents.nucleo import origen_precio as op

    lista = op.en_lugar_de_la_pregunta_del_origen()
    assert all(texto in lista for texto in op._preguntas_fijas_del_origen())
    assert all(texto in lista for por_idioma in core._CONFIRMA_ORIGEN.values() for texto in por_idioma.values())
    assert all("?" not in resto for resto in lista.values())  # lo que queda en su lugar no pregunta


# ─── Bloque 0,5 del Plan Gadea: el tono sin «cerrar con una pregunta» en la reserva, y el contador ───

@pytest.mark.parametrize("lang", ["es", "en"])
def test_en_la_reserva_el_escritor_no_recibe_las_ordenes_de_preguntar(lang):
    from src.agents import rag_agent
    from src.prompts import info

    siempre, reserva = rag_agent.build_system_prompt(lang), rag_agent.build_system_prompt(lang, sin_preguntas=True)
    cerrar = "Cerrar con una pregunta útil" if lang == "es" else "End with a useful question"
    falta = info.RAG_PREGUNTA_LO_QUE_FALTA_ES if lang == "es" else info.RAG_PREGUNTA_LO_QUE_FALTA_EN
    assert cerrar in siempre and falta in siempre  # fuera de la reserva, como siempre
    assert cerrar not in reserva and falta not in reserva
    linea = next(fila for fila in siempre.splitlines() if fila.startswith("- ") and cerrar in fila)
    assert siempre.replace(f"\n{linea}", "").replace(f"\n\n{falta}", "") == reserva  # solo cambian esas dos líneas


@pytest.mark.parametrize(("texto", "pregunta"), [
    ("Incluye el almuerzo.", False),
    ("Reserva aquí: https://book.divingplanet.org/book/salidas-de-buceo/1?language=es", False),  # el «?» del enlace no cuenta
    ("Incluye el almuerzo. ¿Quieres que te pase con un asesor?", True),
    ("Lunch is included. Would you like the link?", True),
    (None, False), ("", False),
])
def test_trae_pregunta(texto, pregunta):
    assert qp.trae_pregunta(texto) is pregunta


@pytest.mark.parametrize(("entradas", "texto", "cuenta"), [
    ({"sin_preguntas": True}, "Incluye el almuerzo. ¿Te paso con un asesor?", True),
    ({"sin_preguntas": True}, "Incluye el almuerzo.", False),
    ({}, "Incluye el almuerzo. ¿Te paso con un asesor?", False),  # fuera de la reserva puede preguntar
])
def test_el_contador_apunta_cuando_el_escritor_pregunta_en_la_reserva(monkeypatch, entradas, texto, cuenta):
    import src.observability as obs

    apuntado = {}
    monkeypatch.setattr(obs, "note_turn", lambda **k: apuntado.update(k))
    core.contar_si_el_escritor_pregunta(entradas, texto)
    assert apuntado.get("escritor_pregunta", False) is cuenta


def test_el_contador_sale_en_las_metricas_del_turno():
    from src.observability import turn_metrics_line

    linea = turn_metrics_line("c", {"escritor_pregunta": True}, "2026-11-09T21:00:00Z", 1.0)
    assert '"escritor_pregunta": true' in linea
