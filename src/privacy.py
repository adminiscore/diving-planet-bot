import re

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

# Any long-ish digit sequence often includes IDs, account numbers, booking refs, etc.
LONG_DIGITS_RE = re.compile(r"\b\d{6,}\b")

# Basic credit card-like patterns (13-19 digits with optional separators)
CARD_NUMBER_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

# Common Spanish keywords that often precede sensitive info
SENSITIVE_KEYWORDS_RE = re.compile(
    r"\b(c[eé]dula|cedula|dni|pasaporte|passport|tarjeta|card|cuenta|account|iban|swift|bancolombia|nequi|daviplata)\b",
    re.IGNORECASE,
)


def detect_pii(text: str) -> list[str]:
    hits: list[str] = []
    if not text:
        return hits

    if EMAIL_RE.search(text):
        hits.append("email")
    if PHONE_RE.search(text):
        hits.append("phone")

    if CARD_NUMBER_RE.search(text) and SENSITIVE_KEYWORDS_RE.search(text):
        hits.append("payment_card")

    if LONG_DIGITS_RE.search(text) and SENSITIVE_KEYWORDS_RE.search(text):
        hits.append("id_or_account")

    return hits


def redact_pii(text: str) -> str:
    if not text:
        return text

    redacted = text
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
    redacted = PHONE_RE.sub("[REDACTED_PHONE]", redacted)

    if SENSITIVE_KEYWORDS_RE.search(redacted):
        redacted = CARD_NUMBER_RE.sub("[REDACTED_CARD]", redacted)
        redacted = LONG_DIGITS_RE.sub("[REDACTED_NUMBER]", redacted)

    # Keep URLs: they can be useful (booking links). No redaction here.
    _ = URL_RE

    return redacted


def privacy_block_message(lang: str = "es") -> str:
    if lang == "en":
        return (
            "For your privacy and security, please don't share personal or payment data (ID numbers, bank accounts, card numbers) here.\n"
            "If you need help with a reservation or payment, I can connect you with an advisor."
        )

    return (
        "Por tu privacidad y seguridad, por favor no compartas datos personales o de pago por este chat (cédulas, cuentas, tarjetas).\n"
        "Si necesitas ayuda con una reserva o pago, puedo conectarte con un asesor."
    )
