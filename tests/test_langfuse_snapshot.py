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
    assert snap["merged_traces"] == {"traces": 0, "turns": 0}


def test_build_snapshot_excludes_traces_that_merge_several_turns():
    observations = [
        _obs("ok", "CHAIN", "router", "2026-09-17T08:00:00Z", "2026-09-17T08:00:01Z", 1.0),
        _obs("merged", "CHAIN", "router", "2026-09-17T08:00:00Z", "2026-09-17T08:00:01Z", 1.0),
        _obs("merged", "CHAIN", "router", "2026-09-17T08:50:00Z", "2026-09-17T08:50:01Z", 1.0),
    ]

    snap = build_snapshot(observations, "prueba", "2026-09-17T00:00:00Z", "2026-09-18T00:00:00Z", "staging")

    assert snap["all"]["turns"] == 1
    assert snap["all"]["latency_p95"] == 1.0
    assert snap["merged_traces"] == {"traces": 1, "turns": 2}


def test_from_run_window_and_client_side_summary():
    from scripts.langfuse_snapshot import client_side, run_window

    records = [
        {"at": "2026-09-17T08:00:00+00:00", "conv": 1, "reply": "hola", "bubbles": 1, "client_latency_s": 3.0},
        {"at": "2026-09-17T08:10:00+00:00", "conv": 1, "reply": "a\n---\nb", "bubbles": 2, "client_latency_s": 7.0},
        {"at": "2026-09-17T08:20:00+00:00", "conv": 2, "reply": None, "bubbles": 0, "client_latency_s": None},
    ]

    assert run_window(records) == ("2026-09-17T07:55:00Z", "2026-09-17T08:22:00Z")
    summary = client_side(records)
    assert summary["turns"] == 3
    assert summary["conversations"] == 2
    assert summary["no_reply"] == 1
    assert summary["multi_bubble"] == 1
    assert summary["latency_max"] == 7.0


def test_traces_without_router_are_not_turns():
    observations = [
        _obs("turn", "CHAIN", "router", "2026-09-18T08:00:00Z", "2026-09-18T08:00:01Z", 1.0),
        _obs("manual", "SPAN", "deploy-diagnostico", "2026-09-18T08:00:00Z", "2026-09-18T08:00:00Z", 0.0),
    ]
    snap = build_snapshot(observations, "prueba", "2026-09-18T00:00:00Z", "2026-09-19T00:00:00Z", "staging")
    assert snap["all"]["turns"] == 1
