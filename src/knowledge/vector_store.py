"""
Vector store interface for pgvector-based similarity search.

Retrieves relevant knowledge base documents by embedding the query
and performing cosine similarity search against stored embeddings.
"""

import json
import logging

import asyncpg
from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger("uvicorn.error")


async def search_knowledge_base(
    query: str,
    lang: str = "es",
    top_k: int = 4,
) -> list[dict]:
    """
    Embed the query and return the top_k most similar documents.

    Args:
        query: User's question.
        lang: Filter results by language (es/en).
        top_k: Number of results to return.

    Returns:
        List of dicts with 'content', 'metadata', and 'score'.
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Generate query embedding
    resp = await client.embeddings.create(
        model=settings.openai_embedding_model,
        input=query,
    )
    query_embedding = resp.data[0].embedding

    # Similarity search in pgvector
    conn = await asyncpg.connect(settings.database_url)
    try:
        rows = await conn.fetch(
            """
            SELECT content, metadata, 1 - (embedding <=> $1::vector) AS score
            FROM kb_documents
            WHERE metadata->>'lang' = $2
            ORDER BY embedding <=> $1::vector
            LIMIT $3
            """,
            str(query_embedding),
            lang,
            top_k,
        )
        results = []
        for row in rows:
            results.append({
                "content": row["content"],
                "metadata": json.loads(row["metadata"]),
                "score": float(row["score"]),
            })
        return results
    finally:
        await conn.close()
