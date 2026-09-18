"""Foto de latencia y llamadas LLM por turno desde Langfuse (plan maestro, Fase M0).

Lee las observaciones de Langfuse de una ventana de tiempo (API v2; la API legacy de
trazas no existe para organizaciones creadas desde el 2026-09-16), las agrupa por traza
(= un turno del grafo) y resume:

- latencia del turno (p50/p95/media, desde la primera hasta la ultima observacion),
- llamadas LLM y embeddings por turno, tokens y coste,
- p50/p95 por nodo del grafo (router, setup, routing, extraction, slotfill_close, ...),
- modelos usados,

en total y por tipo de turno (`rag` = hubo embedding; `reserva` = el resto).

La salida es un JSON pensado para guardarse como una foto en el seguimiento del plan
(pagina compartida del equipo), para comparar antes/despues de cada fase.

Uso (no llama a ningun LLM, solo lee Langfuse):

    ENV_FILE=.env.dev python -m scripts.langfuse_snapshot --label "Baseline M0" \\
        [--from 2026-09-16T00:00:00Z] [--to 2026-09-17T00:00:00Z] [--env staging] [--out foto.json]

    # Tras una ejecucion de scripts.run_synthetic_pre: ventana y tiempo del cliente salen del fichero
    ENV_FILE=.env.dev python -m scripts.langfuse_snapshot --label "Cierre L1" \\
        --from-run docs/robustness/synthetic-runs/2026-09-17-m0.jsonl

Sin `--from` ni `--from-run` toma los ultimos 7 dias. Claves: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`
y `LANGFUSE_HOST` del entorno o del fichero `ENV_FILE`.
"""

import argparse
import base64
import json
import os
import statistics
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

_FIELDS = "core,basic,time,usage,model,metadata"


def _env(name: str, default: str = "") -> str:
    if os.environ.get(name):
        return os.environ[name]
    env_file = os.environ.get("ENV_FILE")
    if env_file and os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as fh:
            for line in fh:
                key, sep, value = line.strip().partition("=")
                if sep and key.strip() == name:
                    return value.strip().strip('"').strip("'")
    return default


def fetch_observations(host: str, auth: str, start: str, end: str, environment: str | None) -> list[dict]:
    out: list[dict] = []
    cursor = None
    while True:
        params = {"fromStartTime": start, "toStartTime": end, "limit": 1000, "fields": _FIELDS}
        if environment:
            params["environment"] = environment
        if cursor:
            params["cursor"] = cursor
        req = urllib.request.Request(
            f"{host.rstrip('/')}/api/public/v2/observations?{urllib.parse.urlencode(params)}",
            headers={"Authorization": "Basic " + auth},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            page = json.load(resp)
        out += page.get("data", [])
        cursor = (page.get("meta") or {}).get("cursor")
        if not cursor or not page.get("data"):
            return out


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 3)
    return round(statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1], 3)


def turn_facts(observations: list[dict]) -> dict:
    """Resumen del turno que escribe el bot en la raiz `turno` (m0-1, desde el 2026-09-18).
    Vacio en trazas anteriores."""
    for o in observations:
        meta = o.get("metadata") or {}
        if o.get("name") == "turno" and isinstance(meta, dict) and isinstance(meta.get("turn"), dict):
            return meta["turn"]
    return {}


