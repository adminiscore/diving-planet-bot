import argparse
import asyncio
import json
from datetime import datetime

from src.knowledge.vector_store import detect_query_topics, search_knowledge_base


DEFAULT_QUERIES_ES = [
    "¿Dónde es el punto de encuentro?",
    "¿Es en el muelle de la Bodeguita? ¿Qué puerta?",
    "¿A qué hora es el encuentro y a qué hora regresamos?",
    "¿Qué debo llevar? (toalla, bloqueador, etc.)",
    "¿Cuánto cuesta el plan de 2 buceos en USD?",
    "¿Cuánto cuesta en pesos para colombianos?",
    "¿El 10% de descuento necesita código?",
    "¿Cuánto cuesta snorkeling y qué incluye?",
    "¿Cómo reservo?",
    "¿Puedo pagar por transferencia o QR?",
    "¿Qué formulario tengo que llenar para bucear certificado?",
    "¿Necesitan foto del carné de certificación?",
    "¿Qué pasa si se cancela por clima? ¿Hay reembolso o cambio de fecha?",
    "Si no puedo viajar, ¿puedo mover la fecha?",
    "Tengo Open Water, ¿qué plan me recomiendas?",
    "Hace años no buceo, ¿necesito refresher?",
    "¿Qué profundidad máxima se bucea normalmente?",
    "¿Desde qué hotel operan en las islas?",
    "¿El alojamiento está incluido?",
    "Si me quedo en Isla Grande, ¿puedo bucear saliendo desde allá?",
]

DEFAULT_QUERIES_EN = [
    "Where is the meeting point?",
    "Is it at Muelle de la Bodeguita? Which gate?",
    "What time do we meet and what time do we return?",
    "What should I bring? (towel, sunscreen, etc.)",
    "How much is the 2 dives 1 day plan in USD?",
    "Do Colombians get a local price?",
    "Do I need a discount code for the 10% discount?",
    "How much is snorkeling and what is included?",
    "How do I book?",
    "Can I pay by bank transfer or QR?",
    "Which form do I need to fill out as a certified diver?",
    "Do you need a photo of my certification card?",
    "What happens if the trip is canceled due to weather? Is there a refund or date change?",
    "If I can't travel, can I change the date?",
    "I have Open Water, which plan do you recommend?",
    "I haven't dived in years, do I need a refresher?",
    "What is the usual maximum depth?",
    "Which hotels are your dive bases on the islands?",
    "Is accommodation included?",
    "If I'm already staying on Isla Grande, can I dive from there?",
]


def _pick_queries(lang: str) -> list[str]:
    if lang == "en":
        return DEFAULT_QUERIES_EN
    return DEFAULT_QUERIES_ES


async def eval_queries(lang: str, top_k: int, candidate_multiplier: int, output_json: str | None) -> int:
    queries = _pick_queries(lang)

    results_out: list[dict] = []

    for idx, q in enumerate(queries, 1):
        query_topics = detect_query_topics(q)
        docs = await search_knowledge_base(q, lang=lang, top_k=top_k)

        print("=" * 110)
        print(f"[{idx}/{len(queries)}] {q}")
        print(f"query_topics={query_topics}")

        for i, d in enumerate(docs, 1):
            md = d.get("metadata") or {}
            print(
                f"  {i}. source={md.get('source')} id={md.get('id')} key={md.get('key')} "
                f"score={d.get('score'):.4f} boosted={d.get('score_boosted', d.get('score')):.4f} topics={md.get('topics')}"
            )

        results_out.append({
            "query": q,
            "lang": lang,
            "query_topics": query_topics,
            "top_k": top_k,
            "docs": [
                {
                    "score": d.get("score"),
                    "score_boosted": d.get("score_boosted", d.get("score")),
                    "content_preview": (d.get("content") or "")[:240],
                    "metadata": d.get("metadata") or {},
                }
                for d in docs
            ],
        })

    if output_json:
        payload = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "lang": lang,
            "top_k": top_k,
            "results": results_out,
        }
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print("=" * 110)
        print(f"Wrote report: {output_json}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline-ish retrieval evaluation (prints top docs per query).")
    parser.add_argument("--lang", choices=["es", "en"], default="es")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--output-json", type=str, default=None)

    args = parser.parse_args()

    return asyncio.run(eval_queries(args.lang, args.top_k, candidate_multiplier=6, output_json=args.output_json))


if __name__ == "__main__":
    raise SystemExit(main())
