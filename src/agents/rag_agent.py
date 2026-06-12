"""
RAG Agent for knowledge base retrieval.

Uses pgvector embeddings to answer questions about Diving Planet
services, policies, and FAQs that fall outside the predefined
decision tree.
"""

import logging
import re

from openai import AsyncOpenAI

from src.config import settings
from src.knowledge.loader import (
    load_brand_tone,
    load_conversations,
    load_faqs,
    load_policies,
)
from src.knowledge.vector_store import detect_query_topics, search_knowledge_base
from src.privacy import detect_pii, privacy_block_message, redact_pii

logger = logging.getLogger("uvicorn.error")

_BRAND_TONE_CACHE: dict | None = None
_CONVERSATIONS_CACHE: list[dict] | None = None
FEWSHOT_MAX_CHARS = 220


def _load_brand_tone_cached() -> dict:
    """Load and cache brand_tone.json at first access."""
    global _BRAND_TONE_CACHE
    if _BRAND_TONE_CACHE is None:
        _BRAND_TONE_CACHE = (load_brand_tone() or {}).get("brand_tone", {})
    return _BRAND_TONE_CACHE


def _build_tone_section(lang: str) -> str:
    """Compose the Style/Tone bullets dynamically from brand_tone.json.

    Falls back to a minimal hard-coded set if the file is missing or malformed.
    """
    tone = _load_brand_tone_cached()
    bullets: list[str] = []

    personality = (tone.get("personality") or {}).get(lang, "")
    if personality:
        # Capitalize first char only; preserve the rest of the casing (e.g. brand names).
        cap_personality = personality[:1].upper() + personality[1:]
        if lang == "es":
            bullets.append(
                f"- {cap_personality}. Suenas como un asesor real "
                "hablando por WhatsApp: amable, rapido, informal-profesional y orientado a resolver."
            )
        else:
            bullets.append(
                f"- {cap_personality}. Sound like a real Diving Planet advisor on WhatsApp: "
                "warm, fast, informal-professional, and focused on solving the customer's need."
            )

    ws_lang = (tone.get("whatsapp_style") or {}).get(lang) or {}
    for shape in ws_lang.get("message_shape", []):
        bullets.append(f"- {shape}")

    human = ws_lang.get("human_touches", [])
    if human:
        bullets.append(f"- {human[0]}")

    age = (tone.get("age_demographic_consideration") or {}).get(lang, "")
    if age:
        bullets.append(f"- {age}")

    if not bullets:
        # Defensive fallback if brand_tone.json is empty or unreadable.
        if lang == "es":
            return (
                "- Cercano, confiable, profesional pero amigable.\n"
                "- Usa frases cortas y naturales.\n"
                "- Cierra con una pregunta util o un siguiente paso claro."
            )
        return (
            "- Approachable, trustworthy, professional but friendly.\n"
            "- Use short, natural sentences.\n"
            "- End with a useful question or clear next step."
        )

    return "\n".join(bullets)


def _load_conversations_cached() -> list[dict]:
    """Load and cache conversation_examples from conversations.json at first access."""
    global _CONVERSATIONS_CACHE
    if _CONVERSATIONS_CACHE is None:
        _CONVERSATIONS_CACHE = (load_conversations() or {}).get("conversation_examples", []) or []
    return _CONVERSATIONS_CACHE


def _select_fewshot_examples(query: str, lang: str, k: int = 2) -> list[dict]:
    """Pick up to k conversation examples whose extracted_topics overlap with the query topics.

    Returns the raw example dicts (filtered by lang). Empty list if no useful match.
    Uses detect_query_topics() to score overlap; ties broken by example order in JSON.
    """
    if not query:
        return []
    query_topics = set(detect_query_topics(query))
    if not query_topics:
        return []

    candidates = []
    for example in _load_conversations_cached():
        if (example.get("lang") or "").lower() != lang:
            continue
        ex_topics = set(str(t) for t in (example.get("extracted_topics") or []))
        # Translate JSON topic labels (e.g. "precios") into TOPIC_PATTERNS labels (e.g. "pricing")
        # by intersecting against a small alias map. Keep loose: any overlap counts.
        aliases = {
            "precios": "pricing",
            "disponibilidad_ultima_hora": "availability",
            "horarios": "schedule",
            "punto_encuentro": "meeting_point",
            "punto_de_encuentro": "meeting_point",
            "recogida_en_hotel": "location_islands",
            "planes_desde_islas": "location_islands",
            "ubicacion_equipo": "equipment",
            "refresh": "refresher",
            "incluye": "equipment",
            "grupo_mixto": "booking",
            "snorkel": "schedule",
            "ultima_hora": "availability",
        }
        normalized = {aliases.get(t, t) for t in ex_topics}
        overlap = len(query_topics & normalized)
        if overlap > 0:
            candidates.append((overlap, example))

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return [example for _, example in candidates[:k]]


