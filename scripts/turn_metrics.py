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
            "llamadas": m.get("llamadas") or [],
            "router": m.get("router"),
            "router_ms": m.get("router_ms"),
            "rag_adelantado": m.get("rag_adelantado"),
            "rag_rehecho_por": m.get("rag_rehecho_por"),
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
        "rag_adelantado": rag_adelantado(turns),
        "por_pieza": por_pieza(turns),
        "coste": coste(turns),
    }


def coste(turns: list[dict]) -> dict:
    """mej-5 (21-oct): dólares y tokens de la ronda, por proveedor, pieza, modelo y conversación. OpenRouter trae su
    coste en cada llamada ("usd"); OpenAI se calcula con `scripts/precios_llm`. Las llamadas sin tokens (métricas de
    antes del 21-oct, o un fallo) no suman; las de un modelo sin precio se cuentan aparte en `sin_precio`."""
    from scripts.precios_llm import FECHA, coste_openai

    total = {"openai": 0.0, "openrouter": 0.0}
    piezas: dict[str, dict] = defaultdict(lambda: {"usd": 0.0, "in": 0, "out": 0, "n": 0})
    modelos: dict[str, float] = defaultdict(float)
    por_conv: dict[str, float] = defaultdict(float)
    sin_precio: Counter = Counter()
    for t in turns:
        for c in t.get("llamadas") or []:
            u = c.get("u") or {}
            if not u:
                continue
            if "usd" in u:
                usd, proveedor = float(u["usd"]), "openrouter"
            else:
                usd, proveedor = coste_openai(c.get("m"), u.get("in", 0), u.get("ca", 0), u.get("out", 0)), "openai"
                if usd is None:
                    sin_precio[c.get("m") or "?"] += 1
                    continue
            total[proveedor] += usd
            pieza = piezas[c.get("p") or "?"]
            pieza["usd"] += usd
            pieza["in"] += u.get("in", 0) or 0
            pieza["out"] += u.get("out", 0) or 0
            pieza["n"] += 1
            modelos[c.get("m") or "?"] += usd
            por_conv[str(t.get("session"))] += usd
    n = len(turns) or 1
    convs = sorted(por_conv.values())
    return {
        "precios": FECHA,
        "usd": round(total["openai"] + total["openrouter"], 4),
        "openai_usd": round(total["openai"], 4),
        "openrouter_usd": round(total["openrouter"], 4),
        "usd_por_100_turnos": round((total["openai"] + total["openrouter"]) * 100 / n, 4),
        "por_conversacion": {"n": len(convs), "p50": _pct(convs, 50), "max": round(max(convs), 4) if convs else None},
        "por_pieza": {p: {**v, "usd": round(v["usd"], 4)} for p, v in sorted(piezas.items(), key=lambda kv: -kv[1]["usd"])},
        "por_modelo": {m: round(v, 4) for m, v in sorted(modelos.items(), key=lambda kv: -kv[1])},
        "sin_precio": dict(sin_precio),
    }


def por_pieza(turns: list[dict]) -> dict:
    """r6-1: duración de las llamadas al LLM por pieza del bot (y modelo), en todos los turnos de la ronda."""
    tiempos: dict[str, list[float]] = defaultdict(list)
    modelos: dict[str, Counter] = defaultdict(Counter)
    for t in turns:
        for c in t.get("llamadas") or []:
            tiempos[c.get("p") or "?"].append(c.get("s") or 0.0)
            if c.get("m"):
                modelos[c.get("p") or "?"][c["m"]] += 1
    return {p: {"n": len(v), "p50": _pct(v, 50), "p95": _pct(v, 95), "modelos": dict(modelos[p])}
            for p, v in sorted(tiempos.items(), key=lambda kv: -len(kv[1]))}


def rag_adelantado(turns: list[dict]) -> dict:
    """rag-5: qué pasó con el RAG lanzado a la vez que el enrutador (aprovechado / rehecho / descartado), la
    latencia de los turnos RAG según ese resultado y, de los rehechos, qué parte del contexto cambió."""
    resultados = Counter(t.get("rag_adelantado") or "sin_adelantar" for t in turns)
    rag = [t for t in turns if t["type"] == "rag"]
    latencia = {}
    for r in sorted({t.get("rag_adelantado") or "sin_adelantar" for t in rag}):
        v = [t["latency"] for t in rag if (t.get("rag_adelantado") or "sin_adelantar") == r and t["latency"] is not None]
        latencia[r] = {"n": len(v), "p50": _pct(v, 50), "p95": _pct(v, 95)}
    rehecho_por = Counter(p for t in turns for p in (t.get("rag_rehecho_por") or "").split(",") if p)
    return {"resultados": dict(resultados), "latencia_turnos_rag": latencia, "rehecho_por": dict(rehecho_por)}


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
    parser.add_argument("--metricas", help="fichero .metricas de ronda_local_pre --metricas (sin ir al log de PRE)")
    args = parser.parse_args(argv)

    if args.metricas:
        # mej-5: las métricas que guarda la ronda sin desplegar (una línea JSON por turno, sin la etiqueta).
        with open(args.metricas, encoding="utf-8") as fh:
            turns = parse_lines(f"{TAG} {line}" for line in fh if line.strip())
        snapshot = build(turns, args.label, turns[0]["start"] if turns else "", turns[-1]["start"] if turns else "")
        text = json.dumps(snapshot, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0

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
