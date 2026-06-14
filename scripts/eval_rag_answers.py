import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from src.agents.rag_agent import FALLBACK_EN, FALLBACK_ES, rag_answer


CASES = [
    {
        "id": "es_meeting_point",
        "lang": "es",
        "category": "meeting_point_schedule",
        "query": "¿Dónde es el punto de encuentro?",
        "expected_mode": "answer",
    },
    {
        "id": "es_gate_bodeguita",
        "lang": "es",
        "category": "meeting_point_schedule",
        "query": "¿Es en el muelle de la Bodeguita? ¿Qué puerta?",
        "expected_mode": "answer",
    },
    {
        "id": "es_schedule_return",
        "lang": "es",
        "category": "meeting_point_schedule",
        "query": "¿A qué hora es el encuentro y a qué hora regresamos?",
        "expected_mode": "answer",
    },
    {
        "id": "es_food",
        "lang": "es",
        "category": "food",
        "query": "¿Qué comida incluye el tour?",
        "expected_mode": "answer",
    },
    {
        "id": "es_vegetarian",
        "lang": "es",
        "category": "food",
        "query": "Soy vegetariana, ¿qué hay para comer?",
        "expected_mode": "answer",
    },
    {
        "id": "es_allergy",
        "lang": "es",
        "category": "food",
        "query": "Tengo alergia al marisco, ¿hay problema?",
        "expected_mode": "answer",
    },
    {
        "id": "es_photos",
        "lang": "es",
        "category": "media",
        "query": "¿Hacen fotos durante la inmersión?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_videos",
        "lang": "es",
        "category": "media",
        "query": "¿Graban video bajo el agua?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_price_2_dives_usd",
        "lang": "es",
        "category": "pricing",
        "query": "¿Cuánto cuesta el plan de 2 buceos en USD?",
        "expected_mode": "answer",
    },
    {
        "id": "es_price_local_cop",
        "lang": "es",
        "category": "pricing",
        "query": "¿Cuánto cuesta en pesos para colombianos?",
        "expected_mode": "answer",
    },
    {
        "id": "es_discount_code",
        "lang": "es",
        "category": "pricing",
        "query": "¿El 10% de descuento necesita código?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_snorkel_price_included",
        "lang": "es",
        "category": "pricing_included",
        "query": "¿Cuánto cuesta snorkeling y qué incluye?",
        "expected_mode": "answer",
    },
    {
        "id": "es_booking_process",
        "lang": "es",
        "category": "booking_payment",
        "query": "¿Cómo reservo?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_payment_transfer_qr",
        "lang": "es",
        "category": "booking_payment",
        "query": "¿Puedo pagar por transferencia o QR?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_waiver_form",
        "lang": "es",
        "category": "forms",
        "query": "¿Qué formulario tengo que llenar para bucear certificado?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_card_photo",
        "lang": "es",
        "category": "forms",
        "query": "¿Necesitan foto del carné de certificación?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_weather_cancel",
        "lang": "es",
        "category": "weather_policy",
        "query": "¿Qué pasa si se cancela por clima? ¿Hay reembolso o cambio de fecha?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_reschedule",
        "lang": "es",
        "category": "weather_policy",
        "query": "Si no puedo viajar, ¿puedo mover la fecha?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_refresher",
        "lang": "es",
        "category": "certification",
        "query": "Hace años no buceo, ¿necesito refresher?",
        "expected_mode": "answer",
    },
    {
        "id": "es_max_depth",
        "lang": "es",
        "category": "certification",
        "query": "¿Qué profundidad máxima se bucea normalmente?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_open_water_from_islands",
        "lang": "es",
        "category": "courses_location",
        "query": "¿Cómo es el Curso Básico PADI Open Water si ya estoy en las Islas del Rosario?",
        "expected_mode": "answer",
    },
    {
        "id": "es_open_water_followup_islands",
        "lang": "es",
        "category": "followup_rewrite",
        "query": "¿y si ya estoy en las islas?",
        "history": [
            {"role": "user", "content": "¿Cómo es el Curso Básico PADI Open Water?"},
            {"role": "assistant", "content": "Te cuento cómo funciona el curso."}
        ],
        "expected_mode": "answer",
    },
    {
        "id": "es_hotel_pickup_pao_pao",
        "lang": "es",
        "category": "islands_pickup",
        "query": "Hotel Pao Pao recogida?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_pickup_extra_cost_island",
        "lang": "es",
        "category": "islands_pickup",
        "query": "¿La recogida en lancha tiene algún costo extra?",
        "extra_context": "El cliente ya está en las Islas del Rosario. Se hospeda en Isla Grande. Pregunta por logística desde hotel en isla.",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_accommodation_included",
        "lang": "es",
        "category": "accommodation",
        "query": "¿El alojamiento está incluido?",
        "expected_mode": "answer",
    },
    {
        "id": "es_isla_grande_from_there",
        "lang": "es",
        "category": "accommodation",
        "query": "Si me quedo en Isla Grande, ¿puedo bucear saliendo desde allá?",
        "expected_mode": "answer",
    },
    {
        "id": "es_ambiguous_pao_pao",
        "lang": "es",
        "category": "ambiguous_location",
        "query": "Pao Pao",
        "expected_mode": "clarify",
    },
    {
        "id": "es_ambiguous_cocoliso",
        "lang": "es",
        "category": "ambiguous_location",
        "query": "Cocoliso",
        "expected_mode": "clarify",
    },
    {
        "id": "es_ambiguous_san_pedro",
        "lang": "es",
        "category": "ambiguous_location",
        "query": "San Pedro de Majagua",
        "expected_mode": "clarify",
    },
    {
        "id": "es_baru",
        "lang": "es",
        "category": "misc_ops",
        "query": "¿También van a Barú?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_private_service",
        "lang": "es",
        "category": "misc_ops",
        "query": "¿Pueden organizar un servicio privado para mi grupo?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_closed_christmas",
        "lang": "es",
        "category": "misc_ops",
        "query": "¿Abren el 25 de diciembre?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "es_new_year",
        "lang": "es",
        "category": "misc_ops",
        "query": "¿Salen el 1 de enero?",
        "expected_mode": "answer_or_fallback",
    },
    {
        "id": "en_meeting_point",
        "lang": "en",
        "category": "meeting_point_schedule",
        "query": "Where is the meeting point?",
        "expected_mode": "answer",
    },
    {
        "id": "en_price_2_dives",
        "lang": "en",
        "category": "pricing",
        "query": "How much is the 2 dives 1 day plan in USD?",
        "expected_mode": "answer",
    },
    {
        "id": "en_refresher",
        "lang": "en",
        "category": "certification",
        "query": "I haven't dived in years, do I need a refresher?",
        "expected_mode": "answer",
    },
    {
        "id": "en_accommodation",
        "lang": "en",
        "category": "accommodation",
        "query": "Is accommodation included?",
        "expected_mode": "answer",
    },
    {
        "id": "en_followup_islands",
        "lang": "en",
        "category": "followup_rewrite",
        "query": "and if I'm already on the islands?",
        "history": [
            {"role": "user", "content": "How does the PADI Open Water course work?"},
            {"role": "assistant", "content": "I can explain the course structure."}
        ],
        "expected_mode": "answer",
    },
    {
        "id": "en_ambiguous_pao_pao",
        "lang": "en",
        "category": "ambiguous_location",
        "query": "Pao Pao",
        "expected_mode": "clarify",
    },
]


