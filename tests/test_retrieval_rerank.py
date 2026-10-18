"""Temas de la pregunta (`detect_query_topics`): siguen saliendo en el log `[RAG][RETRIEVAL]` de cada búsqueda.

Los empujones por tema/fuente/subtipo que los usaban para reordenar (`source_weight_for_topics`,
`subtype_boost_for_topics`) eran el camino de la base antigua (`RAG_KB_V2` apagado) y se quitaron en s4-25: con la
base curada la búsqueda ordena solo por vector + palabras (RRF).
"""
from __future__ import annotations

import pytest

from src.knowledge.vector_store import detect_query_topics


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("¿Dónde es el punto de encuentro?", {"meeting_point"}),
        ("What is the meeting point gate?", {"meeting_point"}),
        ("¿Cuánto cuesta en pesos para colombianos?", {"pricing", "discount_colombian"}),
        ("El 10% de descuento necesita codigo?", {"discount"}),
        ("How can I pay? Do you have a QR?", {"payment"}),
        ("¿Cuál es la política de cancelación por clima?", {"weather_cancellation"}),
        ("¿Cómo reservo?", {"booking"}),
        ("Hace años no buceo, ¿necesito refresher?", {"refresher"}),
        ("Si no puedo viajar, ¿puedo mover la fecha?", {"reschedule"}),
        ("¿Qué profundidad máxima se bucea normalmente?", {"depth"}),
        ("¿El alojamiento está incluido?", {"accommodation"}),
        ("¿Qué debo llevar? (toalla, bloqueador, etc.)", {"equipment"}),
    ],
)
def test_detect_query_topics(query: str, expected: set[str]):
    topics = set(detect_query_topics(query))
    assert expected.issubset(topics)
