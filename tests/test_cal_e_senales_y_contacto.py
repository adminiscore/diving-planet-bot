"""CAL-E (16-oct): los seis fallos "sueltos" del banco, arreglados por causa y no por caso.

Las causas, leídas en el banco (`docs/robustness/cal/banco-fallos.json`):

1. **E1 `contacto_pasa_a_persona`** (cal-03, cal-33): DECISIÓN DE GADEA del 16-oct, que sustituye a la del 17-sep:
   esto es un chatbot y **no da números** de teléfono ni de WhatsApp. Quien pide un número o quiere hablar con
   alguien, pasa con un asesor. Así desaparece también la invención que el juez marcaba ("solo mensajes, no
   llamadas", que la base no dice). El criterio del golden `contacto-real` y los casos del banco se actualizaron.
2. **E2, DESCARTADO el 17-oct** (ver §4): decía que lo que el cliente esperaba ver y no ve no es una avería, pero el
   criterio `escala-si-no-aparece` del golden pide justo que se ofrezca un asesor, y cal-38 y cal-39 ya pasan solos.
   Se quitó el flag y su código.
3. **E5 `jev_con_contexto`** (cal-29, cal-33): Jev contestaba las señales viendo solo el mensaje del turno, así que un
   mensaje referido perdía a qué se refiere ("Me lo podrías compartir por favor" tras "se me perdió el número";
   "Pero un link especial"). Con el flag le viajan los dos últimos mensajes como referencia.

Ninguno añade una lista de frases ni un patrón: ese es el fallo que arreglan (norma del proyecto).
"""

import pytest

from src.agents import jev_router as jr
from src.agents import supervisor as sv
from src.config import settings

# ---------------------------------------------------------------- E1: el contacto pasa a una persona


def test_con_el_flag_la_peticion_de_contacto_pasa_a_un_asesor(monkeypatch):
    """Decisión de Gadea (16-oct): esto es un chatbot y no da números. Quien pide un número o quiere hablar con
    alguien, pasa con un asesor. De paso desaparece la invención de cal-03 ("solo mensajes, no llamadas", que la base
    no dice): ya no hay número que afirmar."""
    from src.flows.state import ConversationState, Step

    monkeypatch.setattr(settings, "contacto_pasa_a_persona", True)
    monkeypatch.setattr(sv, "build_lead_summary", lambda state, escalation_reason=None: "resumen")
    st = ConversationState(conversation_id="t")
    es = sv._contacto_pasa_a_persona(st, "es")
    assert "asesor" in es
    assert "320" not in es and "+57" not in es, "ningún número"
    assert "llamadas" not in es, "ninguna condición que la base no diga"
    assert st.step is Step.ESCALATE
    assert st.pending_escalation_reason and st.pending_note == "resumen"
    en = sv._contacto_pasa_a_persona(ConversationState(conversation_id="t2"), "en")
    assert "advisor" in en and "+57" not in en


def test_con_el_flag_el_texto_de_antes_no_da_el_numero(monkeypatch):
    monkeypatch.setattr(settings, "s4_fixes", True)
    monkeypatch.setattr(sv, "_official_whatsapp", lambda: "+57 320 231515")
    monkeypatch.setattr(settings, "contacto_pasa_a_persona", True)
    assert "+57" not in sv._contact_number_deflection("es")


def test_sin_el_flag_el_comportamiento_es_el_de_hoy(monkeypatch):
    """Hasta medirlo, PRE sigue dando el WhatsApp (decisión del 17-sep)."""
    monkeypatch.setattr(settings, "s4_fixes", True)
    monkeypatch.setattr(sv, "_official_whatsapp", lambda: "+57 320 231515")
    monkeypatch.setattr(settings, "contacto_pasa_a_persona", False)
    assert "+57 320 231515" in sv._contact_number_deflection("es")


# ---------------------------------------------------------------- E3: lo que el sistema no da, lo hace una persona


def test_con_el_flag_lo_que_el_sistema_no_da_pasa_a_una_persona(monkeypatch):
    """cal-29: "Pero un link especial" (una agencia que quiere un enlace para sus clientes) no era, para la señal,
    algo que solo pueda hacer una persona, así que el bot lo explicaba sin ofrecer el pase."""
    monkeypatch.setattr(settings, "s4_fixes", True)
    monkeypatch.setattr(settings, "pase_si_pide_fuera_del_sistema", False)
    assert "special" not in jr._questions_for_turn()["needs_staff"]["instructions"]
    monkeypatch.setattr(settings, "pase_si_pide_fuera_del_sistema", True)
    instrucciones = jr._questions_for_turn()["needs_staff"]["instructions"]
    assert "'special' payment link" in instrucciones
    assert "only a person can" in instrucciones
    # Clase, no caso: la factura, las tarifas y la salida privada entran igual.
    for palabra in ("invoice", "private", "outside the website"):
        assert palabra in jr._FUERA_DEL_SISTEMA


