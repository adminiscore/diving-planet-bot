"""
RAG Agent for knowledge base retrieval.

Uses pgvector embeddings to answer questions about Diving Planet
services, policies, and FAQs that fall outside the predefined
decision tree.
"""

import logging

from openai import AsyncOpenAI

from src.config import settings
from src.knowledge.vector_store import search_knowledge_base

logger = logging.getLogger("uvicorn.error")

SYSTEM_PROMPT_ES = """Eres el asistente virtual de Diving Planet, el primer centro de buceo PADI 5 Estrellas de Colombia, ubicado en Cartagena.

Reglas:
- Responde SOLO con la información del contexto proporcionado.
- Si no encuentras la respuesta en el contexto, di que no tienes esa información y ofrece contactar a un asesor (WhatsApp: +57 320 2301515).
- Sé conciso, amable y profesional.
- No inventes precios, horarios ni políticas.
- Usa formato de WhatsApp (*negrita*, _cursiva_) cuando sea útil.
- Responde en español."""

SYSTEM_PROMPT_EN = """You are the virtual assistant for Diving Planet, Colombia's first PADI 5 Star Dive Center, located in Cartagena.

Rules:
- Answer ONLY using the provided context information.
- If you can't find the answer in the context, say you don't have that information and offer to connect with an advisor (WhatsApp: +57 320 2301515).
- Be concise, friendly, and professional.
- Do not make up prices, schedules, or policies.
- Use WhatsApp formatting (*bold*, _italic_) when useful.
- Answer in English."""


async def rag_answer(query: str, lang: str = "es", history: list[dict] | None = None) -> str:
    """
    Retrieve relevant context from the knowledge base and generate
    an answer using the LLM.

    Args:
        query: The user's question.
        lang: Language for the response.
        history: Previous messages for conversational context.

    Returns:
        The LLM-generated answer grounded in retrieved documents.
    """
    # Retrieve relevant documents
    docs = await search_knowledge_base(query, lang=lang, top_k=4)

    if not docs:
        if lang == "es":
            return (
                "No encontré información sobre eso en mi base de datos. "
                "¿Quieres que te conecte con un asesor?\n"
                "WhatsApp: +57 320 2301515"
            )
        return (
            "I couldn't find information about that in my database. "
            "Would you like me to connect you with an advisor?\n"
            "WhatsApp: +57 320 2301515"
        )

    # Build context from retrieved docs
    context_parts = []
    for i, doc in enumerate(docs, 1):
        context_parts.append(f"[{i}] {doc['content']}")
    context = "\n\n".join(context_parts)

    # Build messages for the LLM
    system_prompt = SYSTEM_PROMPT_ES if lang == "es" else SYSTEM_PROMPT_EN
    messages = [{"role": "system", "content": system_prompt}]

    # Add conversation history (last 6 messages max)
    if history:
        for msg in history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({
        "role": "user",
        "content": f"Contexto:\n{context}\n\nPregunta del cliente: {query}",
    })

    # Call LLM
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        temperature=0.3,
        max_tokens=500,
    )

    answer = response.choices[0].message.content
    logger.info(f"[RAG] Query: {query[:60]}... | Docs: {len(docs)} | Tokens: {response.usage.total_tokens}")
    return answer
