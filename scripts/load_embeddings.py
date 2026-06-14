"""
Load knowledge base JSON files into pgvector as embeddings.

Usage:
    python -m scripts.load_embeddings

Requires OPENAI_API_KEY in .env for generating embeddings.
"""

import json
import asyncio
import logging
import re
from pathlib import Path

import asyncpg
from openai import OpenAI

from src.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "knowledge_base"
EMBEDDING_MODEL = settings.openai_embedding_model  # text-embedding-3-small
EMBEDDING_DIM = 1536


TOPIC_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("pricing", re.compile(r"\b(precio|precios|valor|cu[aá]nto cuesta|usd|d[oó]lares|pesos|cop)\b", re.IGNORECASE)),
    ("discount", re.compile(r"(?:10%|\bdescuento\b|\bdiscount\b|descuento\s*10|discount\s*10)", re.IGNORECASE)),
    ("availability", re.compile(r"\b(disponibilidad|cupos|hay cupo|available|availability|tomorrow|ma[nñ]ana)\b", re.IGNORECASE)),
    ("booking", re.compile(r"\b(reservar|reserva|reservas|reservo|reservamos|apartar|booking|book|p[aá]gina|web|online)\b", re.IGNORECASE)),
    ("meeting_point", re.compile(r"\b(punto de encuentro|muelle|bodeguita|gate|puerta|marina|todo mar)\b", re.IGNORECASE)),
    ("schedule", re.compile(r"\b(horario|hora|itinerario|schedule|duraci[oó]n|duration|regreso|return)\b", re.IGNORECASE)),
    ("reschedule", re.compile(r"\b(mover la fecha|cambiar la fecha|cambio de fecha|reprogramar|reagendar|move the date|change the date|reschedule)\b", re.IGNORECASE)),
    ("certification", re.compile(r"\b(certificaci[oó]n|certificado|open water|advanced|rescue|padi|ssi|logbook)\b", re.IGNORECASE)),
    ("refresher", re.compile(r"\b(refresh|refresher|refresh requirement|hace a[nñ]os no buceo|hace mucho no buceo|sin bucear|tiempo sin bucear)\b", re.IGNORECASE)),
    ("location_islands", re.compile(r"\b(isla|islas|rosario|isla grande|cocoliso|majagua|mulata|hotel)\b", re.IGNORECASE)),
    ("accommodation", re.compile(r"\b(alojamiento|accommodation|hotel|hospedaje|incluye alojamiento|is accommodation included)\b", re.IGNORECASE)),
    ("discount_colombian", re.compile(r"\b(colombian|colombiano|colombiana|colombianos|colombianas|residente)\b", re.IGNORECASE)),
    ("payment", re.compile(r"\b(pago|pagar|transferencia|qr|bancolombia|tarjeta|credit|pasarela|link de pago)\b", re.IGNORECASE)),
    ("forms_waiver", re.compile(r"\b(formulario|exoneraci[oó]n|jotform|carn[eé]|carne|certification photo|foto)\b", re.IGNORECASE)),
    ("equipment", re.compile(r"\b(equipo|equipment|incluye|include|insurance|seguro|qu[eé]\s+debo\s+llevar|qu[eé]\s+llevar|llevar|traer|bring|towel|toalla|bloqueador|sunscreen)\b", re.IGNORECASE)),
    ("depth", re.compile(r"\b(profundidad|metros|m\b|maxima|max\s+depth|depth)\b", re.IGNORECASE)),
    ("weather_cancellation", re.compile(r"\b(clima|weather|cancelaci[oó]n|reembolso|refund|pol[ií]tica)\b", re.IGNORECASE)),
    ("photos_media", re.compile(r"\b(foto|fotos|photos|video|videos)\b", re.IGNORECASE)),
    ("seasickness", re.compile(r"\b(mareo|sea sick|seasick|tabletas|pills)\b", re.IGNORECASE)),
]