# ---------------------------------------------------------------- E4: el idioma lo dice el extractor


@pytest.mark.asyncio
async def test_el_idioma_del_primer_turno_lo_dice_el_extractor(monkeypatch):
    """cal-12: "Busco el seguinte: Vamos en família a Cartagena" tiene tantas palabras iguales al español que la
    heurística de palabras vacías dice "es" y corta la cadena. El extractor (ya lanzado con el enrutador) dice `pt`,
    y la regla G-10 de Gadea manda contestar en inglés."""
    import asyncio

    from src.agents import conversational_core as core
    from src.flows.state import ConversationState

    monkeypatch.setattr(settings, "idioma_del_extractor", True)
    monkeypatch.setattr(settings, "idioma_otro_en_ingles", True)
    st = ConversationState(conversation_id="t")

    async def extraccion():
        return {"idioma": "pt"}

    st._extraccion_adelantada = asyncio.create_task(extraccion())
    mensaje = "Busco el seguinte: Vamos en família a Cartagena. 1 buzo avanzado y 2 para bautismo"
    assert await core._idioma_del_extractor(st, mensaje) == "en"


@pytest.mark.asyncio
async def test_el_extractor_no_cambia_el_espanol_ni_el_ingles(monkeypatch):
    import asyncio

    from src.agents import conversational_core as core
    from src.flows.state import ConversationState

    monkeypatch.setattr(settings, "idioma_del_extractor", True)
    monkeypatch.setattr(settings, "idioma_otro_en_ingles", True)
    for idioma, esperado in (("es", "es"), ("en", "en"), ("fr", "en")):
        st = ConversationState(conversation_id="t")

        async def extraccion(i=idioma):
            return {"idioma": i}

        st._extraccion_adelantada = asyncio.create_task(extraccion())
        assert await core._idioma_del_extractor(st, "hola quiero bucear en las islas") == esperado


@pytest.mark.asyncio
async def test_sin_el_flag_o_sin_extraccion_decide_la_cadena_de_siempre(monkeypatch):
    import asyncio

    from src.agents import conversational_core as core
    from src.flows.state import ConversationState

    monkeypatch.setattr(settings, "idioma_otro_en_ingles", True)
    st = ConversationState(conversation_id="t")

    async def extraccion():
        return {"idioma": "pt"}

    st._extraccion_adelantada = asyncio.create_task(extraccion())
    monkeypatch.setattr(settings, "idioma_del_extractor", False)
    assert await core._idioma_del_extractor(st, "un mensaje largo en portugues brasileiro") is None
    # Con el flag pero sin extracción (o con un mensaje de dos palabras), tampoco decide.
    monkeypatch.setattr(settings, "idioma_del_extractor", True)
    vacio = ConversationState(conversation_id="t2")
    assert await core._idioma_del_extractor(vacio, "un mensaje largo de verdad") is None
    assert await core._idioma_del_extractor(st, "bom dia") is None
    st._extraccion_adelantada.cancel()


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


def test_el_enrutador_de_respaldo_tambien_ve_los_ultimos_turnos(monkeypatch):
    """La otra mitad de E5, medida con la sonda: con contexto Jev sube a 0,63, cae en la zona de duda y decide el
    enrutador LLM, que veía solo el mensaje. Si el contexto no llega también aquí, el arreglo no sirve."""
    from src.agents import escalation

    monkeypatch.setattr(settings, "jev_con_contexto", False)
    assert escalation._mensaje_con_contexto("Me lo podrías compartir", _HISTORIAL) == "Me lo podrías compartir"
    monkeypatch.setattr(settings, "jev_con_contexto", True)
    con = escalation._mensaje_con_contexto("Me lo podrías compartir", _HISTORIAL)
    assert "Se me perdió el número" in con
    assert con.rstrip().endswith("Me lo podrías compartir")
    assert "SOLO este último mensaje" in con
    assert escalation._mensaje_con_contexto("hola", None) == "hola"


def test_sin_historial_el_estado_es_el_de_siempre(monkeypatch):
    monkeypatch.setattr(settings, "jev_con_contexto", True)
    assert jr._estado_para_jev("hola", None) == jr._estado_para_jev("hola", [])
    assert jr._estado_para_jev("hola", [{"role": "user", "content": ""}]).endswith("Customer message: hola")
