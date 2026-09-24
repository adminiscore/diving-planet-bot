"""Escalón 0 barato: reproducir en LOCAL los diálogos del golden (sin examen oculto) con un
flag apagado y encendido, con el estado REAL turno a turno (se usó en u3-4, 24-sep).

Uso (dos pasadas, luego `scripts/replay_diff.py`):
    python -m scripts.replay_golden_local --flag answer_and_continue --side off
    python -m scripts.replay_golden_local --flag answer_and_continue --side on
Salida: docs/robustness/<dir>/replay-<side>.jsonl (por defecto --dir u3-4).
Coste: céntimos (solo extracción + Jev; RAG/acuse/notas son respuestas fijas).

Lo que se mide es la EXTRACCIÓN (qué datos guarda cada versión) y si la pregunta se contesta
(la respuesta del RAG sale como «RAG» en el texto). Extracción, veto, señales especiales y
router (Jev) son los de verdad, con los flags de PRE (fijados abajo; revísalos si cambia
docker-compose.vps.yml). Chatwoot apunta a una dirección muerta: no se envía nada.
Necesita .env.dev con OPENAI_API_KEY y OPENROUTER_API_KEY.
"""
import asyncio
import json
import os
from pathlib import Path

os.environ.update({
    "ENV_FILE": ".env.dev", "APP_ENV": "development",
    "LLM_EXTRACTION_CUTOVER_CERTIFICATION": "true", "LLM_EXTRACTION_CUTOVER_GROUP": "true",
    "LLM_EXTRACTION_CUTOVER_LOCATION": "true", "LLM_EXTRACTION_CUTOVER_LOGISTICS": "true",
    "JEV_ROUTER_ENABLED": "true", "AGENT_ARCH": "true", "RAG_MIN_SCORE": "0.40",
    "NOTES_IN_PARALLEL": "false", "ACK_IN_PARALLEL": "false",
    "LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": "",
    "CHATWOOT_API_TOKEN": "", "CHATWOOT_BASE_URL": "http://127.0.0.1:9", "CHATWOOT_API_BASE_URL": "http://127.0.0.1:9",
})

from scripts.run_synthetic_pre import GOLDEN_FILE, load_batches  # noqa: E402
from src.agents import conversational_core as core  # noqa: E402
from src.agents import escalation, supervisor  # noqa: E402
from src.config import settings  # noqa: E402
from src.flows.state import ConversationState  # noqa: E402

FIELDS = ("detected_activity", "is_certified", "location", "detected_location", "hotel", "detected_group_size",
          "detected_group_allocation", "is_colombian", "last_dive_over_2_years", "refresher_interested",
          "core_pending_slot")
RAG_MARK = "«RAG»"


async def _rag(message, **_k):
    return RAG_MARK


async def _noop(*_a, **_k):
    return True


def dialogues():
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    by_tag = {tag: turns for cases in load_batches().values() for tag, turns in cases}
    out = []
    for d in golden["dialogues"]:
        if d.get("suite") == "oculto":
            continue
        turns = d.get("turns") or by_tag.get((d.get("source") or {}).get("tag"))
        if turns:
            out.append((d["id"], [t if isinstance(t, str) else (t.get("text") or t.get("msg") or "") for t in turns]))
    return out


async def replay(did, turns, sem):
    async with sem:
        st = ConversationState(conversation_id=f"u34-{did}")
        rows = []
        for i, msg in enumerate(turns, 1):
            try:
                reply = await supervisor.route_message(st, msg)
            except Exception as exc:  # noqa: BLE001
                reply = f"ERROR {type(exc).__name__}: {exc}"
            snap = {f: getattr(st, f, None) for f in FIELDS}
            rows.append({"id": did, "turn": i, "msg": msg, "reply": reply if isinstance(reply, str) else str(reply),
                         "rag": RAG_MARK in str(reply), "state": json.loads(json.dumps(snap, default=str))})
        return rows


async def main(flag_name: str, side: str, out_dir: Path):
    setattr(settings, flag_name, side == "on")
    supervisor.rag_answer = _rag
    core.compose_acknowledgement = lambda *a, **k: asyncio.sleep(0, result="")
    core.extract_notes = lambda *a, **k: asyncio.sleep(0, result=[])
    escalation.escalate_to_human = _noop
    supervisor.escalate_to_human = _noop
    ds = dialogues()
    sem = asyncio.Semaphore(8)
    res = await asyncio.gather(*(replay(d, t, sem) for d, t in ds))
    rows = [r for rs in res for r in rs]
    name = side
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / f"replay-{side}.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(name, "dialogos", len(ds), "turnos", len(rows), "con RAG", sum(r["rag"] for r in rows),
          "errores", sum(r["reply"].startswith("ERROR") for r in rows))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--flag", required=True, help="nombre del setting booleano a comparar")
    ap.add_argument("--side", choices=["off", "on"], required=True)
    ap.add_argument("--dir", default="u3-4", help="carpeta dentro de docs/robustness/")
    a = ap.parse_args()
    asyncio.run(main(a.flag, a.side, Path("docs/robustness") / a.dir))
