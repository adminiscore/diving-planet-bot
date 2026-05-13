import json
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


TOPIC_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("pricing", re.compile(r"\b(precio|precios|valor|cu[aá]nto cuesta|usd|d[oó]lares|pesos|cop)\b", re.IGNORECASE)),
    ("availability", re.compile(r"\b(disponibilidad|cupos|hay cupo|available|availability|tomorrow|ma[nñ]ana)\b", re.IGNORECASE)),
    ("meeting_point", re.compile(r"\b(punto de encuentro|muelle|bodeguita|gate|puerta|marina|todo mar)\b", re.IGNORECASE)),
    ("schedule", re.compile(r"\b(horario|hora|itinerario|schedule|duraci[oó]n|duration|regreso|return)\b", re.IGNORECASE)),
    ("certification", re.compile(r"\b(certificaci[oó]n|certificado|open water|advanced|rescue|padi|ssi|logbook)\b", re.IGNORECASE)),
    ("location_islands", re.compile(r"\b(isla|islas|rosario|isla grande|cocoliso|majagua|mulata|hotel)\b", re.IGNORECASE)),
    ("discount_colombian", re.compile(r"\b(colombian|colombiano|colombiana|residente|descuento)\b", re.IGNORECASE)),
    ("payment", re.compile(r"\b(pago|pagar|transferencia|qr|bancolombia|tarjeta|credit|pasarela|link de pago)\b", re.IGNORECASE)),
    ("forms_waiver", re.compile(r"\b(formulario|exoneraci[oó]n|jotform|carn[eé]|carne|certification photo|foto)\b", re.IGNORECASE)),
    ("equipment", re.compile(r"\b(equipo|equipment|incluye|include|insurance|seguro)\b", re.IGNORECASE)),
    ("weather_cancellation", re.compile(r"\b(clima|weather|cancelaci[oó]n|reembolso|refund|pol[ií]tica)\b", re.IGNORECASE)),
    ("photos_media", re.compile(r"\b(foto|fotos|photos|video|videos)\b", re.IGNORECASE)),
    ("seasickness", re.compile(r"\b(mareo|sea sick|seasick|tabletas|pills)\b", re.IGNORECASE)),
]


WASAP_DIR = Path(__file__).parent.parent / "wasap"
CONVERSATIONS_PATH = Path(__file__).parent.parent / "data" / "knowledge_base" / "conversations.json"


CHAT_LINE_RE = re.compile(
    r"^\[(?P<date>\d{1,2}/\d{1,2}/\d{2}),\s*(?P<time>[^\]]+)\]\s*(?P<sender>[^:]+):\s*(?P<text>.*)$"
)

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
LONG_DIGITS_RE = re.compile(r"\b\d{6,}\b")


@dataclass
class ParsedMessage:
    sender: str
    text: str


@dataclass(frozen=True)
class Turn:
    customer: str | None
    diving_planet: str | None


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"[^a-z0-9_]+", "", value)
    return value[:80].strip("_") or "chat"


def sanitize_text(text: str) -> str:
    text = text.replace("\u200e", "").replace("\u200f", "")
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = LONG_DIGITS_RE.sub("[REDACTED_NUMBER]", text)
    return text.strip()


def is_noise_message(sender: str, text: str) -> bool:
    lowered = text.lower().strip()

    if "cifrados de extremo a extremo" in lowered:
        return True

    if lowered.endswith("es un contacto."):
        return True

    if "<adjunto:" in lowered:
        return True

    if lowered.startswith("llamada"):
        return True

    if not lowered:
        return True

    return False


def parse_chat_file(path: Path) -> list[ParsedMessage]:
    messages: list[ParsedMessage] = []
    current: ParsedMessage | None = None

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.rstrip("\n")
        match = CHAT_LINE_RE.match(line)
        if match:
            sender = match.group("sender").strip()
            text = match.group("text")
            text = sanitize_text(text)

            if is_noise_message(sender, text):
                current = None
                continue

            current = ParsedMessage(sender=sender, text=text)
            messages.append(current)
            continue

        if current is not None:
            continuation = sanitize_text(line)
            if continuation:
                current.text = (current.text + "\n" + continuation).strip()

    return messages


def guess_lang(customer_messages: list[str]) -> str:
    hay_en = sum(
        1
        for msg in customer_messages
        for kw in (
            "hi",
            "hello",
            "price",
            "available",
            "booking",
            "thanks",
            "tomorrow",
            "dive",
            "snorkel",
        )
        if kw in msg.lower()
    )
    hay_es = sum(
        1
        for msg in customer_messages
        for kw in (
            "hola",
            "precio",
            "disponibilidad",
            "mañana",
            "reserva",
            "gracias",
            "buceo",
            "snorkel",
        )
        if kw in msg.lower()
    )

    if hay_en > hay_es:
        return "en"
    return "es"


def extract_topics(texts: list[str]) -> list[str]:
    joined = "\n".join(texts)
    topics: list[str] = []
    for name, pattern in TOPIC_PATTERNS:
        if pattern.search(joined):
            topics.append(name)
    return topics


