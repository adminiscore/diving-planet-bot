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

# Un numero con separadores de miles ("2.215.000", "1,429,000"): todos los grupos tras el primero
# son de 3 cifras. Un telefono nunca tiene esa forma (3-3-4, +57 ...): es un importe... o una cedula
# escrita con puntos ("1.023.456.789"). Ronda A del paso 5 (27-sep): "Con tarjeta de crédito son
# los mismos 2.215.000?" recibia el bloqueo de privacidad por "telefono", y los precios en COP del
# historial llegaban al LLM como [REDACTED_PHONE].
_GROUPED_NUMBER_RE = re.compile(r"\d{1,3}([.,])\d{3}(?:\1\d{3})*")
# Solo documento y cuenta, sin "tarjeta"/"card": una tarjeta no se escribe en grupos de 3, y "¿con
# tarjeta son los mismos 2.215.000?" es una pregunta de precio.
_ID_KEYWORDS_RE = re.compile(
    r"\b(c[eé]dula|dni|pasaporte|passport|cuenta|account|iban|swift|bancolombia|nequi|daviplata)\b",
    re.IGNORECASE,
)
_GROUPED_ID_MIN_DIGITS = 7


def _phone_matches(text: str) -> list[re.Match]:
    return [m for m in PHONE_RE.finditer(text) if not _GROUPED_NUMBER_RE.fullmatch(m.group(0))]


def _grouped_id_matches(text: str) -> list[re.Match]:
    """Numeros agrupados largos junto a una palabra de documento o cuenta (cedula con puntos)."""
    if not _ID_KEYWORDS_RE.search(text):
        return []
    return [
        m for m in _GROUPED_NUMBER_RE.finditer(text)
        if sum(ch.isdigit() for ch in m.group(0)) >= _GROUPED_ID_MIN_DIGITS
    ]


def detect_pii(text: str) -> list[str]:
    hits: list[str] = []
    if not text:
        return hits

    if EMAIL_RE.search(text):
        hits.append("email")
    if _phone_matches(text):
        hits.append("phone")

    if CARD_NUMBER_RE.search(text) and SENSITIVE_KEYWORDS_RE.search(text):
        hits.append("payment_card")

    if (LONG_DIGITS_RE.search(text) and SENSITIVE_KEYWORDS_RE.search(text)) or _grouped_id_matches(text):
        hits.append("id_or_account")

    return hits


def _replace_matches(text: str, matches: list[re.Match], label: str) -> str:
    for m in reversed(matches):
        text = text[: m.start()] + label + text[m.end():]
    return text


def redact_pii(text: str) -> str:
    if not text:
        return text

    redacted = text
    redacted = EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)
    redacted = _replace_matches(redacted, _phone_matches(redacted), "[REDACTED_PHONE]")
    redacted = _replace_matches(redacted, _grouped_id_matches(redacted), "[REDACTED_NUMBER]")

    if SENSITIVE_KEYWORDS_RE.search(redacted):
        redacted = CARD_NUMBER_RE.sub("[REDACTED_CARD]", redacted)
        redacted = LONG_DIGITS_RE.sub("[REDACTED_NUMBER]", redacted)

    # Keep URLs: they can be useful (booking links). No redaction here.
    _ = URL_RE

    return redacted


def redact_pii_por_lineas(text: str) -> str:
    """`redact_pii` línea a línea, para textos largos que juntan muchas fuentes (el contexto del juez: catálogo,
    FAQs, historial). La regla "hay una palabra de documento → tapo todos los números largos" solo tiene sentido
    dentro de un mismo mensaje: sobre el texto entero, "pasaporte" en una FAQ tapaba los precios del catálogo."""
    if not text:
        return text
    return "\n".join(redact_pii(linea) for linea in text.split("\n"))


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
