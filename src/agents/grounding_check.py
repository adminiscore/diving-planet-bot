import logging
import re

from openai import AsyncOpenAI

from src.config import settings
from src.llm_client import trace_openai
from src.privacy import redact_pii
from src.prompts.info import GROUNDING_VERIFY_EN, GROUNDING_VERIFY_ES

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


# People nouns a capacity claim can attach to (ES + EN).
_PEOPLE_NOUN = (
    r"(?:personas?|buzos?|buceadoras?|buceadores?|pasajeros?|cupos?|plazas?|"
    r"people|divers?|persons?|pax|guests?)"
)

# A capacity/limit trigger right before "<N> <people>", or a max word right after
# it. These assert HOW MANY PEOPLE FIT — routinely hallucinated for the private
# tour, whose real KB says only "cotizacion personalizada segun el grupo" (no
# number). Plain echoes of the customer's own headcount ("para 4 personas",
# "somos 4 personas") have no trigger word and are NOT matched.
_CAP_BEFORE = (
    r"(?:hasta|m[aá]x(?:imo)?|capacidad|cupo|aforo|l[ií]mite|cabe[n]?|admite[n]?|"
    r"up\s+to|maximum|max|capacity|holds?|fits?|accommodates?)"
)
_CAP_AFTER = r"(?:m[aá]x(?:imo)?|maximum|max)"
_CAPACITY_CLAIM = re.compile(
    r"(?:" + _CAP_BEFORE + r")\s+(?:de\s+|para\s+|of\s+|up\s+to\s+)?(\d[\d.,]*)\s*" + _PEOPLE_NOUN
    + r"|(\d[\d.,]*)\s*" + _PEOPLE_NOUN + r"\s+(?:como\s+)?" + _CAP_AFTER,
    re.IGNORECASE,
)


def _capacity_claim_numbers(text: str) -> set[str]:
    numbers: set[str] = set()
    for match in _CAPACITY_CLAIM.finditer(text or ""):
        raw = match.group(1) or match.group(2)
        if raw:
            numbers |= _number_variants(raw)
    return numbers


def capacity_claims_grounded(answer: str, context: str) -> bool:
    """Reject answers that assert a maximum people-capacity number not present in
    the context (e.g. "el tour privado admite hasta 12 personas" when the KB only
    says "cotizacion segun el grupo"). Complements the LLM judge, which follows
    the no-invented-capacity rule only intermittently at temperature 0.3. Plain
    headcount echoes without a max/limit trigger are ignored.
    """
    if not answer:
        return True
    answer_caps = _capacity_claim_numbers(answer)
    if not answer_caps:
        return True
    return answer_caps.issubset(_capacity_claim_numbers(context))


# --------------------------------------------------------------------------- #
# Personal-data collection guard
#
# The bot must NEVER run a manual booking process in chat ("send me full names,
# ID/passport numbers and the date to book you in"). Bookings close with the
# online booking link or a human-advisor handoff; the official form/advisor
# collects personal data. The LLM occasionally improvises that advisor ritual
# (seen live on PRE, 2026-07-09) despite the system-prompt rule, so this is a
# deterministic backstop: reject answers that REQUEST identity data.
#
# Requesting = a request verb near an identity-data noun. Merely DESCRIBING a
# form ("el formulario pide tus datos") or telling the customer to WhatsApp the
# advisor with their info does not match.
# --------------------------------------------------------------------------- #