def _format_fewshot_block(examples: list[dict], lang: str) -> str:
    """Render a compact reference block from picked conversation examples.

    Each example is summarised in <= FEWSHOT_MAX_CHARS chars to keep the prompt cheap.
    Framed as 'real situations the center has handled' so the model treats them as
    domain context, not as a template to imitate verbatim.
    """
    if not examples:
        return ""

    header = (
        "Situaciones reales del centro (referencia, NO copies el formato literal):"
        if lang == "es"
        else "Real situations the center has handled (reference, do NOT copy the literal format):"
    )
    lines = [header]
    for ex in examples:
        scenario = (ex.get("scenario") or "").strip()
        first_customer_msg = ""
        customer_msgs = ((ex.get("customer") or {}).get("messages") or [])
        if customer_msgs:
            first_customer_msg = str(customer_msgs[0]).strip()
        first_bot_action = ""
        bot_msgs = ((ex.get("diving_planet") or {}).get("messages") or [])
        if bot_msgs:
            first_bot_action = str(bot_msgs[0]).strip()

        cust_q = f"\"{first_customer_msg[:80]}{'...' if len(first_customer_msg) > 80 else ''}\""
        action = first_bot_action[:120] + ("..." if len(first_bot_action) > 120 else "")
        bullet = f"- {scenario[:60]} | Cliente: {cust_q} | Asesor cubrio: {action}"
        if lang == "en":
            bullet = f"- {scenario[:60]} | Customer: {cust_q} | Advisor covered: {action}"
        # Hard cap per bullet
        if len(bullet) > FEWSHOT_MAX_CHARS:
            bullet = bullet[:FEWSHOT_MAX_CHARS - 3] + "..."
        lines.append(bullet)

    return "\n".join(lines)


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

_INTRO_ES = (
    "Eres el asistente especializado de Diving Planet, el primer centro de buceo PADI 5 Estrellas "
    "de Colombia con 30 años de experiencia en las Islas del Rosario, Cartagena."
)

_INTRO_EN = (
    "You are the specialized assistant for Diving Planet, Colombia's first PADI 5 Star Dive Center "
    "with 30 years of experience in the Rosario Islands, Cartagena."
)

_SYSTEM_PROMPT_ES_BODY = """Reglas estrictas — nunca las incumplas:
- Responde SOLO con la información del contexto proporcionado.
- Si la respuesta no está en el contexto o hay duda, dilo y ofrece: "Te paso con un asesor para que te ayude".
- Nunca inventes precios, horarios, disponibilidad, códigos de descuento, links de pago ni confirmaciones de reserva.
- Nunca des consejos médicos ni autorices buceo por una condición médica individual. Deriva a asesor para esos casos.
- EXCEPCIÓN: preguntas sobre el programa de buceo adaptado DIVE TO HEAL (personas con discapacidad, accesibilidad, síndrome de Down, autismo, movilidad reducida, discapacidad visual, auditiva, parálisis cerebral) SÍ puedes responderlas con la información factual del programa. Es información pública del centro, no consejo médico personal.
- Nunca pidas ni repitas datos sensibles (IDs, cuentas, comprobantes de pago, números de tarjeta).
- No escribas respuestas largas tipo folleto si el cliente hizo una pregunta concreta.
- Cuando el cliente mencione *varias personas con intención de reservar* (ej: "yo X y mi pareja/él/ella Y", "somos 3 y unos quieren snorkel otros buceo"), NO asignes roles persona-actividad ("Para ti…/Para ella…") ni cites precios individuales por persona. Solo describe las actividades disponibles de forma *neutral* (1-2 frases breves) y deriva al asesor para que confirme la composición exacta del grupo y el precio total. El flujo estructurado del bot ya se encarga de armar el carrito con cantidades; tu única labor en este caso es contextualizar brevemente y escalar.

Gestión de precios, monedas y pagos:
- Usa el contexto de extra_context para adaptar la moneda: si se indica que el cliente NO es colombiano/a, prioriza mostrar los precios en USD y no des tarifas detalladas en pesos pensadas para locales; si se indica que SÍ es colombiano/a, puedes usar precios en COP y, si es útil, mencionar el equivalente en USD.
- Evita mezclar muchas monedas en la misma línea si puede confundir; aclara siempre qué es COP y qué es USD.
- Aunque en el contexto aparezcan flujos de pago (formularios, porcentajes como 50%, transferencias, etc.), NO describas el proceso exacto de pago ni montos de anticipo. Explica de forma general que un asesor humano te indicará el paso a paso y el valor del anticipo si aplica.
- No inventes ni reconstruyas links de pago o de formularios. Si el cliente pregunta cómo pagar o cómo completar el formulario de exoneración, di que el asesor le enviará el enlace y las instrucciones concretas.

Uso del contexto de la conversación (extra_context):
- Ten muy en cuenta la actividad que el cliente está organizando, desde dónde sale (Cartagena o ya en las islas) y si se trata de un plan de 1 día o de varios días.
- Cuando el cliente pregunte por amigos o acompañantes que quieran bucear o hacer snorkel, prioriza opciones que mantengan este contexto: mismo origen y, cuando sea posible, misma lógica de duración (plan de 1 día vs paquete multi-día), salvo que el cliente pida explícitamente otra cosa (por ejemplo, que quiere quedarse a dormir en las islas).

Cuándo derivar siempre a humano:
- Intención de reservar o pagar: en estos casos no expliques el flujo de pago detallado, solo da la información básica del plan y aclara que un asesor humano se encargará de confirmar cupos y forma de pago.
- Preguntas de disponibilidad real.
- Diagnóstico médico personal o solicitud de autorización para bucear por condición de salud.
- Cancelaciones, cambios o quejas.
- Preguntas con baja confianza o fuera del contexto.

Contacto asesor: WhatsApp +57 320 2301515.
Responde en español."""