def _pick_cases(lang: str) -> list[dict]:
    if lang == "all":
        return CASES
    return [case for case in CASES if case["lang"] == lang]


def _response_mode(answer: str, lang: str) -> str:
    fallback = FALLBACK_ES if lang == "es" else FALLBACK_EN
    normalized = (answer or "").strip()
    if normalized == fallback.strip():
        return "fallback"
    if lang == "es" and normalized.startswith("¿Te refieres a "):
        return "clarify"
    if lang == "en" and normalized.startswith("Do you mean "):
        return "clarify"
    return "answer"


def _matches_expected_mode(actual_mode: str, expected_mode: str | None) -> bool:
    if expected_mode == "answer_or_fallback":
        return actual_mode in {"answer", "fallback"}
    return actual_mode == expected_mode


async def _run_case(case: dict) -> dict:
    answer = await rag_answer(
        case["query"],
        lang=case["lang"],
        history=case.get("history"),
        extra_context=case.get("extra_context"),
    )
    mode = _response_mode(answer, case["lang"])
    return {
        "id": case["id"],
        "lang": case["lang"],
        "category": case["category"],
        "query": case["query"],
        "expected_mode": case.get("expected_mode"),
        "actual_mode": mode,
        "history": case.get("history"),
        "extra_context": case.get("extra_context"),
        "answer": answer,
        "matches_expected_mode": _matches_expected_mode(mode, case.get("expected_mode")),
    }


async def main_async(lang: str, output_json: str | None) -> int:
    cases = _pick_cases(lang)
    results = []

    for index, case in enumerate(cases, 1):
        print("=" * 120)
        print(f"[{index}/{len(cases)}] {case['id']} | {case['category']} | {case['lang']}")
        print(f"QUERY: {case['query']}")
        if case.get("history"):
            print(f"HISTORY_TURNS: {len(case['history'])}")
        if case.get("extra_context"):
            print("EXTRA_CONTEXT: yes")
        result = await _run_case(case)
        print(f"EXPECTED_MODE: {result['expected_mode']}")
        print(f"ACTUAL_MODE: {result['actual_mode']}")
        print(f"MATCHES_EXPECTATION: {result['matches_expected_mode']}")
        print("ANSWER_START")
        print(result["answer"])
        print("ANSWER_END")
        results.append(result)

    if output_json:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "lang": lang,
            "total_cases": len(results),
            "results": results,
        }
        output_path = Path(output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print("=" * 120)
        print(f"WROTE_JSON: {output_path}")

    answers = sum(1 for result in results if result["actual_mode"] == "answer")
    fallbacks = sum(1 for result in results if result["actual_mode"] == "fallback")
    clarifications = sum(1 for result in results if result["actual_mode"] == "clarify")
    expected_matches = sum(1 for result in results if result["matches_expected_mode"])

    print("=" * 120)
    print(f"SUMMARY cases={len(results)} answers={answers} fallbacks={fallbacks} clarifications={clarifications} expectation_matches={expected_matches}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a repeatable baseline of final RAG answers.")
    parser.add_argument("--lang", choices=["es", "en", "all"], default="all")
    parser.add_argument("--output-json", type=str, default=None)
    args = parser.parse_args()
    return asyncio.run(main_async(args.lang, args.output_json))


if __name__ == "__main__":
    raise SystemExit(main())
