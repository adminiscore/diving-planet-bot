import logging

from openai import AsyncOpenAI

from src.config import settings
from src.privacy import redact_pii

logger = logging.getLogger("uvicorn.error")

_REWRITE_PROMPT_ES = (
    "Eres un reescritor de preguntas. Dada una conversacion entre un cliente "
    "y un asesor, reescribe la ULTIMA pregunta del cliente como una pregunta "
    "independiente y completa que pueda entenderse sin el contexto previo. "
    "Si la pregunta ya es autosuficiente, devuelvela sin cambios. "
    "Responde SOLO con la pregunta reescrita, sin prefijos ni explicaciones."
)

_REWRITE_PROMPT_EN = (
    "You are a question rewriter. Given a conversation between a customer "
    "and an advisor, rewrite the customer's LAST question as a standalone, "
    "self-contained question that can be understood without prior context. "
    "If the question is already self-contained, return it unchanged. "
    "Respond ONLY with the rewritten question, no prefixes or explanations."
)


def _should_condense(query: str, history: list[dict] | None) -> bool:
    if not query or not history:
        return False
    if len(query.split()) >= 8:
        return False
    user_msgs = [m for m in history if m.get("role") == "user"]
    return len(user_msgs) >= 2


def _format_history_for_prompt(history: list[dict], lang: str, max_turns: int = 4) -> str:
    customer_label = "Cliente" if lang == "es" else "Customer"
    advisor_label = "Asesor" if lang == "es" else "Advisor"
    lines: list[str] = []
    for msg in history[-max_turns:]:
        content = redact_pii((msg.get("content") or "").strip())
        if not content:
            continue
        role = customer_label if msg.get("role") == "user" else advisor_label
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


async def condense_query(
    query: str,
    history: list[dict] | None = None,
    lang: str = "es",
) -> str:
    if not _should_condense(query, history):
        return query

    system = _REWRITE_PROMPT_ES if lang == "es" else _REWRITE_PROMPT_EN
    history_block = _format_history_for_prompt(history or [], lang=lang)
    safe_query = redact_pii(query)

    if lang == "es":
        user_content = (
            f"Conversacion previa:\n{history_block}\n\n"
            f"Pregunta a reescribir: {safe_query}"
        )
    else:
        user_content = (
            f"Prior conversation:\n{history_block}\n\n"
            f"Question to rewrite: {safe_query}"
        )

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=80,
        )
        rewritten = (response.choices[0].message.content or "").strip()
        if not rewritten:
            return query
        logger.info(
            f"[RAG][REWRITE] original={safe_query[:40]}... rewritten={rewritten[:60]}..."
        )
        return rewritten
    except Exception as exc:
        logger.warning(f"[RAG][REWRITE] failed, using original query: {exc}")
        return query
