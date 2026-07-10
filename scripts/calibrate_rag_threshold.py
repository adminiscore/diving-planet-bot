"""Calibrate RAG_MIN_SCORE on a labeled eval set instead of guessing it.

Why this exists
---------------
A raw cosine score is NOT calibrated: its absolute value depends on the
embedding model and on how long the query is versus the document. With
`text-embedding-3-small`, a short customer question against a long FAQ lands
around 0.45-0.55 *even when the match is perfect*. So a hand-picked absolute
threshold (we shipped 0.50 on PRE) silently discards correct answers.

The industry-standard way to pick it is to measure, not to guess:

1. Build a labeled eval set.
   - Positives: realistic customer phrasings, each labeled with the FAQ that
     answers it (the "gold" document). We generate these synthetically from the
     KB itself with an LLM ("synthetic query generation"), which is the usual
     technique when you have documents but no query logs.
   - Negatives: plausible questions the KB genuinely cannot answer. The bot
     SHOULD fall back on these.
2. Retrieve once per query, then sweep the threshold offline and score it as a
   binary decision ("does this query get trustworthy context?").
3. Read the precision/recall curve and pick the operating point that matches the
   business cost of each error:
   - false negative -> unnecessary "I'll pass you to an advisor" (lost sale)
   - false positive -> answer built on irrelevant context (hallucination risk)

Note this threshold is only a *coarse* gate: the deterministic guards
(prices/URLs/capacity) and the grounding judge run downstream, so a permissive
threshold is the safer trade-off here — a dropped document can never be
recovered, but a marginal one still has to survive the judge.

Usage
-----
    python -m scripts.calibrate_rag_threshold --generate     # build eval set (LLM, costs a little)
    python -m scripts.calibrate_rag_threshold                # sweep + report

Re-run `--generate` whenever the KB or the embedding model changes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from pathlib import Path

from openai import AsyncOpenAI

from src.config import settings

EVAL_SET_PATH = Path(__file__).parent.parent / "docs" / "rag-eval-set.json"
FAQS_PATH = Path(__file__).parent.parent / "data" / "knowledge_base" / "faqs.json"

# Plausible customer questions the KB genuinely cannot answer. Retrieving
# "confident" context for these means the bot would answer from irrelevant
# documents instead of honestly deferring to an advisor.
NEGATIVES: list[tuple[str, str]] = [
    ("es", "cuantos empleados tiene diving planet?"),
    ("es", "quien es el dueno de diving planet?"),
    ("es", "tienen sucursal en medellin?"),
    ("es", "que marca de aletas me recomiendan comprar?"),
    ("es", "cual es la contrasena del wifi de la base?"),
    ("es", "me consigues entradas para el carnaval?"),
    ("es", "cual es la capital de francia?"),
    ("es", "cuanto cuesta un vuelo a cartagena?"),
    ("es", "tienen convenio con avianca?"),
    ("es", "me recomiendas un restaurante en bogota?"),
    ("es", "en que ano se fundo la empresa exactamente?"),
    ("es", "cuantos instructores trabajan hoy?"),
    ("en", "do you sell diving gear?"),
    ("en", "who founded diving planet?"),
    ("en", "can you book my flight?"),
    ("en", "what is the wifi password?"),
]

_GEN_PROMPT = """Eres un generador de consultas de evaluacion para un buscador (RAG) de un centro de buceo.

Para CADA FAQ que te doy, escribe consultas tal y como las escribiria un cliente real por WhatsApp:
- cortas y naturales (3-10 palabras), no copies la pregunta original
- coloquiales, a veces sin tildes ni mayusculas
- que la FAQ dada responda claramente

Devuelve SOLO un JSON valido con esta forma exacta:
{"items": [{"id": <id>, "es": ["consulta1", "consulta2"], "en": ["query1"]}]}

Las "es" en espanol, la "en" en ingles.