_PD_REQUEST_VERB = (
    r"(?:necesit(?:o|are|aria)\s+que\s+me|me\s+(?:confirm[ae]s|env[ií][ae]s|compart[ae]s|indi(?:que|ca)s|di(?:ga|ce)s|pas[ae]s|facilit[ae]s)|"
    r"envíame|enviame|compárteme|comparteme|indícame|indicame|pásame|pasame|"
    r"por\s+favor\s+(?:envia|envía|comparte|indica|confirma)|"
    r"(?:i\s+(?:will\s+)?need|please\s+(?:share|send|provide|confirm)|send\s+me|share\s+with\s+me|provide\s+(?:me\s+)?(?:with\s+)?your)"
    r")"
)
_PD_IDENTITY_NOUN = (
    r"(?:nombres?\s+(?:y\s+apellidos?|completos?)|apellidos?|"
    r"n[uú]mero\s+de\s+(?:identificaci[oó]n|documento|c[eé]dula|pasaporte)|"
    r"c[eé]dula|pasaporte|documento\s+de\s+identidad|"
    r"fecha\s+de\s+nacimiento|"
    r"full\s+names?|passport|id\s+number|identification\s+number|date\s+of\s+birth)"
)
# Request verb followed by an identity noun within a short window (same clause).
_PD_REQUEST = re.compile(
    _PD_REQUEST_VERB + r"[^.!?\n]{0,120}?" + _PD_IDENTITY_NOUN,
    re.IGNORECASE,
)
# Numbered-list ritual: a line that is basically "1. Nombres y apellidos ..." /
# "2. Numero de identificacion ..." (the live-PRE failure shape), regardless of
# where the request verb sits.
_PD_LIST_ITEM = re.compile(
    r"(?:^|\n)\s*(?:\d+[.)]|[-*•])\s*\**\s*" + _PD_IDENTITY_NOUN,
    re.IGNORECASE,
)


def requests_personal_data(answer: str) -> bool:
    """True if the answer asks the customer to hand over identity data in chat."""
    if not answer:
        return False
    return bool(_PD_REQUEST.search(answer) or _PD_LIST_ITEM.search(answer))


# --------------------------------------------------------------------------- #
# Phone-number guard
#
# The bot must NEVER hand the customer a phone/WhatsApp number (owner decision,
# 2026-07-20) — advisor contact is handled internally via the Chatwoot handoff,
# not by giving the number. The number lives in many KB FAQs the LLM might
# surface, so a system-prompt rule alone isn't watertight; this is the
# deterministic backstop (same pattern as urls_grounded / requests_personal_data).
#
# Matches: +57 320 231515, 320 231515, 320231515, 3202315151, +573202315151,
# and generic long digit runs that read as a phone (7+ digits, possibly grouped).
# Deliberately does NOT match prices ("288.000", "$178"), years ("2026"),
# quantities, times ("4:30"), or percentages.
# --------------------------------------------------------------------------- #
_PHONE_PATTERN = re.compile(
    r"(?:\+?57[\s.\-]?)?(?:\(?3\d{2}\)?[\s.\-]?)\d{3}[\s.\-]?\d{4}"   # Colombian mobile 3xx xxx xxxx
    r"|(?:\+?57[\s.\-]?)?3\d{2}[\s.\-]?\d{2}[\s.\-]?\d{4}"           # 3xx xx xxxx grouping (231515 style)
    r"|\+\d[\d\s.\-]{7,}\d"                                           # any + international run
    r"|\b\d{3}[\s.\-]\d{3}[\s.\-]?\d{3,4}\b",                          # generic grouped 3-3-3/4
    re.IGNORECASE,
)
# "WhatsApp" / "escríbenos al" cue right before a shorter digit run also counts.
_PHONE_CUE = re.compile(
    r"(?:whats\s?app|wpp|tel[eé]fono|phone|ll[aá]ma\w*|escr[ií]benos\s+al)\D{0,12}\d[\d\s.\-]{5,}\d",
    re.IGNORECASE,
)


def contains_phone_number(answer: str) -> bool:
    """True if the answer emits a phone/WhatsApp number to the customer."""
    if not answer:
        return False
    return bool(_PHONE_PATTERN.search(answer) or _PHONE_CUE.search(answer))


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


async def is_grounded(answer: str, context: str, lang: str = "es") -> tuple[bool, str]:
    if not answer.strip() or not context.strip():
        return False, "empty_answer_or_context"

    system = GROUNDING_VERIFY_ES if lang == "es" else GROUNDING_VERIFY_EN
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
        client = trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
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
