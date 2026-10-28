"""gen-4 (21-oct, decisión de Gadea, Coral #862), flag `pago_colombiano_con_asesor`: el colombiano sigue pasando a un
asesor al cerrar, pero sin "confirmar disponibilidad" (siempre hay) y en su número, sin género; y el RAG, que a un
colombiano ya conocido le daba el link de reserva (banco docs/robustness/gen/dialogos-gen4-moneda.json), sabe que su
pago lo coordina un asesor.
"""

import pytest

from src.agents.nucleo import slotfill_close
from src.agents.rutas.contexto_rag import _build_extra_context
from src.flows.state import ConversationState


def _colombiano(lang: str, personas: int) -> ConversationState:
    st = ConversationState(conversation_id="gen4-cierre", language=lang)
    st.is_colombian = True
    st.detected_activity = "minicourse"
    st.detected_service_id = "minicourse"
    st.detected_group_size = personas
    st.location = "cartagena"
    return st


@pytest.mark.parametrize("lang, personas, numero", [
    ("es", 1, "puedes pagar"), ("es", 3, "pueden pagar"), ("en", 1, "You pay"), ("en", 3, "You pay"),
])
def test_el_cierre_sin_disponibilidad_y_en_su_numero(monkeypatch, lang, personas, numero):
    texto = slotfill_close._finalize(_colombiano(lang, personas))
    assert "disponibilidad" not in texto and "availability" not in texto
    assert numero in texto
    assert "Como son" not in texto and "colombianos/residentes" not in texto


def test_el_rag_sabe_que_el_pago_lo_coordina_un_asesor():
    contexto = _build_extra_context(_colombiano("es", 1)) or ""
    assert "no le compartas el link de reserva" in contexto
    extranjero = _colombiano("es", 1)
    extranjero.is_colombian = False
    assert "no le compartas el link" not in (_build_extra_context(extranjero) or "")


@pytest.mark.parametrize("intenciones, senales, mensaje, previo, pasa", [
    (["precio", "descuento"], {}, "¿qué precio tiene y hay descuento por ser 5?", "", False),  # sparring CALN3-R06
    (["pago"], {}, "listo, ¿cómo pagamos?", "", True),
    (["enlace"], {}, "¿cómo reservamos?", "", True),
    ([], {"wants_human": True}, "quiero hablar con alguien", "", True),
    ([], {}, "dale", "…\n\n" + slotfill_close._OFERTA_DEL_ASESOR["es_grupo"], True),
    ([], {}, "dale", "¿Ha pasado más de 2 años desde la última inmersión?", False),  # el «sí» es a otra pregunta
])
def test_el_colombiano_pasa_al_asesor_cuando_quiere_reservar_o_pagar(intenciones, senales, mensaje, previo, pasa):
    """28-oct (decisión de Gadea): no en cuanto sale la tarjeta; cuando lo pide o dice que sí a la oferta."""
    st = _colombiano("es", 5)
    st._intenciones, st._senales_router = intenciones, senales
    st.history = [{"role": "assistant", "content": previo}] if previo else []
    assert slotfill_close._quiere_reservar_o_pagar(st, mensaje) is pasa


def test_sin_querer_reservar_ve_el_precio_y_se_le_ofrece_el_asesor():
    st = _colombiano("es", 5)
    texto = slotfill_close._finalize(st, pasar_al_asesor=False)
    assert texto.endswith(slotfill_close._OFERTA_DEL_ASESOR["es_grupo"]) and "COP" in texto
    assert st.pending_escalation_reason is None
    assert slotfill_close._OFERTA_DEL_ASESOR["es_grupo"] not in slotfill_close._finalize(_colombiano("es", 5),
                                                                                        pasar_al_asesor=False, ofrecer=False)