FAQs:
"""


async def _generate_eval_set(sample_size: int) -> dict:
    faqs = json.loads(FAQS_PATH.read_text(encoding="utf-8-sig"))["faqs"]
    rng = random.Random(42)  # deterministic sample -> reproducible eval set
    idxs = sorted(rng.sample(range(len(faqs)), min(sample_size, len(faqs))))

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    positives: list[dict] = []

    for start in range(0, len(idxs), 8):
        chunk = idxs[start : start + 8]
        block = "\n".join(
            f'- id {i}: P: {faqs[i]["question_es"]} | R: {faqs[i]["answer_es"][:220]}'
            for i in chunk
        )
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": _GEN_PROMPT + block}],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        for item in data.get("items", []):
            i = int(item["id"])
            if i not in chunk:
                continue
            for q in item.get("es", [])[:2]:
                positives.append({"query": q, "lang": "es", "gold_index": i})
            for q in item.get("en", [])[:1]:
                positives.append({"query": q, "lang": "en", "gold_index": i})
        print(f"  generated for FAQs {chunk[0]}..{chunk[-1]} ({len(positives)} queries so far)")

    eval_set = {
        "embedding_model": settings.openai_embedding_model,
        "note": "gold_index = index into data/knowledge_base/faqs.json['faqs']",
        "positives": positives,
        "negatives": [{"query": q, "lang": lang} for lang, q in NEGATIVES],
    }
    EVAL_SET_PATH.write_text(json.dumps(eval_set, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(positives)} positives + {len(NEGATIVES)} negatives -> {EVAL_SET_PATH}")
    return eval_set


def _is_gold(doc: dict, gold_index: int, lang: str) -> bool:
    m = doc.get("metadata") or {}
    return m.get("source") == "faqs" and m.get("index") == gold_index and m.get("lang") == lang


async def _retrieve_all(eval_set: dict) -> tuple[list[dict], list[dict]]:
    """Retrieve once per query; keep only the per-doc signals the gate uses."""
    from src.knowledge.vector_store import search_knowledge_base

    async def _one(q: str, lang: str, gold_index: int | None):
        docs = await search_knowledge_base(q, lang=lang, top_k=settings.rag_top_k)
        return {
            "query": q,
            "docs": [
                {
                    "vec": float(d.get("score_vector") or 0.0),
                    "bm25": float(d.get("score_bm25_raw") or 0.0),
                    "gold": gold_index is not None and _is_gold(d, gold_index, lang),
                }
                for d in docs
            ],
        }

    pos = []
    for i, p in enumerate(eval_set["positives"], 1):
        pos.append(await _one(p["query"], p["lang"], p["gold_index"]))
        if i % 25 == 0:
            print(f"  retrieved {i}/{len(eval_set['positives'])} positives")
    neg = [await _one(n["query"], n["lang"], None) for n in eval_set["negatives"]]
    return pos, neg


def _confident(doc: dict, min_cosine: float, min_bm25: float) -> bool:
    """Mirror of rag_agent._is_confident: each retrieval branch on its own scale."""
    return doc["vec"] >= min_cosine or doc["bm25"] >= min_bm25


def _sweep(pos: list[dict], neg: list[dict], min_bm25: float) -> None:
    print(f"\nBM25 gate fixed at rag_min_bm25_rank={min_bm25}")
    print(f"Positives: {len(pos)} | Negatives: {len(neg)}\n")
    print(f"{'thresh':>7} {'recall@gold':>12} {'any-ctx(pos)':>13} {'false-ctx(neg)':>15} "
          f"{'precision':>10} {'F1':>7}")
    print("-" * 72)

    rows = []
    for t in [round(0.30 + 0.025 * i, 3) for i in range(0, 15)]:
        gold_hits = sum(
            1 for q in pos if any(d["gold"] and _confident(d, t, min_bm25) for d in q["docs"])
        )
        any_pos = sum(1 for q in pos if any(_confident(d, t, min_bm25) for d in q["docs"]))
        false_neg_ctx = sum(1 for q in neg if any(_confident(d, t, min_bm25) for d in q["docs"]))

        recall = gold_hits / len(pos)
        fp_rate = false_neg_ctx / len(neg) if neg else 0.0
        # Precision of the "this query has trustworthy context" decision.
        precision = gold_hits / (gold_hits + false_neg_ctx) if (gold_hits + false_neg_ctx) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        rows.append((t, recall, f1))
        print(f"{t:>7.3f} {recall:>11.1%} {any_pos/len(pos):>12.1%} {fp_rate:>14.1%} "
              f"{precision:>9.1%} {f1:>7.3f}")

    best = max(rows, key=lambda r: r[2])
    print(f"\nBest F1 at threshold {best[0]:.3f} (recall@gold {best[1]:.1%}, F1 {best[2]:.3f})")
    print(f"Current code default: {settings.rag_min_score}")


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--generate", action="store_true", help="(re)build the eval set with an LLM")
    ap.add_argument("--sample", type=int, default=45, help="how many FAQs to sample when generating")
    args = ap.parse_args()

    if args.generate:
        eval_set = await _generate_eval_set(args.sample)
    else:
        if not EVAL_SET_PATH.exists():
            raise SystemExit(f"No eval set at {EVAL_SET_PATH}. Run with --generate first.")
        eval_set = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))

    print("\nRetrieving (one pass; the sweep is then done offline)...")
    pos, neg = await _retrieve_all(eval_set)
    _sweep(pos, neg, settings.rag_min_bm25_rank)


if __name__ == "__main__":
    asyncio.run(main())