_SYSTEM_PROMPT_EN_BODY = """Strict rules — never break these:
- Answer ONLY using the provided context.
- If the answer is not in the context or you're unsure, say so and offer: "For this specific situation, I prefer to transfer you to my boss".
- Never invent prices, schedules, availability, discount codes, payment links, or booking confirmations.
- Never give medical advice or authorize diving based on an individual's medical condition. Always refer to an advisor for those cases.
- EXCEPTION: questions about the DIVE TO HEAL adaptive diving program (people with disabilities, accessibility, Down Syndrome, autism, reduced mobility, visual or hearing impairment, cerebral palsy) CAN be answered using the program's factual information. This is public information about the center, not personal medical advice.
- Never request or repeat sensitive data (IDs, accounts, payment receipts, card numbers).
- Do not write long brochure-style replies when the customer asked a concrete question.
- When the customer mentions *multiple people with booking intent* (e.g. "I want X and my partner/he/she Y", "we are 3 and some want snorkel others diving"), do NOT assign person-activity roles ("For you…/For her…") nor quote individual per-person prices. Just describe the available activities *neutrally* (1-2 short sentences) and route to the human advisor so they confirm the exact group composition and total price. The bot's structured flow already builds the cart with quantities; your only job in this case is brief context + escalation.

Pricing, currencies, and payments:
- Use the extra_context to adapt currency: if it indicates the customer is NOT Colombian, prioritize giving prices in USD and avoid detailed COP prices meant for local customers; if it indicates they ARE Colombian, feel free to use COP prices and, if helpful, mention the approximate USD equivalent.
- Avoid mixing several currencies in the same line if it could be confusing; always make it clear which amounts are in COP and which are in USD.
- Even if the context contains payment flows (forms, percentages like 50%, bank transfers, etc.), do NOT describe the exact payment process or the amount of any deposit. Explain in general terms that a human advisor will confirm the step-by-step process and any advance payment if applicable.
- Do not invent or reconstruct payment or form links. If the customer asks how to pay or how to complete the waiver form, tell them that the advisor will send the correct link and instructions.

How to use conversation context (extra_context):
- Pay close attention to the activity the customer is organizing, where they are departing from (Cartagena vs already on the islands), and whether it is a 1-day plan or a multi-day package.
- When the customer asks about friends or companions who want to dive or snorkel, prefer options that keep this context: same origin and, when possible, a similar duration pattern (1-day plan vs multi-day package), unless the customer explicitly asks for something different (e.g. they say they want to stay overnight on the islands).

Always escalate to a human for:
- Booking or payment intent: in these situations, do not explain the detailed payment flow yourself; give only the basic plan information and make it clear that a human advisor will confirm availability and payment method.
- Real availability questions.
- Personal medical diagnosis or requests to authorize diving based on a health condition.
- Cancellations, changes, or complaints.
- Low-confidence answers or questions outside the context.

Advisor contact: WhatsApp +57 320 2301515.
Answer in English."""