def summarize_turn(observations: list[dict]) -> dict:
    gens = [o for o in observations if o["type"] == "GENERATION"]
    embs = [o for o in observations if o["type"] == "EMBEDDING"]
    facts = turn_facts(observations)
    # Tipo detallado: el del resumen del bot; en trazas antiguas, deducido (embedding = RAG).
    turn_type = facts.get("turn_type") or ("rag" if embs else "reserva")
    starts = [_ts(o["startTime"]) for o in observations if o.get("startTime")]
    ends = [_ts(o["endTime"]) for o in observations if o.get("endTime")]
    nodes: dict[str, float] = {}
    for o in observations:
        name = o.get("name") or ""
        if o["type"] == "CHAIN" and name != "LangGraph" and not name.startswith("_") and o.get("latency") is not None:
            nodes[name] = nodes.get(name, 0.0) + o["latency"]
    return {
        "start": min(starts).isoformat() if starts else None,
        # `type` mantiene el corte historico RAG / resto para que las fotos sigan siendo
        # comparables con la linea base; `turn_type` es el desglose fino.
        "type": "rag" if turn_type == "rag" else "reserva",
        "turn_type": turn_type,
        "route": facts.get("route"),
        "booking_link_sent": facts.get("booking_link_sent"),
        "escalated": facts.get("escalated"),
        "has_summary": bool(facts),
        "latency": (max(ends) - min(starts)).total_seconds() if starts and ends else None,
        "llm_calls": len(gens),
        "embeddings": len(embs),
        "tokens": sum(o.get("totalUsage") or 0 for o in gens + embs),
        "cost": sum(o.get("totalCost") or 0 for o in gens + embs),
        "llm_seconds": sum(o.get("latency") or 0 for o in gens),
        "models": Counter(o.get("model") for o in gens if o.get("model")),
        "nodes": nodes,
    }


def aggregate(turns: list[dict]) -> dict:
    lat = [t["latency"] for t in turns if t["latency"] is not None]
    calls = [float(t["llm_calls"]) for t in turns]
    return {
        "turns": len(turns),
        "latency_p50": _pct(lat, 50),
        "latency_p95": _pct(lat, 95),
        "latency_avg": round(statistics.mean(lat), 3) if lat else None,
        "llm_calls_avg": round(statistics.mean(calls), 2) if calls else None,
        "llm_calls_p95": _pct(calls, 95),
        "llm_calls_max": int(max(calls)) if calls else None,
        "embeddings_avg": round(statistics.mean(t["embeddings"] for t in turns), 2) if turns else None,
        "llm_share": round(sum(t["llm_seconds"] for t in turns) / sum(lat), 3) if lat and sum(lat) else None,
        "tokens_avg": round(statistics.mean(t["tokens"] for t in turns)) if turns else None,
        "cost_avg_usd": round(statistics.mean(t["cost"] for t in turns), 6) if turns else None,
    }


def build_snapshot(observations: list[dict], label: str, start: str, end: str, environment: str | None) -> dict:
    by_trace: dict[str, list[dict]] = defaultdict(list)
    for o in observations:
        by_trace[o["traceId"]].append(o)
    # Un turno del bot es una traza con exactamente un `router`. Con varios, la traza junta
    # varios turnos (contexto de traza que se queda pegado, visto en PRE el 2026-09-17): se
    # cuenta aparte. Sin router no es un turno del bot (p. ej. una traza manual): se ignora.
    def routers(obs: list[dict]) -> int:
        return sum(o.get("name") == "router" for o in obs)

    merged = [obs for obs in by_trace.values() if routers(obs) > 1]
    turns = sorted((summarize_turn(obs) for obs in by_trace.values() if routers(obs) == 1), key=lambda t: t["start"] or "")

    node_lat: dict[str, list[float]] = defaultdict(list)
    models: Counter = Counter()
    for t in turns:
        models.update(t["models"])
        for name, seconds in t["nodes"].items():
            node_lat[name].append(seconds)

    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None

    starts = [t["start"] for t in turns if t["start"]]
    return {
        "label": label,
        "taken_at": datetime.now(UTC).isoformat(timespec="seconds"),
        # Cuando se ejecuto el trafico medido (ultimo turno): el eje temporal del seguimiento.
        "run_at": max(starts) if starts else end,
        "commit": commit,
        "environment": environment,
        "window": {"from": start, "to": end, "first_turn": min(starts) if starts else None, "last_turn": max(starts) if starts else None},
        "merged_traces": {"traces": len(merged), "turns": sum(sum(o.get("name") == "router" for o in obs) for obs in merged)},
        "all": aggregate(turns),
        "by_type": {kind: aggregate([t for t in turns if t["type"] == kind]) for kind in ("reserva", "rag")},
        "by_turn_type": {kind: aggregate([t for t in turns if t["turn_type"] == kind]) for kind in sorted({t["turn_type"] for t in turns})},
        "turns_with_summary": sum(t["has_summary"] for t in turns),
        "nodes": {
            name: {"n": len(v), "p50": _pct(v, 50), "p95": _pct(v, 95)}
            for name, v in sorted(node_lat.items(), key=lambda kv: -statistics.median(kv[1]))
        },
        "models": dict(models.most_common()),
    }


