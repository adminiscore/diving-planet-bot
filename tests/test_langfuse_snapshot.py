"""Foto de Langfuse: agrupa observaciones por traza y resume por tipo de turno y nodo."""

from scripts.langfuse_snapshot import build_snapshot


def _obs(trace, type_, name, start, end, latency=None, **extra):
    return {"traceId": trace, "type": type_, "name": name, "startTime": start, "endTime": end, "latency": latency, **extra}


def test_build_snapshot_separates_rag_and_booking_turns():
    observations = [
        # Turno de reserva: 2 s, 2 llamadas LLM.
        _obs("t1", "SPAN", "LangGraph", "2026-09-16T10:00:00Z", "2026-09-16T10:00:02Z"),
        _obs("t1", "CHAIN", "router", "2026-09-16T10:00:00Z", "2026-09-16T10:00:01Z", 1.0),
        _obs("t1", "CHAIN", "_after_routing", "2026-09-16T10:00:01Z", "2026-09-16T10:00:01Z", 0.0),
        _obs("t1", "GENERATION", "OpenAI-generation", "2026-09-16T10:00:00Z", "2026-09-16T10:00:01Z", 0.9,
             model="gpt-4o-mini", totalUsage=100, totalCost=0.001),
        _obs("t1", "GENERATION", "OpenAI-generation", "2026-09-16T10:00:01Z", "2026-09-16T10:00:02Z", 0.8,
             model="gpt-4o-mini", totalUsage=50, totalCost=0.0005),
        # Turno RAG: 6 s, 1 llamada LLM + 1 embedding.
        _obs("t2", "CHAIN", "router", "2026-09-16T11:00:00Z", "2026-09-16T11:00:02Z", 2.0),
        _obs("t2", "EMBEDDING", "OpenAI-embedding", "2026-09-16T11:00:02Z", "2026-09-16T11:00:03Z", 0.3),
        _obs("t2", "GENERATION", "OpenAI-generation", "2026-09-16T11:00:03Z", "2026-09-16T11:00:06Z", 3.0,
             model="gpt-4.1-mini"),
    ]

    snap = build_snapshot(observations, "prueba", "2026-09-16T00:00:00Z", "2026-09-17T00:00:00Z", "staging")

    assert snap["all"]["turns"] == 2
    assert snap["by_type"]["reserva"]["turns"] == 1
    assert snap["by_type"]["reserva"]["latency_p50"] == 2.0
    assert snap["by_type"]["reserva"]["llm_calls_avg"] == 2
    assert snap["by_type"]["rag"]["latency_p50"] == 6.0
    assert snap["by_type"]["rag"]["embeddings_avg"] == 1
    # Los nodos internos (`_after_*`) y el SPAN raiz no cuentan como nodo.
    assert set(snap["nodes"]) == {"router"}
    assert snap["nodes"]["router"]["n"] == 2
    assert snap["models"] == {"gpt-4o-mini": 2, "gpt-4.1-mini": 1}
