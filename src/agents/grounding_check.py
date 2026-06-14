import logging

from openai import AsyncOpenAI

from src.config import settings
from src.privacy import redact_pii

logger = logging.getLogger("uvicorn.error")

_VERIFY_PROMPT_ES = """Verifica si la RESPUESTA esta totalmente basada en el CONTEXTO proporcionado.

Reglas:
- \"GROUNDED\" si cada afirmacion factual de la respuesta aparece literalmente o se infiere directamente del contexto.
- \"HALLUCINATED\" si la respuesta incluye cualquier dato factual que no este en el contexto.
- Frases de cortesia, ofrecimientos genericos y reformulaciones del contexto son aceptables.

Responde con UNA palabra: GROUNDED o HALLUCINATED."""

_VERIFY_PROMPT_EN = """Verify whether the RESPONSE is fully based on the provided CONTEXT.

Rules:
- \"GROUNDED\" if every factual claim in the response appears literally or is directly inferable from the context.
- \"HALLUCINATED\" if the response includes any factual data not present in the context.
- Politeness, generic offers and rewordings of the context are acceptable.

Reply with ONE word: GROUNDED or HALLUCINATED."""


async def is_grounded(answer: str, context: str, lang: str = "es") -> tuple[bool, str]:
    if not answer.strip() or not context.strip():
        return False, "empty_answer_or_context"

    system = _VERIFY_PROMPT_ES if lang == "es" else _VERIFY_PROMPT_EN
    if lang == "es":
        user_content = (
            f"CONTEXTO:\n{redact_pii(context)}\n\n"
            f"RESPUESTA:\n{redact_pii(answer)}"
        )
    else:
        user_content = (
            f"CONTEXT:\n{redact_pii(context)}\n\n"
            f"RESPONSE:\n{redact_pii(answer)}"
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
            max_tokens=30,
        )
        verdict = (response.choices[0].message.content or "").strip().upper()
        grounded = verdict.startswith("GROUNDED")
        reason = verdict if verdict else "empty_verdict"
        logger.info(f"[RAG][GROUNDING] grounded={grounded} verdict={reason}")
        return grounded, reason
    except Exception as exc:
        logger.warning(f"[RAG][GROUNDING] failed, allowing answer: {exc}")
        return True, f"check_failed:{type(exc).__name__}"
