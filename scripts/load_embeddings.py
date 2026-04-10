"""
Load knowledge base JSON files into pgvector as embeddings.

Usage:
    python -m scripts.load_embeddings

Requires OPENAI_API_KEY in .env for generating embeddings.
"""

import json
import asyncio
import logging
from pathlib import Path

import asyncpg
from openai import OpenAI

from src.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "knowledge_base"
EMBEDDING_MODEL = settings.openai_embedding_model  # text-embedding-3-small
EMBEDDING_DIM = 1536


def load_knowledge_base() -> list[dict]:
    """Convert JSON knowledge base files into documents for embedding."""
    documents = []

    # --- Services ---
    with open(DATA_DIR / "services.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    for key, svc in data.get("services", {}).items():
        # Spanish document
        text_es = (
            f"Servicio: {svc.get('name_es', key)}\n"
            f"Categoría: {svc.get('category', '')}\n"
            f"Requiere certificación: {'Sí' if svc.get('requires_certification') else 'No'}\n"
        )
        if svc.get("price_usd"):
            text_es += f"Precio: ${svc['price_usd']} USD\n"
        if svc.get("price_note"):
            text_es += f"Nota de precio: {svc['price_note']}\n"
        if svc.get("duration_days"):
            text_es += f"Duración: {svc['duration_days']} día(s)\n"
        if svc.get("url"):
            text_es += f"URL: {svc['url']}\n"

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
            text_en += f"Price: ${svc['price_usd']} USD\n"
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
    with open(DATA_DIR / "faqs.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    for i, faq in enumerate(data.get("faqs", [])):
        documents.append({
            "content": f"Pregunta: {faq['question_es']}\nRespuesta: {faq['answer_es']}",
            "metadata": {"source": "faqs", "index": i, "lang": "es"},
        })
        documents.append({
            "content": f"Question: {faq['question_en']}\nAnswer: {faq['answer_en']}",
            "metadata": {"source": "faqs", "index": i, "lang": "en"},
        })

    # --- Policies ---
    with open(DATA_DIR / "policies.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    for key, policy in data.get("policies", {}).items():
        policy_name = key.replace("_", " ").title()
        documents.append({
            "content": f"Política - {policy_name}: {policy['es']}",
            "metadata": {"source": "policies", "key": key, "lang": "es"},
        })
        documents.append({
            "content": f"Policy - {policy_name}: {policy['en']}",
            "metadata": {"source": "policies", "key": key, "lang": "en"},
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
