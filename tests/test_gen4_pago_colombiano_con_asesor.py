"""gen-4 (21-oct, decisión de Gadea, Coral #862), flag `pago_colombiano_con_asesor`: el colombiano sigue pasando a un
asesor al cerrar, pero sin "confirmar disponibilidad" (siempre hay) y en su número, sin género; y el RAG, que a un
colombiano ya conocido le daba el link de reserva (banco docs/robustness/gen/dialogos-gen4-moneda.json), sabe que su
pago lo coordina un asesor.
"""

import pytest

from src.agents.nucleo import slotfill_close
from src.agents.rutas.contexto_rag import _build_extra_context
from src.config import settings
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
    monkeypatch.setattr(settings, "pago_colombiano_con_asesor", True)
    texto = slotfill_close._finalize(_colombiano(lang, personas))
    assert "disponibilidad" not in texto and "availability" not in texto
    assert numero in texto
    assert "Como son" not in texto and "colombianos/residentes" not in texto


def test_sin_el_flag_el_cierre_de_siempre(monkeypatch):
    monkeypatch.setattr(settings, "pago_colombiano_con_asesor", False)
    assert "confirmar disponibilidad" in slotfill_close._finalize(_colombiano("es", 1))


@pytest.mark.parametrize("flag", [False, True])
def test_el_rag_sabe_que_el_pago_lo_coordina_un_asesor(monkeypatch, flag):
    monkeypatch.setattr(settings, "pago_colombiano_con_asesor", flag)
    contexto = _build_extra_context(_colombiano("es", 1)) or ""
    assert ("no le compartas el link de reserva" in contexto) is flag
    extranjero = _colombiano("es", 1)
    extranjero.is_colombian = False
    assert "no le compartas el link" not in (_build_extra_context(extranjero) or "")
