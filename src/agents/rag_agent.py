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
