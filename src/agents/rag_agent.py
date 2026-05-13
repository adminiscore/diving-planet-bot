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
from src.privacy import detect_pii, privacy_block_message, redact_pii

logger = logging.getLogger("uvicorn.error")

FALLBACK_ES = (
    "No tengo información suficiente en mi base de conocimiento para responder eso con seguridad. "
    "Te puedo conectar con un asesor de Diving Planet.\n"
    "WhatsApp: +57 320 2301515"
)

FALLBACK_EN = (
    "I don't have enough information in my knowledge base to answer that safely. "
    "I can connect you with a Diving Planet advisor.\n"
    "WhatsApp: +57 320 2301515"
)

SYSTEM_PROMPT_ES = """Eres el asistente especializado de Diving Planet, el primer centro de buceo PADI 5 Estrellas de Colombia con 30 años de experiencia en las Islas del Rosario, Cartagena.

Estilo y tono:
- Cercano, confiable, profesional pero amigable. Suenas como un asesor real hablando por WhatsApp: amable, rápido, informal-profesional y orientado a resolver.
- Usa frases cortas y naturales. Separa información compleja en bloques pequeños.
- Usa expresiones como "Perfecto", "Claro", "Estamos aquí para ayudarte".
- Usa emojis marinos o de acción con moderación, no en cada frase.
- Cierra siempre con una pregunta útil o un siguiente paso claro.
- Adapta el lenguaje para clientes de todas las edades, incluyendo 60+.

Reglas estrictas — nunca las incumplas:
- Responde SOLO con la información del contexto proporcionado.
- Si la respuesta no está en el contexto o hay duda, dilo y ofrece: "Para esta situación específica, prefiero transferirte con mi jefe".
- Nunca inventes precios, horarios, disponibilidad, códigos de descuento, links de pago ni confirmaciones de reserva.
- Nunca des consejos médicos ni autorices buceo por condición médica. Siempre deriva a un asesor.
- Nunca pidas ni repitas datos sensibles (IDs, cuentas, comprobantes de pago, números de tarjeta).
- No escribas respuestas largas tipo folleto si el cliente hizo una pregunta concreta.

Cuándo derivar siempre a humano:
- Intención de reservar o pagar.
- Preguntas de disponibilidad real.
- Dudas médicas o de seguridad.
- Cancelaciones, cambios o quejas.
- Preguntas con baja confianza o fuera del contexto.

Contacto asesor: WhatsApp +57 320 2301515.
Responde en español."""

SYSTEM_PROMPT_EN = """You are the specialized assistant for Diving Planet, Colombia's first PADI 5 Star Dive Center with 30 years of experience in the Rosario Islands, Cartagena.

Style and tone:
- Approachable, trustworthy, professional but friendly. Sound like a real Diving Planet advisor on WhatsApp: warm, fast, informal-professional, and focused on solving the customer's need.
- Use short and natural sentences. Break complex information into small blocks.
- Use expressions like "Perfect", "Sure", "No worries", "We're here to help".
- Use ocean or action emojis moderately, not in every sentence.
- End with a useful question or clear next step.
- Adapt communication for clients of all ages, including 60+.

Strict rules — never break these:
- Answer ONLY using the provided context.
- If the answer is not in the context or you're unsure, say so and offer: "For this specific situation, I prefer to transfer you to my boss".
- Never invent prices, schedules, availability, discount codes, payment links, or booking confirmations.
- Never give medical advice or authorize diving based on a medical condition. Always refer to an advisor.
- Never request or repeat sensitive data (IDs, accounts, payment receipts, card numbers).
- Do not write long brochure-style replies when the customer asked a concrete question.

Always escalate to a human for:
- Booking or payment intent.
- Real availability questions.
- Medical or safety concerns.
- Cancellations, changes, or complaints.
- Low-confidence answers or questions outside the context.

Advisor contact: WhatsApp +57 320 2301515.
Answer in English."""


def build_retrieval_query(query: str, history: list[dict] | None = None) -> str:
    if not history:
        return query

    recent_user_messages = [
        msg["content"]
        for msg in history[-6:]
        if msg.get("role") == "user" and msg.get("content") != query
    ]
    if not recent_user_messages:
        return query

    return "\n".join([*recent_user_messages[-2:], query])


async def rag_answer(
    query: str,
    lang: str = "es",
    history: list[dict] | None = None,
    extra_context: str | None = None,
) -> str:
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
    pii_hits = detect_pii(query)
    if pii_hits:
        logger.warning(f"[RAG][PRIVACY] PII detected in query hits={pii_hits}")
        return privacy_block_message(lang)

    retrieval_query = build_retrieval_query(query, history)
    safe_query = redact_pii(retrieval_query)

    # Retrieve relevant documents
    docs = await search_knowledge_base(safe_query, lang=lang)

    if not docs:
        logger.info(f"[RAG] No docs found query={query[:60]}...")
        return FALLBACK_ES if lang == "es" else FALLBACK_EN

    top_score = max(float(doc.get("score", 0.0)) for doc in docs)
    if top_score < settings.rag_min_score:
        sources = [doc.get("metadata", {}).get("source", "unknown") for doc in docs]
        logger.info(
            f"[RAG] Low confidence query={query[:60]}... retrieval_query={safe_query[:120]}... "
            f"top_score={top_score:.3f} threshold={settings.rag_min_score:.3f} sources={sources}"
        )
        return FALLBACK_ES if lang == "es" else FALLBACK_EN

    # Build context from retrieved docs
    context_parts = []
    for i, doc in enumerate(docs, 1):
        metadata = doc.get("metadata", {})
        source = metadata.get("source", "unknown")
        score = float(doc.get("score", 0.0))
        context_parts.append(f"[{i}] Fuente: {source} | Score: {score:.3f}\n{redact_pii(doc['content'])}")
    context = "\n\n".join(context_parts)

    # Build messages for the LLM
    system_prompt = SYSTEM_PROMPT_ES if lang == "es" else SYSTEM_PROMPT_EN
    messages = [{"role": "system", "content": system_prompt}]

    # Add conversation history (last 6 messages max)
    if history:
        for msg in history[-6:]:
            messages.append({"role": msg["role"], "content": redact_pii(msg["content"])})

    user_content = f"Contexto:\n{context}"
    if extra_context:
        user_content += f"\n\nContexto adicional de la situacion: {extra_context}"
    user_content += f"\n\nPregunta del cliente: {redact_pii(query)}"

    messages.append({
        "role": "user",
        "content": user_content,
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
    sources = [doc.get("metadata", {}).get("source", "unknown") for doc in docs]
    logger.info(
        f"[RAG] Query: {query[:60]}... | Docs: {len(docs)} | TopScore: {top_score:.3f} | "
        f"Sources: {sources} | Tokens: {response.usage.total_tokens}"
    )
    return answer