def build_turns(parsed: list[ParsedMessage]) -> list[Turn]:
    turns: list[Turn] = []
    pending_customer: str | None = None

    for m in parsed:
        if "DIVING PLANET" in m.sender.upper():
            if pending_customer is None and turns and turns[-1].diving_planet is None:
                turns[-1] = Turn(customer=turns[-1].customer, diving_planet=m.text)
                continue

            if pending_customer is not None:
                turns.append(Turn(customer=pending_customer, diving_planet=m.text))
                pending_customer = None
            else:
                turns.append(Turn(customer=None, diving_planet=m.text))
        else:
            if pending_customer is None:
                pending_customer = m.text
            else:
                pending_customer = (pending_customer + "\n" + m.text).strip()

    if pending_customer is not None:
        turns.append(Turn(customer=pending_customer, diving_planet=None))

    return turns


def segment_turns_by_topic(turns: list[Turn]) -> list[list[Turn]]:
    if not turns:
        return []

    scored: list[tuple[Turn, str]] = []
    for turn in turns:
        texts = [t for t in (turn.customer, turn.diving_planet) if t]
        topics = extract_topics(texts)
        primary = topics[0] if topics else "general"
        scored.append((turn, primary))

    segments: list[list[Turn]] = []
    current: list[Turn] = []
    current_topic = scored[0][1]

    for turn, topic in scored:
        if current and (topic != current_topic) and len(segments) < 2:
            segments.append(current)
            current = []
            current_topic = topic

        current.append(turn)

        if len(current) >= 10 and len(segments) < 2:
            segments.append(current)
            current = []

    if current:
        segments.append(current)

    if len(segments) > 3:
        segments = segments[:3]

    return segments


def build_conversation_examples(chat_path: Path, parsed: list[ParsedMessage]) -> list[dict]:
    if not parsed:
        return []

    folder_hash = hashlib.sha1(chat_path.parent.name.encode("utf-8", "replace")).hexdigest()[:10]
    folder_slug = f"chat_{folder_hash}"
    first_customer_msg = next((m.text for m in parsed if "DIVING PLANET" not in m.sender.upper()), "")

    turns = build_turns(parsed)
    segments = segment_turns_by_topic(turns)
    if not segments:
        return []

    all_customer_msgs = [t.customer for t in turns if t.customer]
    lang = guess_lang([m for m in all_customer_msgs if m])

    examples: list[dict] = []
    for idx, seg in enumerate(segments, 1):
        customer_msgs = [t.customer for t in seg if t.customer]
        dp_msgs = [t.diving_planet for t in seg if t.diving_planet]

        customer_msgs = [m for m in customer_msgs if m][:15]
        dp_msgs = [m for m in dp_msgs if m][:15]
        if not customer_msgs or not dp_msgs:
            continue

        topics = extract_topics(customer_msgs + dp_msgs)
        scenario = "Importada de WhatsApp. "
        if idx == 1 and first_customer_msg:
            scenario += f"Primer mensaje del cliente: {first_customer_msg[:160]}"
        if topics:
            scenario += (" | Temas: " + ", ".join(topics))

        examples.append({
            "id": f"whatsapp_import_{folder_slug}_part{idx}",
            "lang": lang,
            "scenario": scenario,
            "customer": {"messages": customer_msgs},
            "diving_planet": {"messages": dp_msgs},
            "privacy_note": "Importado desde WhatsApp con anonimización básica (teléfonos/emails/números largos).",
            "extracted_topics": topics,
        })

    return examples


def main() -> int:
    chat_files = sorted(WASAP_DIR.glob("**/_chat.txt"))
    if not chat_files:
        raise SystemExit(f"No se encontraron _chat.txt en {WASAP_DIR}")

    if CONVERSATIONS_PATH.exists():
        data = json.loads(CONVERSATIONS_PATH.read_text(encoding="utf-8"))
    else:
        data = {"conversation_examples": []}

    examples: list[dict] = list(data.get("conversation_examples", []))
    existing_ids = {ex.get("id") for ex in examples if isinstance(ex, dict)}

    added = 0
    skipped = 0

    for chat_path in chat_files:
        parsed = parse_chat_file(chat_path)
        new_examples = build_conversation_examples(chat_path, parsed)
        if not new_examples:
            skipped += 1
            continue

        for example in new_examples:
            if example["id"] in existing_ids:
                suffix = hashlib.sha1(str(chat_path).encode("utf-8", "replace")).hexdigest()[:8]
                example["id"] = f"{example['id']}_{suffix}"
            examples.append(example)
            existing_ids.add(example["id"])
            added += 1

    data["conversation_examples"] = examples

    if CONVERSATIONS_PATH.exists():
        backup_path = CONVERSATIONS_PATH.with_suffix(".json.bak")
        backup_path.write_text(CONVERSATIONS_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    CONVERSATIONS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"WhatsApp import: added={added} skipped={skipped} total={len(examples)}")
    print(f"Updated: {CONVERSATIONS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
