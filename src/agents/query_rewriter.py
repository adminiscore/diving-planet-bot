import logging

from openai import AsyncOpenAI

from src.config import settings
from src.privacy import redact_pii
from src.prompts.info import QUERY_REWRITE_EN, QUERY_REWRITE_ES

logger = logging.getLogger("uvicorn.error")


def _should_condense(query: str, history: list[dict] | None) -> bool:
    if not query or not history:
        return False
    if len(query.split()) >= 8:
        return False
    # A single prior user turn is enough to condense a follow-up — a 2-turn
    # conversation (1 Q + 1 follow-up) only has 1 user message in history.
    user_msgs = [m for m in history if m.get("role") == "user"]
    return len(user_msgs) >= 1


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

    system = QUERY_REWRITE_ES if lang == "es" else QUERY_REWRITE_EN
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
