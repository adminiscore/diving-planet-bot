from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.knowledge.vector_store import (
    detect_query_topics,
    source_weight_for_topics,
    subtype_boost_for_topics,
)


@dataclass(frozen=True)
class Candidate:
    source: str
    topics: list[str]
    score: float


def boosted_score(candidate: Candidate, query_topics: list[str]) -> float:
    overlap = set(query_topics) & set(candidate.topics)
    boost = 0.0
    if overlap:
        boost += 0.05 * len(overlap)
    boost += source_weight_for_topics(candidate.source, query_topics)
    return candidate.score + boost


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


def test_source_weight_prefers_policies_for_cancellation_weather():
    topics = ["weather_cancellation"]
    assert source_weight_for_topics("policies", topics) > source_weight_for_topics("faqs", topics)
    assert source_weight_for_topics("faqs", topics) > source_weight_for_topics("conversations", topics)


def test_source_weight_prefers_conversations_for_meeting_point():
    topics = ["meeting_point"]
    assert source_weight_for_topics("conversations", topics) > source_weight_for_topics("faqs", topics)
    assert source_weight_for_topics("faqs", topics) > source_weight_for_topics("policies", topics)


def test_rerank_orders_candidates_by_boosted_score():
    query_topics = ["meeting_point"]

    candidates = [
        Candidate(source="faqs", topics=["meeting_point"], score=0.80),
        Candidate(source="conversations", topics=["meeting_point"], score=0.80),
        Candidate(source="services", topics=["pricing"], score=0.95),
    ]

    ordered = sorted(candidates, key=lambda c: boosted_score(c, query_topics), reverse=True)

    assert ordered[0].source == "conversations"
    assert ordered[1].source == "faqs"


def test_rerank_policies_win_for_cancellation_even_if_semantically_close():
    query_topics = ["weather_cancellation"]

    candidates = [
        Candidate(source="conversations", topics=["weather_cancellation"], score=0.90),
        Candidate(source="policies", topics=["weather_cancellation"], score=0.86),
    ]

    ordered = sorted(candidates, key=lambda c: boosted_score(c, query_topics), reverse=True)
    assert ordered[0].source == "policies"


def test_subtype_boost_matches_intent_to_service_subchunk():
    assert subtype_boost_for_topics("pricing", ["pricing"]) > 0
    assert subtype_boost_for_topics("itinerary", ["schedule"]) > 0
    assert subtype_boost_for_topics("requirements", ["certification"]) > 0
    assert subtype_boost_for_topics("included", ["equipment"]) > 0


def test_subtype_boost_zero_when_subtype_mismatched_or_missing():
    assert subtype_boost_for_topics("pricing", ["schedule"]) == 0.0
    assert subtype_boost_for_topics(None, ["pricing"]) == 0.0
    assert subtype_boost_for_topics("itinerary", []) == 0.0