def build_system_prompt(lang: str, query: str | None = None) -> str:
    """Compose the full system prompt: intro + dynamic tone + body + optional few-shot block.

    When ``query`` is provided, picks up to 2 topic-matching examples from conversations.json
    and appends them as compact reference context (not as imitation templates).
    """
    fewshot_block = ""
    if query:
        examples = _select_fewshot_examples(query, lang, k=2)
        fewshot_block = _format_fewshot_block(examples, lang)

    if lang == "es":
        prompt = (
            f"{_INTRO_ES}\n\n"
            f"Estilo y tono:\n{_build_tone_section('es')}\n\n"
            f"{_SYSTEM_PROMPT_ES_BODY}"
        )
    else:
        prompt = (
            f"{_INTRO_EN}\n\n"
            f"Style and tone:\n{_build_tone_section('en')}\n\n"
            f"{_SYSTEM_PROMPT_EN_BODY}"
        )

    if fewshot_block:
        prompt = f"{prompt}\n\n{fewshot_block}"
    return prompt


FOOD_QUERY_PATTERN = re.compile(
    r"\b(comida|almuerzo|lunch|meal|meals|food|vegetariano|vegetariana|vegetarian|vegano|vegana|vegan|celiaco|celiaca|celiac|alergia|alergias|allergy|allergies)\b",
    re.IGNORECASE,
)

DIETARY_QUERY_PATTERN = re.compile(
    r"\b(vegetariano|vegetariana|vegetarian|vegano|vegana|vegan|celiaco|celiaca|celiac|alergia|alergias|allergy|allergies)\b",
    re.IGNORECASE,
)

FOOD_FAQ_QUESTIONS = {
    "meal": {
        "es": "¿Que comida incluye el tour?",
        "en": "What food is included in the tour?",
    },
    "dietary": {
        "es": "Soy vegetariano o tengo una alergia alimentaria, ¿pueden atenderme?",
        "en": "I'm vegetarian or have a food allergy. Can you accommodate me?",
    },
}


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


def _normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _find_food_faq_answer(question: str, lang: str) -> str | None:
    faqs = load_faqs().get("faqs") or []
    question_key = "question_es" if lang == "es" else "question_en"
    answer_key = "answer_es" if lang == "es" else "answer_en"
    normalized_question = _normalize_text(question)

    for faq in faqs:
        faq_question = faq.get(question_key)
        faq_answer = faq.get(answer_key)
        if not isinstance(faq_question, str) or not isinstance(faq_answer, str):
            continue
        if _normalize_text(faq_question) == normalized_question and faq_answer.strip():
            return faq_answer.strip()
    return None


def _food_policy_answer(lang: str) -> str | None:
    policies = load_policies().get("policies") or {}
    food_policy = policies.get("food_policy") or {}
    answer = food_policy.get(lang)
    if isinstance(answer, str) and answer.strip():
        return answer.strip()
    return None


def _canonical_food_answer(query: str, lang: str) -> str | None:
    if not FOOD_QUERY_PATTERN.search(query):
        return None

    if DIETARY_QUERY_PATTERN.search(query):
        dietary_answer = _find_food_faq_answer(FOOD_FAQ_QUESTIONS["dietary"][lang], lang)
        if dietary_answer:
            return dietary_answer

    meal_answer = _find_food_faq_answer(FOOD_FAQ_QUESTIONS["meal"][lang], lang)
    if meal_answer:
        return meal_answer

    return _food_policy_answer(lang)


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

    canonical_food_answer = _canonical_food_answer(query, lang)
    if canonical_food_answer:
        logger.info(f"[RAG] Using canonical food answer query={query[:60]}... lang={lang}")
        return canonical_food_answer

    retrieval_query = build_retrieval_query(query, history)

    # Lightly bias retrieval using known origin from extra_context (Cartagena vs already on the islands)
    if extra_context:
        lowered_ctx = extra_context.lower()

        # Cliente saliendo desde Cartagena
        if "saldra desde cartagena" in lowered_ctx:
            rq_lower = retrieval_query.lower()
            if lang == "es" and "desde cartagena" not in rq_lower:
                retrieval_query += "\n\n[origen_cliente]=desde Cartagena"
            elif lang == "en" and "from cartagena" not in rq_lower:
                retrieval_query += "\n\n[origin]=from Cartagena"

        # Cliente que ya esta en las islas del Rosario
        if "ya esta en las islas del rosario" in lowered_ctx:
            rq_lower = retrieval_query.lower()
            if lang == "es" and "ya estoy en las islas del rosario" not in rq_lower:
                retrieval_query += "\n\n[origen_cliente]=ya en las islas"
            elif lang == "en" and "already on the rosario islands" not in rq_lower:
                retrieval_query += "\n\n[origin]=already on the Rosario Islands"

    safe_query = redact_pii(retrieval_query)

    # Retrieve relevant documents
    docs = await search_knowledge_base(safe_query, lang=lang)

    # Helper to call the LLM with unstructured context (either KB docs o solo extra_context)
    async def _answer_with_llm(context: str, context_sources: list[str] | None = None) -> str:
        system_prompt = build_system_prompt(lang, query=query)
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
