import logging

from openai import AsyncOpenAI

from src.config import settings
from src.privacy import redact_pii

logger = logging.getLogger("uvicorn.error")

_REWRITE_PROMPT_ES = (
    "Eres un reescritor de consultas. Dada una conversacion entre un cliente "
    "y un asesor, reescribe el ULTIMO mensaje del cliente como una consulta "
    "independiente y completa que pueda entenderse sin el contexto previo. "
    "El ultimo mensaje del cliente puede ser una PREGUNTA o una RESPUESTA corta "
    "a lo que pregunto el asesor (por ejemplo, decir en que hotel se hospeda). "
    "En ese caso, combina la intencion previa del cliente con su respuesta para "
    "formar la consulta completa. Ejemplo: si el asesor pregunto por recogida y "
    "el cliente responde 'en el hotel Pao Pao', reescribe como '¿Me recogen en "
    "el hotel Pao Pao?'. Conserva nombres propios (hoteles, islas) tal cual. "
    "Si el mensaje ya es autosuficiente, devuelvelo sin cambios. "
    "Responde SOLO con la consulta reescrita, sin prefijos ni explicaciones."
)

_REWRITE_PROMPT_EN = (
    "You are a query rewriter. Given a conversation between a customer and an "
    "advisor, rewrite the customer's LAST message as a standalone, self-contained "
    "query that can be understood without prior context. The customer's last "
    "message may be a QUESTION or a short ANSWER to what the advisor asked (for "
    "example, naming the hotel where they are staying). In that case, combine the "
    "customer's earlier intent with their answer to form the complete query. "
    "Example: if the advisor asked about pickup and the customer replies 'at the "
    "Pao Pao hotel', rewrite as 'Do you pick me up at the Pao Pao hotel?'. Keep "
    "proper names (hotels, islands) exactly. If the message is already "
    "self-contained, return it unchanged. Respond ONLY with the rewritten query, "
    "no prefixes or explanations."
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
