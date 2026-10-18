"""CAL-F pareja-certificados-cop-descuento-almuerzo (18-oct, decisión de Gadea), flag `tarjeta_sin_seguridad`.

Si solo falta la respuesta de seguridad y el cliente no la contestó, la tarjeta con el precio sale igualmente, con la
pregunta una vez dentro y el precio del refresher en UNA sola moneda (COP a colombianos y residentes; USD al resto).
"""

import pytest

from src.agents import conversational_core as core
from src.config import settings
from src.flows import cart_render
from src.flows.state import ConversationState


def _pareja(colombianos=True):
    st = ConversationState(conversation_id="calf-pareja")
    st.language = "es"
    st.detected_activity = "certified_diving"
    st.is_certified = st.detected_is_certified = True
    st.location = st.detected_location = "cartagena"
    st.detected_group_size = 2
    st.is_colombian = colombianos
    return st


@pytest.mark.parametrize("flag, prev, sale", [(True, core.SLOT_SAFETY, True), (False, core.SLOT_SAFETY, False),
                                              (True, None, False)])
def test_la_tarjeta_sale_si_solo_falta_la_seguridad_sin_contestar(monkeypatch, flag, prev, sale):
    monkeypatch.setattr(settings, "tarjeta_sin_seguridad", flag)
    st = _pareja()
    nxt = core.next_missing_slot(st)
    assert nxt == core.SLOT_SAFETY
    assert core._tarjeta_sin_seguridad(st, nxt, prev) is sale


def test_si_falta_otra_cosa_no_sale(monkeypatch):
    monkeypatch.setattr(settings, "tarjeta_sin_seguridad", True)
    st = _pareja(colombianos=None)  # falta también la nacionalidad
    assert core._tarjeta_sin_seguridad(st, core.SLOT_SAFETY, core.SLOT_SAFETY) is False


@pytest.mark.parametrize("colombianos, moneda, otra", [(True, "COP", "USD"), (False, "USD", "COP")])
def test_la_nota_lleva_una_sola_moneda(colombianos, moneda, otra):
    nota = core._nota_seguridad(_pareja(colombianos))
    assert moneda in nota and otra not in nota and "2 años" in nota


def test_sin_una_moneda_el_precio_de_siempre():
    texto = cart_render.refresher_price_text(_pareja())
    assert "USD" in texto and "COP" in texto


# mod-7 (decisión de Gadea): las notas por OpenRouter van sin datos personales ---------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("modelo, tapado", [("gpt-4o-mini", False), ("deepseek/deepseek-v4.1-flash", True)])
async def test_las_notas_por_openrouter_van_sin_datos_personales(monkeypatch, modelo, tapado):
    from src.agents import notes_extractor

    monkeypatch.setattr(settings, "notas_model", modelo)
    llamadas = []

    class _C:
        async def create(self, **kw):
            llamadas.append(kw)
            raise RuntimeError("fin")

    cliente = type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})()
    await notes_extractor.extract_notes("mi correo es ana.perez@gmail.com y soy alérgica", client=cliente)
    texto = llamadas[0]["messages"][-1]["content"]
    assert ("ana.perez@gmail.com" not in texto) is tapado
