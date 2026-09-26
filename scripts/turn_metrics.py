"""Foto de latencia y llamadas SIN Langfuse: lee las líneas `[TURN_METRICS]` del bot en PRE.

Desde el 24-sep-2026 cada turno escribe en el log de `dp-pre-bot` una línea
`[TURN_METRICS] {json}` (ver `src/observability.py`): resumen del turno, llamadas al LLM
(cuántas, cuánto tardan, modelo) y tiempo de cada nodo del grafo. Este script las baja
por SSH y construye la MISMA foto que `scripts/langfuse_snapshot.py` (mismos campos:
`all`, `by_type`, `by_turn_type`, `nodes`, `business`, `client_latency`), así que las dos
son comparables y la foto se puede pegar en la página igual. Sin límites de uso.

Diferencias con Langfuse: no hay tokens ni coste (salen a 0) y el tiempo del turno es el
del bot (de que entra el mensaje a que sale la respuesta), no el de la traza.

Uso:

    python -m scripts.turn_metrics --label "..." --from-run docs/robustness/synthetic-runs/<fichero>.jsonl [--out foto.json]
    python -m scripts.turn_metrics --from 2026-09-24T10:00:00Z --to 2026-09-24T11:00:00Z

SSH: `~/.ssh/dp_pre_vps` y `root@89.167.4.161` por defecto (`PRE_SSH_KEY` / `PRE_SSH_HOST`), vía `scripts/pre_access.py`.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from scripts.langfuse_snapshot import _pct, aggregate, business_metrics, client_side, run_window
from scripts.pre_access import pre_ssh

TAG = "[TURN_METRICS]"


def parse_lines(lines) -> list[dict]:
    """Líneas del log -> turnos con la forma de `langfuse_snapshot.summarize_turn`."""
    turns = []
    for line in lines:
        i = line.find(TAG)
        if i < 0:
            continue
        try:
            m = json.loads(line[i + len(TAG):].strip())
        except ValueError:
            continue
        turn_type = m.get("turn_type") or "otro"
        turns.append({
            "start": m.get("start"),
            "type": "rag" if turn_type == "rag" else "reserva",
            "turn_type": turn_type,
            "route": m.get("route"),
            "booking_link_sent": m.get("booking_link_sent"),
            "escalated": m.get("escalated"),
            "activity_chosen": m.get("activity_chosen"),
            "cart_items": m.get("cart_items"),
            "fallback": m.get("fallback"),
            "session": m.get("conv"),
            "has_summary": True,
            "latency": m.get("latency"),
            "llm_calls": m.get("llm_calls") or 0,
            "embeddings": m.get("embeddings") or 0,
            "tokens": 0,
            "cost": 0,
            "llm_seconds": m.get("llm_seconds") or 0,
            "models": Counter(m.get("models") or {}),
            "nodes": m.get("nodes") or {},
            "router": m.get("router"),
            "router_ms": m.get("router_ms"),
        })
    return sorted(turns, key=lambda t: t["start"] or "")


def build(turns: list[dict], label: str, start: str, end: str) -> dict:
    node_lat: dict[str, list[float]] = defaultdict(list)
    models: Counter = Counter()
    for t in turns:
        models.update(t["models"])
        for name, seconds in t["nodes"].items():
            node_lat[name].append(seconds)
    routers = Counter(t["router"] or "llm" for t in turns)
    router_ms = [t["router_ms"] for t in turns if t.get("router_ms") is not None]
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    starts = [t["start"] for t in turns if t["start"]]
    return {
        "label": label,
        "source": "turn_metrics (log de PRE)",
        "taken_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_at": max(starts) if starts else end,
        "commit": commit,
        "environment": "staging",
        "window": {"from": start, "to": end, "first_turn": min(starts) if starts else None, "last_turn": max(starts) if starts else None},
        "all": aggregate(turns),
        "by_type": {kind: aggregate([t for t in turns if t["type"] == kind]) for kind in ("reserva", "rag")},
        "by_turn_type": {kind: aggregate([t for t in turns if t["turn_type"] == kind]) for kind in sorted({t["turn_type"] for t in turns})},
        "turns_with_summary": len(turns),
        "business": business_metrics(turns),
        "nodes": {
            name: {"n": len(v), "p50": _pct(v, 50), "p95": _pct(v, 95)}
            for name, v in sorted(node_lat.items(), key=lambda kv: -statistics.median(kv[1]))
        },
        "router": {"by_backend": dict(routers), "ms_p50": _pct(router_ms, 50), "ms_p95": _pct(router_ms, 95)},
        "models": dict(models.most_common()),
    }


def fetch_log_lines(start: str, end: str) -> list[str]:
    cmd = f"docker logs dp-pre-bot --since {start} --until {end} 2>&1 | grep -F '{TAG}'"
    return pre_ssh(cmd, timeout=300).stdout.splitlines()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="Foto")
    parser.add_argument("--from", dest="start")
    parser.add_argument("--to", dest="end")
    parser.add_argument("--from-run", help="JSONL de scripts.run_synthetic_pre: fija la ventana y añade el tiempo del cliente")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    run_records = None
    if args.from_run:
        with open(args.from_run, encoding="utf-8") as fh:
            run_records = [json.loads(line) for line in fh if line.strip()]
        run_start, run_end = run_window(run_records)
        args.start, args.end = args.start or run_start, args.end or run_end
    if not (args.start and args.end):
        print("Hace falta --from-run o --from/--to.", file=sys.stderr)
        return 2

    turns = parse_lines(fetch_log_lines(args.start, args.end))
    snapshot = build(turns, args.label, args.start, args.end)
    if run_records is not None:
        snapshot["run_file"] = args.from_run.replace("\\", "/")
        snapshot["client_latency"] = client_side(run_records)
        if len(turns) < 0.9 * len(run_records):
            print(f"AVISO: el log solo tiene {len(turns)} de {len(run_records)} turnos (¿se reinició el bot?).", file=sys.stderr)
    text = json.dumps(snapshot, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