def detect_topics(text: str) -> list[str]:
    topics: list[str] = []
    for name, pattern in TOPIC_PATTERNS:
        if pattern.search(text):
            topics.append(name)
    return topics


def normalize_conversation_topics(raw_topics: list[str] | None) -> list[str]:
    if not raw_topics:
        return []

    topic_map: dict[str, str] = {
        "punto_de_encuentro": "meeting_point",
        "muelle_bodeguita": "meeting_point",
        "cancelacion_reembolso": "weather_cancellation",
        "clima": "weather_cancellation",
        "alojamiento_en_islas": "accommodation",
        "base_en_islas": "accommodation",
        "recogida_en_hotel": "accommodation",
        "proceso_reserva": "booking",
        "corte_reserva_online": "booking",
        "pago": "payment",
        "pago_50_por_ciento": "payment",
        "link_pago": "payment",
        "formulario_exoneracion": "forms_waiver",
        "foto_certificacion": "forms_waiver",
        "precios": "pricing",
        "precios_usd": "pricing",
        "precio_colombianos": "discount_colombian",
        "descuento_10_por_ciento": "discount",
        "disponibilidad_ultima_hora": "availability",
        "ultima_hora": "availability",
        "horarios": "schedule",
        "duracion": "schedule",
        "ubicacion_equipo": "equipment",
        "equipo_incluido": "equipment",
        "incluye": "equipment",
        "refresh": "refresher",
        "refresher": "refresher",
    }

    normalized: list[str] = []
    for t in raw_topics:
        if not t:
            continue
        mapped = topic_map.get(t, t)
        if mapped in topic_map.values() or any(mapped == known for known, _ in TOPIC_PATTERNS):
            normalized.append(mapped)

    deduped = list(dict.fromkeys(normalized))
    return deduped


def _service_subchunks(service_id: str, service: dict, lang: str) -> list[dict]:
    name = service.get(f"name_{lang}", service_id)
    description = service.get(f"description_{lang}", "")
    category = service.get("category", "")
    url = service.get("url", "")
    price_note = service.get("price_note", "")
    duration_days = service.get("duration_days")
    requires_certification = service.get("requires_certification")

    summary_lines = [
        f"Servicio: {name}" if lang == "es" else f"Service: {name}",
        f"Categoría: {category}" if lang == "es" else f"Category: {category}",
        (
            f"Requiere certificación: {'Sí' if requires_certification else 'No'}"
            if lang == "es"
            else f"Requires certification: {'Yes' if requires_certification else 'No'}"
        ),
    ]
    if description:
        summary_lines.append(description)
    if duration_days:
        summary_lines.append(
            f"Duración: {duration_days} día(s)"
            if lang == "es"
            else f"Duration: {duration_days} day(s)"
        )
    if url:
        summary_lines.append(f"URL: {url}")

    summary_key = f"{service_id}:summary"
    chunks: list[dict] = []

    def add_chunk(key: str, content: str, subtype: str) -> None:
        text = content.strip()
        if not text:
            return
        chunks.append({
            "content": text,
            "metadata": {
                "source": "services",
                "key": key,
                "lang": lang,
                "service_id": service_id,
                "subtype": subtype,
                "topics": detect_topics(text),
            },
        })

    add_chunk(summary_key, "\n".join(summary_lines), "summary")

    itinerary = service.get(f"itinerary_{lang}", []) or []
    if itinerary:
        title = f"Itinerario de {name}:" if lang == "es" else f"Itinerary for {name}:"
        add_chunk(
            f"{service_id}:itinerary",
            "\n".join([title, *[f"- {step}" for step in itinerary]]),
            "itinerary",
        )
        chunks[-1]["metadata"]["parent_id"] = summary_key

    included = service.get(f"included_{lang}", []) or []
    not_included = service.get(f"not_included_{lang}", []) or []
    if included or not_included:
        body_lines: list[str] = []
        if included:
            body_lines.append(
                f"Qué incluye {name}:" if lang == "es" else f"What is included in {name}:"
            )
            body_lines.extend(f"- {item}" for item in included)
        if not_included:
            body_lines.append("")
            body_lines.append(
                "Qué NO incluye:" if lang == "es" else "What is NOT included:"
            )
            body_lines.extend(f"- {item}" for item in not_included)
        add_chunk(f"{service_id}:included", "\n".join(body_lines), "included")
        chunks[-1]["metadata"]["parent_id"] = summary_key

    requirements = service.get(f"requirements_{lang}", []) or []
    if requirements:
        title = f"Requisitos para {name}:" if lang == "es" else f"Requirements for {name}:"
        add_chunk(
            f"{service_id}:requirements",
            "\n".join([title, *[f"- {item}" for item in requirements]]),
            "requirements",
        )
        chunks[-1]["metadata"]["parent_id"] = summary_key

    pricing_lines: list[str] = []
    if service.get("price_usd"):
        pricing_lines.append(
            f"Precio online: ${service['price_usd']} USD"
            if lang == "es"
            else f"Online price: ${service['price_usd']} USD"
        )
    if service.get("price_usd_normal"):
        pricing_lines.append(
            f"Precio normal: ${service['price_usd_normal']} USD"
            if lang == "es"
            else f"Regular price: ${service['price_usd_normal']} USD"
        )
    if service.get("price_cop"):
        pricing_lines.append(
            f"Precio en COP online: ${service['price_cop']:,} COP"
            if lang == "es"
            else f"Online price in COP: ${service['price_cop']:,} COP"
        )
    if service.get("price_cop_normal"):
        pricing_lines.append(
            f"Precio en COP normal: ${service['price_cop_normal']:,} COP"
            if lang == "es"
            else f"Regular price in COP: ${service['price_cop_normal']:,} COP"
        )
    if price_note:
        pricing_lines.append(
            f"Nota de precio: {price_note}"
            if lang == "es"
            else f"Price note: {price_note}"
        )
    if pricing_lines:
        title = f"Precios de {name}:" if lang == "es" else f"Pricing for {name}:"
        add_chunk(f"{service_id}:pricing", "\n".join([title, *pricing_lines]), "pricing")
        chunks[-1]["metadata"]["parent_id"] = summary_key

    return chunks


