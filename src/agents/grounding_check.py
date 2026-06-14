import logging
import re

from openai import AsyncOpenAI

from src.config import settings
from src.privacy import redact_pii

logger = logging.getLogger("uvicorn.error")

# Any digit run, possibly with thousands/decimal separators (e.g. 178, 178.00, 630.000, 1,234.50).
_NUMBER_TOKEN = re.compile(r"\d[\d.,]*")

# Concrete monetary / percentage amounts in an answer that we must be able to
# trace back to the context: "$178", "178 USD", "630.000 COP", "10%".
_ANSWER_AMOUNT = re.compile(
    r"\$\s?\d[\d.,]*"
    r"|\b\d[\d.,]*\s*(?:usd|cop|d[oó]lares|dolares|pesos)\b"
    r"|\b\d[\d.,]*\s*%",
    re.IGNORECASE,
)


def _number_variants(raw: str) -> set[str]:
    """Normalize a number token into comparable variants.

    Handles USD decimal formatting ("178.0" / "178.00") and COP thousands
    separators ("630.000") so an answer's "$178" matches a context
    "178.0 USD" or "178.00 USD".
    """
    digits_only = re.sub(r"[.,\s]", "", raw)
    variants = {digits_only}
    trailing_single_zero_decimal = re.search(r"[.,](0)$", raw)
    if trailing_single_zero_decimal:
        variants.add(re.sub(r"[.,\s]", "", raw[: trailing_single_zero_decimal.start()]))
    trailing_decimals = re.search(r"[.,](\d{2})$", raw)
    if trailing_decimals and trailing_decimals.group(1) == "00":
        variants.add(re.sub(r"[.,\s]", "", raw[: trailing_decimals.start()]))
    return {variant for variant in variants if variant}


def _context_number_set(context: str) -> set[str]:
    numbers: set[str] = set()
    for token in _NUMBER_TOKEN.findall(context):
        numbers |= _number_variants(token)
    return numbers


def currency_amounts_grounded(answer: str, context: str) -> bool:
    """Deterministically verify every monetary/percentage amount in the answer
    appears in the context. Catches invented prices (e.g. "$180" vs "$178")
    without an LLM call. Non-currency numbers (días, metros, teléfono) are ignored.
    """
    if not answer or not context:
        return True
    context_numbers = _context_number_set(context)
    for amount in _ANSWER_AMOUNT.findall(answer):
        core = _NUMBER_TOKEN.search(amount)
        if not core:
            continue
        if not (_number_variants(core.group(0)) & context_numbers):
            return False
    return True


# Explicit links the answer might emit (http(s):// or www.).
_URL_PATTERN = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def _normalize_url(raw: str) -> str:
    return raw.rstrip(").,;:!?\"'>]}").lower()


def urls_grounded(answer: str, context: str) -> bool:
    """Reject answers that emit a link not present in the context.

    Booking/payment links must come from the structured flow, not from the LLM,
    so any URL the model writes must be traceable to the retrieved context.
    """
    if not answer:
        return True
    lowered_context = (context or "").lower()
    for raw_url in _URL_PATTERN.findall(answer):
        url = _normalize_url(raw_url)
        if url and url not in lowered_context:
            return False
    return True


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
