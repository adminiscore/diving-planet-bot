"""arq-4b (22-oct), arreglos de los fallos del G10 nº 4 (banco docs/robustness/arq/banco-arq4b.json).

- `recotizar_al_cambiar_moneda`: «soy colombiano» DESPUÉS de recibir el precio en USD → se vuelve a dar en COP.
- `rag_comprueba_los_hechos`: el RAG con hechos (mensajes mezclados) recibe los bloques para comprobar su respuesta.
- `redactor_sin_preguntas_de_cierre`: el redactor no termina preguntando datos del cliente.
- `fecha_con_dia_de_la_semana`: la fecha del contexto lleva el día de la semana de hoy y de mañana.
"""

import pytest

from src.agents import redactor_hechos
from src.agents.nucleo.slotfill_close import _precio_en_su_moneda
from src.agents.rutas import contexto_rag
from src.flows.state import ConversationState

_CON_USD = [{"role": "assistant", "content": "El minicurso cuesta 183 USD reservando online."}]


def _estado(lang="es", colombiano=True, historial=_CON_USD, actividad="minicourse"):
    st = ConversationState(conversation_id="arq4b", language=lang)
    st.is_colombian = colombiano
    st.detected_activity = actividad
    st.history = list(historial)
    return st


@pytest.mark.parametrize("antes, colombiano, historial, sale", [
    (None, True, _CON_USD, True),
    (True, True, _CON_USD, False),  # ya lo sabía: el precio ya iba en COP
    (None, False, _CON_USD, False),  # no es colombiano: nada que cambiar
    (None, True, [], False),  # aún no se le dio ningún precio
])
def test_recotiza_en_cop_al_saber_que_es_colombiano(antes, colombiano, historial, sale):
    texto = _precio_en_su_moneda(_estado(colombiano=colombiano, historial=historial), {"prev_is_colombian": antes})
    assert bool(texto) is sale
    if sale:
        assert "COP" in texto and "USD" not in texto and texto.startswith("En pesos colombianos")


def test_recotiza_con_un_origen_sin_repetirlo(monkeypatch):
    st = _estado(lang="en")
    st.location = "cartagena"
    texto = _precio_en_su_moneda(st, {"prev_is_colombian": None})
    assert texto.startswith("In Colombian pesos") and texto.count("•") == 1 and "(from Cartagena)" not in texto


def test_grupo_mixto_no_recotiza(monkeypatch):
    st = _estado()
    st.mixed_nationality_notice = True
    assert _precio_en_su_moneda(st, {"prev_is_colombian": None}) == ""


def test_el_redactor_no_cierra_preguntando_datos():
    sistema = redactor_hechos._mensajes("es", [], "¿qué incluye?", "[]")[0]["content"]
    assert "No termines preguntando un dato del cliente" in sistema


def test_la_fecha_lleva_el_dia_de_la_semana(monkeypatch):
    st = ConversationState(conversation_id="arq4b", language="es")
    linea = contexto_rag._build_extra_context(st).splitlines()[0]
    assert "mañana es" in linea and any(d in linea for d in ("lunes", "martes", "miércoles", "jueves", "viernes",
                                                             "sábado", "domingo"))


def test_los_descuentos_son_una_intencion_de_la_tabla():
    from src.agents import jev_router as j

    q = j._questions_for_turn()
    assert j.PIDE_DESCUENTO in q
    assert "discounts" in q[j.PIDE_OTRA_COSA]["instructions"]
    assert j.answers_to_signals({j.PIDE_DESCUENTO: {"noul": 0.9}})[j.PIDE_DESCUENTO] is True


def test_los_hechos_del_descuento_con_y_sin_actividad():
    from src.flows import hechos as hechos_mod

    st = ConversationState(conversation_id="arq4b", language="es")
    con = hechos_mod.hechos(st, ["descuento"], ["snorkel"])[0]["descuento"]
    sin = hechos_mod.hechos_sin_actividad(st, ["descuento"])[0]["descuento"]
    assert con == sin and len(con) == 4 and any("grupos de 5" in d for d in con)
    respuesta = "Reservando online tienes un 10 % de descuento automático."
    assert hechos_mod.faltan(respuesta, [{"descuento": con}], ["descuento"])  # le faltan el de grupo, el del equipo…