def load_knowledge_base() -> list[dict]:
    """Convert JSON knowledge base files into documents for embedding."""
    documents = []

    # --- Services ---
    with open(DATA_DIR / "services.json", "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    for key, svc in data.get("services", {}).items():
        documents.extend(_service_subchunks(key, svc, "es"))
        documents.extend(_service_subchunks(key, svc, "en"))

    # --- FAQs ---
    with open(DATA_DIR / "faqs.json", "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    for i, faq in enumerate(data.get("faqs", [])):
        topics_es = detect_topics(f"{faq['question_es']}\n{faq['answer_es']}")
        topics_en = detect_topics(f"{faq['question_en']}\n{faq['answer_en']}")
        documents.append({
            "content": f"Pregunta: {faq['question_es']}\nRespuesta: {faq['answer_es']}",
            "metadata": {"source": "faqs", "index": i, "lang": "es", "topics": topics_es},
        })
        documents.append({
            "content": f"Question: {faq['question_en']}\nAnswer: {faq['answer_en']}",
            "metadata": {"source": "faqs", "index": i, "lang": "en", "topics": topics_en},
        })

    # --- Policies ---
    with open(DATA_DIR / "policies.json", "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    for key, policy in data.get("policies", {}).items():
        policy_name = key.replace("_", " ").title()
        topics_es = detect_topics(str(policy.get("es", "")))
        topics_en = detect_topics(str(policy.get("en", "")))
        documents.append({
            "content": f"Política - {policy_name}: {policy['es']}",
            "metadata": {"source": "policies", "key": key, "lang": "es", "topics": topics_es},
        })
        documents.append({
            "content": f"Policy - {policy_name}: {policy['en']}",
            "metadata": {"source": "policies", "key": key, "lang": "en", "topics": topics_en},
        })

    # --- Pricing ---
    pricing_path = DATA_DIR / "pricing.json"
    if pricing_path.exists():
        with open(pricing_path, "r", encoding="utf-8-sig") as f:
            pricing_data = json.load(f)

        year = pricing_data.get("pricing_year", "")
        eq_disc = pricing_data.get("own_equipment_discount_cop", 0)

        def _fmt_entry_es(entry: dict) -> str:
            if entry.get("available") is False:
                return entry.get("note_es", "No disponible")
            parts = []
            if entry.get("cop_online"):
                parts.append(f"${entry['cop_online']:,} COP online / ${entry.get('cop_normal', '?'):,} COP normal")
            if entry.get("usd_online"):
                parts.append(f"${entry['usd_online']} USD online / ${entry.get('usd_normal', '?')} USD normal")
            price = " | ".join(parts) if parts else entry.get("note_es", "consultar")
            note = entry.get("note_es", "")
            return f"{price}" + (f" ({note})" if note and note not in price else "")

        def _fmt_entry_en(entry: dict) -> str:
            if entry.get("available") is False:
                return entry.get("note_en", "Not available")
            parts = []
            if entry.get("cop_online"):
                parts.append(f"COP ${entry['cop_online']:,} online / ${entry.get('cop_normal', '?'):,} normal")
            if entry.get("usd_online"):
                parts.append(f"${entry['usd_online']} USD online / ${entry.get('usd_normal', '?')} USD regular")
            price = " | ".join(parts) if parts else entry.get("note_en", "contact us")
            note = entry.get("note_en", "")
            return f"{price}" + (f" ({note})" if note and note not in price else "")

        section_labels = {
            "servicios_buceo_snorkel": ("Servicios de buceo y snorkel", "Diving and snorkeling services"),
            "paquetes": ("Paquetes multi-día", "Multi-day packages"),
            "cursos_buceo": ("Cursos de buceo", "Diving courses"),
            "cursos_especialidades": ("Especialidades PADI", "PADI specialties"),
        }

        for origin_key, origin_label_es, origin_label_en, ctx_key_es, ctx_key_en in [
            ("from_cartagena", "desde Cartagena", "from Cartagena", "context_note_es", "context_note_en"),
            ("from_islands", "desde las Islas del Rosario", "from the Rosario Islands", "context_note_es", "context_note_en"),
        ]:
            origin = pricing_data.get(origin_key, {})
            ctx_es = origin.get(ctx_key_es, "")
            ctx_en = origin.get(ctx_key_en, "")

            for section_key, (label_es, label_en) in section_labels.items():
                section = origin.get(section_key)
                if not section:
                    continue

                lines_es = [f"Precios {origin_label_es} — {label_es} ({year})", ctx_es, ""]
                lines_en = [f"Prices {origin_label_en} — {label_en} ({year})", ctx_en, ""]

                for svc_key, entry in section.items():
                    if not isinstance(entry, dict):
                        continue
                    name_es = entry.get("name_es", svc_key)
                    name_en = entry.get("name_en", svc_key)
                    lines_es.append(f"- {name_es}: {_fmt_entry_es(entry)}")
                    lines_en.append(f"- {name_en}: {_fmt_entry_en(entry)}")

                lines_es.append(f"\nDescuento equipo propio: ${eq_disc:,} COP por día de buceo.")
                lines_en.append(f"\nOwn equipment discount: COP ${eq_disc:,} per diving day.")

                topics = ["pricing"]
                if "colombian" in section_key or "descuento" in section_key:
                    topics.append("discount_colombian")
                if "curso" in section_key or "especialidad" in section_key:
                    topics.append("certification")

                documents.append({
                    "content": "\n".join(lines_es).strip(),
                    "metadata": {
                        "source": "pricing",
                        "origin": origin_key,
                        "section": section_key,
                        "lang": "es",
                        "topics": topics,
                    },
                })
                documents.append({
                    "content": "\n".join(lines_en).strip(),
                    "metadata": {
                        "source": "pricing",
                        "origin": origin_key,
                        "section": section_key,
                        "lang": "en",
                        "topics": topics,
                    },
                })

        # Discount policies
        disc = pricing_data.get("discount_policies", {})
        if disc:
            lines_es = [f"Políticas de descuento Diving Planet ({year})", ""]
            lines_en = [f"Diving Planet discount policies ({year})", ""]
            for disc_key, disc_entry in disc.items():
                name_es = disc_entry.get("name_es", disc_key)
                name_en = disc_entry.get("name_en", disc_key)
                desc_es = disc_entry.get("description_es", "")
                desc_en = disc_entry.get("description_en", "")
                lines_es.append(f"- {name_es}: {desc_es}")
                lines_en.append(f"- {name_en}: {desc_en}")
            documents.append({
                "content": "\n".join(lines_es).strip(),
                "metadata": {"source": "pricing", "section": "discount_policies", "lang": "es", "topics": ["discount", "discount_colombian", "pricing"]},
            })
            documents.append({
                "content": "\n".join(lines_en).strip(),
                "metadata": {"source": "pricing", "section": "discount_policies", "lang": "en", "topics": ["discount", "discount_colombian", "pricing"]},
            })

    conversations_path = DATA_DIR / "conversations.json"
    if conversations_path.exists():
        with open(conversations_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)

        for i, conv in enumerate(data.get("conversation_examples", [])):
            lang = conv.get("lang", "es")
            scenario = conv.get("scenario", "")
            customer_msgs = (conv.get("customer", {}) or {}).get("messages", [])
            dp_msgs = (conv.get("diving_planet", {}) or {}).get("messages", [])
            topics = normalize_conversation_topics(conv.get("extracted_topics", []))

            content = (
                f"Conversación real (WhatsApp)\n"
                f"Escenario: {scenario}\n\n"
                f"Cliente dice:\n- " + "\n- ".join(customer_msgs) + "\n\n"
                f"Diving Planet responde:\n- " + "\n- ".join(dp_msgs)
            )
            if topics:
                content += "\n\nTemas: " + ", ".join(topics)

            documents.append({
                "content": content.strip(),
                "metadata": {
                    "source": "conversations",
                    "index": i,
                    "id": conv.get("id"),
                    "lang": lang,
                    "topics": topics,
                },
            })

    return documents


def generate_embeddings(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts using OpenAI API."""
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


async def store_documents(documents: list[dict], embeddings: list[list[float]]):
    """Store documents and their embeddings in pgvector."""
    conn = await asyncpg.connect(settings.database_url)

    try:
        # Clear existing documents
        await conn.execute("DELETE FROM kb_documents")
        logger.info("Cleared existing documents")

        # Insert new documents
        for doc, emb in zip(documents, embeddings):
            await conn.execute(
                """
                INSERT INTO kb_documents (content, metadata, embedding)
                VALUES ($1, $2, $3)
                """,
                doc["content"],
                json.dumps(doc["metadata"]),
                str(emb),
            )

        count = await conn.fetchval("SELECT COUNT(*) FROM kb_documents")
        logger.info(f"Stored {count} documents in kb_documents")
    finally:
        await conn.close()


async def main():
    logger.info("Loading knowledge base...")
    documents = load_knowledge_base()
    logger.info(f"Created {len(documents)} documents from knowledge base")

    logger.info(f"Generating embeddings with {EMBEDDING_MODEL}...")
    client = OpenAI(api_key=settings.openai_api_key)

    # Batch embeddings (API supports up to 2048 inputs)
    texts = [doc["content"] for doc in documents]
    embeddings = generate_embeddings(client, texts)
    logger.info(f"Generated {len(embeddings)} embeddings")

    logger.info("Storing in pgvector...")
    await store_documents(documents, embeddings)

    logger.info("Done! Knowledge base loaded into pgvector.")


if __name__ == "__main__":
    asyncio.run(main())