def client_side(run_records: list[dict]) -> dict:
    """Resumen de una ejecucion de `run_synthetic_pre`: turnos, sin respuesta, varias
    burbujas y el tiempo que ve el cliente en Chatwoot."""
    lat = [r["client_latency_s"] for r in run_records if r.get("client_latency_s") is not None]
    return {
        "turns": len(run_records),
        "conversations": len({r["conv"] for r in run_records}),
        "no_reply": sum(r.get("reply") is None for r in run_records),
        "multi_bubble": sum((r.get("bubbles") or 0) > 1 for r in run_records),
        "latency_p50": _pct(lat, 50),
        "latency_p95": _pct(lat, 95),
        "latency_max": max(lat) if lat else None,
    }


def run_window(run_records: list[dict]) -> tuple[str, str]:
    """Ventana de Langfuse que cubre una ejecucion (margen para el primer turno y la ingesta)."""
    stamps = [_ts(r["at"]) for r in run_records]
    fmt = lambda d: d.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")  # noqa: E731
    return fmt(min(stamps) - timedelta(minutes=5)), fmt(max(stamps) + timedelta(minutes=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="Foto")
    parser.add_argument("--from", dest="start")
    parser.add_argument("--to", dest="end")
    parser.add_argument("--from-run", help="JSONL de scripts.run_synthetic_pre: fija la ventana y anade el tiempo del cliente")
    parser.add_argument("--env", default="staging", help="environment de Langfuse ('' = todos)")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    run_records = None
    if args.from_run:
        with open(args.from_run, encoding="utf-8") as fh:
            run_records = [json.loads(line) for line in fh if line.strip()]
        run_start, run_end = run_window(run_records)
        args.start, args.end = args.start or run_start, args.end or run_end

    public, secret = _env("LANGFUSE_PUBLIC_KEY"), _env("LANGFUSE_SECRET_KEY")
    if not (public and secret):
        print("Faltan LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY (entorno o ENV_FILE).", file=sys.stderr)
        return 2
    host = _env("LANGFUSE_HOST") or _env("LANGFUSE_BASE_URL") or "https://cloud.langfuse.com"
    auth = base64.b64encode(f"{public}:{secret}".encode()).decode()

    now = datetime.now(UTC)
    end = args.end or now.isoformat(timespec="seconds").replace("+00:00", "Z")
    start = args.start or (now - timedelta(days=7)).isoformat(timespec="seconds").replace("+00:00", "Z")
    environment = args.env or None

    snapshot = build_snapshot(fetch_observations(host, auth, start, end, environment), args.label, start, end, environment)
    if run_records is not None:
        snapshot["run_file"] = args.from_run.replace("\\", "/")
        snapshot["client_latency"] = client_side(run_records)
        # Langfuse tarda unos minutos en dejar consultables las trazas nuevas: una foto sacada
        # justo al acabar la ejecucion sale vacia o a medias (2026-09-18 salio 0 de 12).
        seen, sent = snapshot["all"]["turns"] + snapshot["merged_traces"]["turns"], len(run_records)
        if seen < 0.9 * sent:
            snapshot["incomplete"] = {"langfuse_turns": seen, "client_turns": sent}
            print(
                f"AVISO: Langfuse solo tiene {seen} de {sent} turnos de la ejecucion. Si acaba de terminar, "
                "espera 5-10 minutos (retraso de ingesta) y repite la foto.",
                file=sys.stderr,
            )
    text = json.dumps(snapshot, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
