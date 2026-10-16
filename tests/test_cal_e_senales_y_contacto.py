"""CAL-E (16-oct): los seis fallos "sueltos" del banco, arreglados por causa y no por caso.

Las causas, leídas en el banco (`docs/robustness/cal/banco-fallos.json`):

1. **E1 `contacto_solo_lo_de_la_base`** (cal-03): al dar el WhatsApp oficial, el texto añadía "(solo mensajes de
   WhatsApp, no llamadas)", una restricción que NO está en la base: el juez la marca como invención. La aclaración
   sale de la base o no se dice. Si es verdad, el negocio la añade.
2. **E2 `queja_solo_si_algo_falla`** (cal-38, cal-39): "the discount of 10% is not showing up. what is the code?" se
   tomaba por un problema del sistema y el turno acababa en un pase a una persona diciendo "sorry the link didn't
   work". Lo que el cliente esperaba ver y no ve es una PREGUNTA que contesta la base. Se arregla en la frontera de
   las señales (queja de enlace y tema sensible), para toda la clase.
3. **E5 `jev_con_contexto`** (cal-29, cal-33): Jev contestaba las señales viendo solo el mensaje del turno, así que un
   mensaje referido perdía a qué se refiere ("Me lo podrías compartir por favor" tras "se me perdió el número";
   "Pero un link especial"). Con el flag le viajan los dos últimos mensajes como referencia.

Ninguno añade una lista de frases ni un patrón: ese es el fallo que arreglan (norma del proyecto).
"""

import pytest

from src.agents import jev_router as jr
from src.agents import supervisor as sv
from src.config import settings

# ---------------------------------------------------------------- E1: el contacto dice solo lo que está en la base


@pytest.fixture
def con_whatsapp(monkeypatch):
    monkeypatch.setattr(settings, "s4_fixes", True)
    monkeypatch.setattr(sv, "_official_whatsapp", lambda: "+57 320 231515")
    return monkeypatch


def test_sin_el_flag_el_texto_del_whatsapp_es_el_de_hoy(con_whatsapp):
    con_whatsapp.setattr(settings, "contacto_solo_lo_de_la_base", False)
    assert "solo mensajes de WhatsApp, no llamadas" in sv._contact_number_deflection("es")


def test_con_el_flag_no_se_afirma_lo_que_la_base_no_dice(con_whatsapp):
    """cal-03: la restricción no está en la base y el juez la marca como invención."""
    con_whatsapp.setattr(settings, "contacto_solo_lo_de_la_base", True)
    con_whatsapp.setattr(sv, "_nota_del_whatsapp", lambda lang: "")
    es = sv._contact_number_deflection("es")
    assert "+57 320 231515" in es, "el número sí se da (decisión de Gadea del 17-sep)"
    assert "llamadas" not in es and "(" not in es.split("*")[-1]
    en = sv._contact_number_deflection("en")
    assert "calls" not in en


def test_si_la_base_trae_la_aclaracion_se_dice(con_whatsapp):
    """El negocio la añade a `escalation_rules.json` (`contact_info.nota_es`/`nota_en`) y entonces sí se dice."""
    con_whatsapp.setattr(settings, "contacto_solo_lo_de_la_base", True)
    con_whatsapp.setattr(sv, "_nota_del_whatsapp", lambda lang: "solo mensajes" if lang == "es" else "messages only")
    assert "(solo mensajes)" in sv._contact_number_deflection("es")
    assert "(messages only)" in sv._contact_number_deflection("en")


def test_la_nota_del_whatsapp_sale_de_la_base(monkeypatch):
    from src.knowledge import loader

    monkeypatch.setattr(loader, "load_json", lambda nombre: {
        "handoff_protocol": {"contact_info": {"whatsapp": "+57 1", "nota_es": "solo mensajes", "nota_en": "msgs"}}})
    assert sv._nota_del_whatsapp("es") == "solo mensajes"
    assert sv._nota_del_whatsapp("en") == "msgs"
    monkeypatch.setattr(loader, "load_json", lambda nombre: {"handoff_protocol": {"contact_info": {}}})
    assert sv._nota_del_whatsapp("es") == ""


# ---------------------------------------------------------------- E2: lo que no aparece no es un fallo


def test_sin_el_flag_las_senales_son_las_de_hoy(monkeypatch):
    monkeypatch.setattr(settings, "queja_solo_si_algo_falla", False)
    preguntas = jr._questions_for_turn()
    assert "is not showing up" not in preguntas["broken_link_complaint"]["instructions"]
    assert "is not showing up" not in preguntas["sensitive_topic"]["instructions"]


def test_con_el_flag_lo_que_el_cliente_esperaba_ver_no_es_un_fallo(monkeypatch):
    """cal-38/cal-39: el descuento que no aparece no es un enlace roto ni un problema en tiempo real."""
    monkeypatch.setattr(settings, "queja_solo_si_algo_falla", True)
    preguntas = jr._questions_for_turn()
    for nombre in ("broken_link_complaint", "sensitive_topic"):
        instrucciones = preguntas[nombre]["instructions"]
        assert "is not showing up" in instrucciones
        assert "normal question about how it works" in instrucciones
    # La frontera vale para la clase (descuento, precio, opción, código), no para un caso.
    for palabra in ("discount", "a price", "an option", "a code"):
        assert palabra in jr._NO_APARECE_NO_ES_FALLO


# ---------------------------------------------------------------- E5: Jev con los últimos turnos


_HISTORIAL = [{"role": "user", "content": "Se me perdió el número de la persona que me atendió"},
              {"role": "assistant", "content": "Entiendo que se te perdió el número. ¿Desde dónde saldrías?"}]


def test_sin_el_flag_jev_ve_solo_el_mensaje(monkeypatch):
    monkeypatch.setattr(settings, "jev_con_contexto", False)
    estado = jr._estado_para_jev("Me lo podrías compartir por favor", _HISTORIAL)
    assert estado.endswith("Customer message: Me lo podrías compartir por favor")
    assert "Se me perdió" not in estado


def test_con_el_flag_jev_ve_a_que_se_refiere(monkeypatch):
    """cal-33: sin el turno anterior, "me lo podrías compartir" no es una petición de contacto para nadie."""
    monkeypatch.setattr(settings, "jev_con_contexto", True)
    estado = jr._estado_para_jev("Me lo podrías compartir por favor", _HISTORIAL)
    assert "Se me perdió el número" in estado
    assert "Customer message: Me lo podrías compartir por favor" in estado
    assert "about THIS last message" in estado, "las preguntas siguen siendo sobre el mensaje de este turno"


def test_el_contexto_son_los_ultimos_turnos_y_va_cortado(monkeypatch):
    monkeypatch.setattr(settings, "jev_con_contexto", True)
    largo = [{"role": "user", "content": f"mensaje {i}"} for i in range(10)]
    largo.append({"role": "assistant", "content": "x" * 2000})
    estado = jr._estado_para_jev("y ahora?", largo)
    assert "mensaje 9" in estado and "mensaje 7" not in estado, "solo los dos últimos"
    assert len(estado) < 2000, "el turno largo va cortado"


def test_sin_historial_el_estado_es_el_de_siempre(monkeypatch):
    monkeypatch.setattr(settings, "jev_con_contexto", True)
    assert jr._estado_para_jev("hola", None) == jr._estado_para_jev("hola", [])
    assert jr._estado_para_jev("hola", [{"role": "user", "content": ""}]).endswith("Customer message: hola")
