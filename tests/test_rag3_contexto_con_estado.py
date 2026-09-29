"""rag-3: si ya se sabe qué servicio mira el cliente, su ficha entera va al contexto.

Caso que lo abrió (`rag_piezas`, ronda 2026-09-28-rag2-B2): con `selected_service="open_water"`,
la pregunta "what time does the course finish on the first day?" no encontraba la hora. El dato
existe —el itinerario de la ficha dice "Day 1: meeting point at Muelle de la Bodeguita at 8:00
a.m."— pero la ficha no entraba en el top-8 de la búsqueda. El contexto solo inyectaba
incluye/no incluye, que no lleva horarios.

Los tests fijan las dos mitades del contrato, porque una sola no bastaría:
- encendido, la ficha (con itinerario) está en el contexto;
- **apagado, el contexto es exactamente el de hoy** — sin esto, el flag no sería reversible y el
  A/B no mediría nada.
"""

import pytest

from src.agents import supervisor
from src.config import settings
from src.flows.state import ConversationState


def _estado(lang: str = "en", **campos) -> ConversationState:
    st = ConversationState(conversation_id="rag3")
    st.language = lang
    for k, v in campos.items():
        setattr(st, k, v)
    return st


@pytest.fixture
def con_flag(monkeypatch):
    monkeypatch.setattr(settings, "rag_ficha_del_servicio", True)


@pytest.fixture
def sin_flag(monkeypatch):
    monkeypatch.setattr(settings, "rag_ficha_del_servicio", False)


def test_con_el_servicio_elegido_la_ficha_entra_en_el_contexto(con_flag):
    ctx = supervisor._build_extra_context(_estado(selected_service="open_water")) or ""
    assert "Itinerary:" in ctx, "la ficha tiene que viajar entera, no solo incluye/no incluye"
    assert "8:00 a.m." in ctx, "la hora del día 1 es el dato del caso que abrió rag-3"


def test_apagado_el_contexto_es_el_de_hoy(sin_flag):
    """Control deliberado: sin esto, el test de arriba pasaría aunque el flag no hiciera nada."""
    ctx = supervisor._build_extra_context(_estado(selected_service="open_water")) or ""
    assert "Itinerary:" not in ctx
    assert "8:00 a.m." not in ctx
    assert "currently viewing/considering" in ctx, "lo de hoy sí sigue: la actividad activa se nombra"


def test_sin_servicio_elegido_no_se_inyecta_ninguna_ficha(con_flag):
    """Segundo control: la ficha va SOLO cuando se sabe cuál. Si entrara siempre, el contexto
    crecería en todos los turnos y el A/B mediría otra cosa."""
    ctx = supervisor._build_extra_context(_estado(is_certified=True)) or ""
    assert "Itinerary:" not in ctx
    assert "Service sheet" not in ctx


def test_la_ficha_inyectada_es_la_del_idioma_del_cliente(con_flag):
    ctx_es = supervisor._build_extra_context(_estado("es", selected_service="open_water")) or ""
    assert "Itinerario:" in ctx_es
    assert "Itinerary:" not in ctx_es


def test_tambien_con_el_servicio_en_previsualizacion(con_flag):
    """`selected_service` no es la única vía: el carrito en previsualización y el plan pendiente de
    cantidad también dicen qué mira el cliente (es la cascada que ya usaba el bloque anterior)."""
    ctx = supervisor._build_extra_context(
        _estado(mixed_pending_preview_service_id="referral")
    ) or ""
    assert "Service sheet" in ctx
