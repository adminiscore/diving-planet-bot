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


def test_turn_type_comes_from_the_bot_summary_when_present():
    observations = [
        _obs("t1", "SPAN", "turno", "2026-09-18T08:00:00Z", "2026-09-18T08:00:02Z", 2.0,
             metadata={"turn": {"turn_type": "saludo", "route": "booking", "booking_link_sent": False}}),
        _obs("t1", "CHAIN", "router", "2026-09-18T08:00:00Z", "2026-09-18T08:00:01Z", 1.0),
        # traza antigua sin resumen: se deduce por el embedding
        _obs("t2", "CHAIN", "router", "2026-09-18T09:00:00Z", "2026-09-18T09:00:01Z", 1.0),
        _obs("t2", "EMBEDDING", "OpenAI-embedding", "2026-09-18T09:00:01Z", "2026-09-18T09:00:02Z", 0.3),
    ]
    snap = build_snapshot(observations, "prueba", "2026-09-18T00:00:00Z", "2026-09-19T00:00:00Z", "staging")
    assert set(snap["by_turn_type"]) == {"saludo", "rag"}
    assert snap["by_type"]["reserva"]["turns"] == 1  # el saludo sigue en el corte historico "resto"
    assert snap["by_type"]["rag"]["turns"] == 1
    assert snap["turns_with_summary"] == 1


def _turn(session, **facts):
    """Una traza de un turno con su resumen (raiz `turno` + router)."""
    tid = f"{session}-{facts.pop('n', 0)}"
    start, end = "2026-09-21T08:00:00Z", "2026-09-21T08:00:02Z"
    return [
        _obs(tid, "SPAN", "turno", start, end, 2.0, sessionId=session,
             metadata={"turn_type": "reserva", **{f"turn_{k}": v for k, v in facts.items()}}),
        _obs(tid, "CHAIN", "router", start, end, 1.0, sessionId=session),
    ]


def test_business_funnel_counts_conversations_not_turns():
    observations = [
        # conv A: elige actividad, llena carrito y recibe el link (3 turnos)
        *_turn("A", n=1, activity_chosen=False, cart_items=0),
        *_turn("A", n=2, activity_chosen=True, cart_items=2),
        *_turn("A", n=3, activity_chosen=True, cart_items=2, booking_link_sent=True),
        # conv B: elige actividad y se queda ahi
        *_turn("B", n=1, activity_chosen=True, cart_items=0),
        # conv C: escala a humano y ademas un turno con fallback
        *_turn("C", n=1, escalated=True, fallback=True),
    ]
    b = build_snapshot(observations, "prueba", "2026-09-21T00:00:00Z", "2026-09-22T00:00:00Z", "staging")["business"]
    assert (b["conversations"], b["turns"], b["turns_per_conversation"]) == (3, 5, 1.67)
    assert b["funnel"]["eligen_actividad"]["conversations"] == 2
    assert b["funnel"]["carrito_con_personas"] == {"conversations": 1, "pct": 33.3}
    assert b["funnel"]["link_de_pago"]["pct"] == 33.3
    assert b["escalation_rate_pct"] == 33.3
    assert (b["fallback_turns"], b["fallback_pct_of_turns"]) == (1, 20.0)


def test_business_ignores_turns_without_the_bot_summary():
    old = [
        _obs("t", "CHAIN", "router", "2026-09-21T08:00:00Z", "2026-09-21T08:00:01Z", 1.0),
        _obs("t", "EMBEDDING", "OpenAI-embedding", "2026-09-21T08:00:01Z", "2026-09-21T08:00:02Z", 0.3),
    ]
    b = build_snapshot(old, "prueba", "2026-09-21T00:00:00Z", "2026-09-22T00:00:00Z", "staging")["business"]
    assert b["conversations"] == 0 and "note" in b


def test_turn_facts_read_flat_keys_even_as_text_and_the_old_nested_form():
    from scripts.langfuse_snapshot import turn_facts

    flat = [{"name": "turno", "metadata": {"turn_type": "rag", "turn_rag_used": "true", "turn_cart_items": "2", "scope": {}}}]
    assert turn_facts(flat) == {"turn_type": "rag", "rag_used": True, "cart_items": 2}
    nested_18_sep = [{"name": "turno", "metadata": {"turn": {"turn_type": "saludo"}}}]
    assert turn_facts(nested_18_sep) == {"turn_type": "saludo"}
    truncated = [{"name": "turno", "metadata": {"turn": '{"turn_type": "deflection", "escalated": false, '}}]
    assert turn_facts(truncated) == {}
