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

SYSTEM_PROMPT_ES = """Eres el asistente especializado de Diving Planet (centro de buceo PADI 5 Estrellas en Cartagena). Tu estilo es cercano, confiable y profesional pero amigable.

Enfoque:
- Tu seguridad es nuestra prioridad. Transmite confianza y claridad.
- Comunicación directa, clara y servicial. Evita jerga técnica excesiva.
- Adapta el lenguaje para clientes de todas las edades (incluyendo 60+).

Reglas:
- Responde SOLO con la información del contexto proporcionado.
- Si la respuesta no está en el contexto o hay duda, dilo explícitamente y ofrece asistencia personalizada: "Para esta situación específica, prefiero transferirte con mi jefe".
- No inventes precios, horarios, políticas ni disponibilidad.
- Si piden o incluyen datos personales/de pago, pide no compartirlos y ofrece conectar con un asesor.
- Usa formato de WhatsApp (*negrita*, _cursiva_) cuando sea útil.

Contacto asesor: WhatsApp +57 320 2301515.
Responde en español."""

SYSTEM_PROMPT_EN = """You are the specialized assistant for Diving Planet (a PADI 5 Star Dive Center in Cartagena). Your tone is approachable, trustworthy, professional but friendly.

Focus:
- Your safety is our priority. Build confidence and be clear.
- Be direct, clear, and helpful. Avoid excessive technical jargon.
- Adapt your communication for clients of all ages (including 60+).

Rules:
- Answer ONLY using the provided context.
- If the answer is not in the context or you're unsure, say so and offer personalized help: "For this specific situation, I prefer to transfer you to my boss".
- Do not make up prices, schedules, policies, or availability.
- If the user asks for or shares personal/payment data, ask them not to share it and offer to connect with an advisor.
- Use WhatsApp formatting (*bold*, _italic*) when useful.

Advisor contact: WhatsApp +57 320 2301515.
Answer in English."""


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

    safe_query = redact_pii(query)

    # Retrieve relevant documents
    docs = await search_knowledge_base(safe_query, lang=lang, top_k=4)

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
        context_parts.append(f"[{i}] {redact_pii(doc['content'])}")
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
    user_content += f"\n\nPregunta del cliente: {safe_query}"

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
    logger.info(f"[RAG] Query: {query[:60]}... | Docs: {len(docs)} | Tokens: {response.usage.total_tokens}")
    return answer
