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
- Si la respuesta no está en el contexto o hay duda, dilo y ofrece: "Te paso con un asesor para que te ayude".
- Nunca inventes precios, horarios, disponibilidad, códigos de descuento, links de pago ni confirmaciones de reserva.
- Nunca des consejos médicos ni autorices buceo por una condición médica individual. Deriva a asesor para esos casos.
- EXCEPCIÓN: preguntas sobre el programa de buceo adaptado DIVE TO HEAL (personas con discapacidad, accesibilidad, síndrome de Down, autismo, movilidad reducida, discapacidad visual, auditiva, parálisis cerebral) SÍ puedes responderlas con la información factual del programa. Es información pública del centro, no consejo médico personal.
- Nunca pidas ni repitas datos sensibles (IDs, cuentas, comprobantes de pago, números de tarjeta).
- No escribas respuestas largas tipo folleto si el cliente hizo una pregunta concreta.

Cuándo derivar siempre a humano:
- Intención de reservar o pagar.
- Preguntas de disponibilidad real.
- Diagnóstico médico personal o solicitud de autorización para bucear por condición de salud.
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
- Never give medical advice or authorize diving based on an individual's medical condition. Always refer to an advisor for those cases.
- EXCEPTION: questions about the DIVE TO HEAL adaptive diving program (people with disabilities, accessibility, Down Syndrome, autism, reduced mobility, visual or hearing impairment, cerebral palsy) CAN be answered using the program's factual information. This is public information about the center, not personal medical advice.
- Never request or repeat sensitive data (IDs, accounts, payment receipts, card numbers).
- Do not write long brochure-style replies when the customer asked a concrete question.

Always escalate to a human for:
- Booking or payment intent.
- Real availability questions.
- Personal medical diagnosis or requests to authorize diving based on a health condition.
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
    """Retrieve context from the knowledge base and answer using the LLM.

    Comportamiento en orden de prioridad:
    - Si hay documentos relevantes por encima del umbral -> usar esos docs como contexto principal.
    - Si NO hay docs o la confianza es baja PERO hay ``extra_context`` (por ejemplo, un
      resumen del estado de la conversacion) -> responder usando SOLO ese contexto
      adicional y el historial.
    - Si no hay ni docs ni ``extra_context`` util -> devolver el fallback seguro.
    """
    pii_hits = detect_pii(query)
    if pii_hits:
        logger.warning(f"[RAG][PRIVACY] PII detected in query hits={pii_hits}")
        return privacy_block_message(lang)

    retrieval_query = build_retrieval_query(query, history)
    safe_query = redact_pii(retrieval_query)

    # Retrieve relevant documents
    docs = await search_knowledge_base(safe_query, lang=lang)

    # Helper to call the LLM with unstructured context (either KB docs o solo extra_context)
    async def _answer_with_llm(context: str, context_sources: list[str] | None = None) -> str:
        system_prompt = SYSTEM_PROMPT_ES if lang == "es" else SYSTEM_PROMPT_EN
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history (last 6 messages max)
        if history:
            for msg in history[-6:]:
                messages.append({"role": msg["role"], "content": redact_pii(msg["content"])})

        user_content = f"Contexto:\n{context}"
        if extra_context and context != extra_context:
            # Si ya tenemos contexto KB y ademas extra_context, lo anexamos explicito
            user_content += f"\n\nContexto adicional de la situacion: {extra_context}"
        user_content += f"\n\nPregunta del cliente: {redact_pii(query)}"

        messages.append({"role": "user", "content": user_content})

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            temperature=0.3,
            max_tokens=500,
        )

        answer = response.choices[0].message.content
        logger.info(
            f"[RAG] Query: {query[:60]}... | Docs: {len(docs) if docs else 0} | "
            f"Tokens: {response.usage.total_tokens} | Sources: {context_sources or []}"
        )
        return answer

    # 1) Sin documentos del KB
    if not docs:
        logger.info(f"[RAG] No docs found query={query[:60]}...")
        if extra_context:
            # No hay nada util en el KB, pero si tenemos resumen de estado: dejamos que el LLM
            # razone SOLO con ese contexto en lugar de ir directo al fallback.
            return await _answer_with_llm(extra_context, context_sources=["extra_context_only"])
        return FALLBACK_ES if lang == "es" else FALLBACK_EN

    # 2) Hay documentos pero con score bajo
    top_score = max(float(doc.get("score", 0.0)) for doc in docs)
    if top_score < settings.rag_min_score:
        sources = [doc.get("metadata", {}).get("source", "unknown") for doc in docs]
        logger.info(
            f"[RAG] Low confidence query={query[:60]}... retrieval_query={safe_query[:120]}... "
            f"top_score={top_score:.3f} threshold={settings.rag_min_score:.3f} sources={sources}"
        )
        if extra_context:
            # Igual que en el caso sin docs: ignoramos estos resultados de baja confianza
            # y dejamos que el LLM trabaje solo con el contexto de estado.
            return await _answer_with_llm(extra_context, context_sources=["extra_context_only"])
        return FALLBACK_ES if lang == "es" else FALLBACK_EN

    # 3) Hay documentos suficientemente relevantes -> los usamos como contexto principal
    context_parts = []
    sources = []
    for i, doc in enumerate(docs, 1):
        metadata = doc.get("metadata", {})
        source = metadata.get("source", "unknown")
        score = float(doc.get("score", 0.0))
        sources.append(source)
        context_parts.append(f"[{i}] Fuente: {source} | Score: {score:.3f}\n{redact_pii(doc['content'])}")
    context = "\n\n".join(context_parts)

    return await _answer_with_llm(context, context_sources=sources)
