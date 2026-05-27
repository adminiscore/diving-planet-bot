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


def load_knowledge_base() -> list[dict]:
    """Convert JSON knowledge base files into documents for embedding."""
    documents = []

    # --- Services ---
    with open(DATA_DIR / "services.json", "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    for key, svc in data.get("services", {}).items():
        # Spanish document
        text_es = (
            f"Servicio: {svc.get('name_es', key)}\n"
            f"Categoría: {svc.get('category', '')}\n"
            f"Requiere certificación: {'Sí' if svc.get('requires_certification') else 'No'}\n"
        )
        if svc.get("price_usd"):
            text_es += f"Precio (online): ${svc['price_usd']} USD\n"
        if svc.get("price_note"):
            text_es += f"Nota de precio: {svc['price_note']}\n"
        if svc.get("duration_days"):
            text_es += f"Duración: {svc['duration_days']} día(s)\n"
        if svc.get("url"):
            text_es += f"URL: {svc['url']}\n"

        if svc.get("price_usd_normal"):
            text_es += f"Precio normal (sin descuento): ${svc['price_usd_normal']} USD\n"
        if svc.get("price_cop"):
            text_es += f"Precio en pesos (online): ${svc['price_cop']:,} COP\n"
        if svc.get("price_cop_normal"):
            text_es += f"Precio en pesos (normal): ${svc['price_cop_normal']:,} COP\n"

        documents.append({
            "content": text_es.strip(),
            "metadata": {"source": "services", "key": key, "lang": "es"},
        })

        # English document
        text_en = (
            f"Service: {svc.get('name_en', key)}\n"
            f"Category: {svc.get('category', '')}\n"
            f"Requires certification: {'Yes' if svc.get('requires_certification') else 'No'}\n"
        )
        if svc.get("price_usd"):
            text_en += f"Price (online): ${svc['price_usd']} USD\n"
        if svc.get("price_usd_normal"):
            text_en += f"Price (regular): ${svc['price_usd_normal']} USD\n"
        if svc.get("price_cop"):
            text_en += f"Price in COP (online): ${svc['price_cop']:,} COP\n"
        if svc.get("price_cop_normal"):
            text_en += f"Price in COP (regular): ${svc['price_cop_normal']:,} COP\n"
        if svc.get("price_note"):
            text_en += f"Price note: {svc['price_note']}\n"
        if svc.get("duration_days"):
            text_en += f"Duration: {svc['duration_days']} day(s)\n"
        if svc.get("url"):
            text_en += f"URL: {svc['url']}\n"

        documents.append({
            "content": text_en.strip(),
            "metadata": {"source": "services", "key": key, "lang": "en"},
        })

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
