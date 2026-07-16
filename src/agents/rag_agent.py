"""
RAG Agent for knowledge base retrieval.

Uses pgvector embeddings to answer questions about Diving Planet
services, policies, and FAQs that fall outside the predefined
decision tree.
"""

import json
import logging
import re

from openai import AsyncOpenAI

from src.agents.grounding_check import (
    capacity_claims_grounded,
    currency_amounts_grounded,
    is_grounded,
    requests_personal_data,
    urls_grounded,
)
from src.agents.query_rewriter import condense_query
from src.config import settings
from src.knowledge.loader import (
    load_brand_tone,
    load_conversations,
    load_faqs,
    load_policies,
)
from src.knowledge.vector_store import detect_query_topics, get_pool, search_knowledge_base
from src.privacy import detect_pii, privacy_block_message, redact_pii

logger = logging.getLogger("uvicorn.error")

_BRAND_TONE_CACHE: dict | None = None
_CONVERSATIONS_CACHE: list[dict] | None = None
_FAQS_CACHE: list | None = None
_POLICIES_CACHE: dict | None = None
FEWSHOT_MAX_CHARS = 220


def _load_brand_tone_cached() -> dict:
    """Load and cache brand_tone.json at first access."""
    global _BRAND_TONE_CACHE
    if _BRAND_TONE_CACHE is None:
        _BRAND_TONE_CACHE = (load_brand_tone() or {}).get("brand_tone", {})
    return _BRAND_TONE_CACHE


def _load_faqs_cached() -> list:
    """Load and cache the faqs list at first access."""
    global _FAQS_CACHE
    if _FAQS_CACHE is None:
        _FAQS_CACHE = (load_faqs() or {}).get("faqs") or []
    return _FAQS_CACHE


def _load_policies_cached() -> dict:
    """Load and cache the policies dict at first access."""
    global _POLICIES_CACHE
    if _POLICIES_CACHE is None:
        _POLICIES_CACHE = (load_policies() or {}).get("policies") or {}
    return _POLICIES_CACHE


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


# Translate the legacy/Spanish `extracted_topics` labels stored in
# conversations.json into the canonical TOPIC_PATTERNS labels used by
# detect_query_topics(). Canonical labels (certification, location_islands,
# availability, schedule, meeting_point, pricing, equipment, discount_colombian,
# refresher, accommodation, weather_cancellation, booking...) pass through
# unchanged via aliases.get(t, t).
_FEWSHOT_TOPIC_ALIASES: dict[str, str] = {
    # Pricing / currency
    "precios": "pricing",
    "precios_usd": "pricing",
    "price_usd": "pricing",
    "precio_desde_isla": "pricing",
    # Colombian / resident pricing
    "precio_colombianos": "discount_colombian",
    "precio_local_residente": "discount_colombian",
    "precio_local": "discount_colombian",
    # Availability / booking cutoff
    "disponibilidad_ultima_hora": "availability",
    "ultima_hora": "availability",
    "corte_reserva_online": "availability",
    # Schedule
    "horarios": "schedule",
    "snorkel": "schedule",
    # Meeting point
    "punto_encuentro": "meeting_point",
    "punto_de_encuentro": "meeting_point",
    # Islands / pickup / base location
    "recogida_en_hotel": "location_islands",
    "planes_desde_islas": "location_islands",
    "base_en_islas": "location_islands",
    "base_cocoliso": "location_islands",
    "diferencia_isla_vs_cartagena": "location_islands",
    # Equipment / included
    "ubicacion_equipo": "equipment",
    "equipo_incluido": "equipment",
    "transfer_included": "equipment",
    "incluye": "equipment",
    # Booking process
    "grupo_mixto": "booking",
    "proceso_reserva": "booking",
    # Refresher
    "refresh": "refresher",
    # Weather / cancellation
    "clima": "weather_cancellation",
    "cancelacion_reembolso": "weather_cancellation",
    # Accommodation
    "alojamiento": "accommodation",
    # Courses
    "open_water_course": "certification",
}


# Stale few-shot guard: the "Colombian discount" was removed (v0.18.0) — Colombian
# clients now simply pay in COP (same price, currency only). Imported WhatsApp
# examples where the ADVISOR offered a special Colombian discount/bonus would
# teach the model the old behavior, so we skip them from few-shot selection.
# We only exclude examples whose ADVISOR messages pair a discount word with a
# Colombian/resident word — examples that merely quote a COP price for Colombians
# ("el valor para colombianos es 630.000") stay, since that is still correct.
_STALE_DISCOUNT_WORDS = ("descuento", "bono", "tarifa especial", "precio especial", "rebaja")
_STALE_COLOMBIAN_WORDS = ("colombian", "residente", "descuento local", "precio local")


def _strip_accents_lower(text: str) -> str:
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )


def _example_teaches_stale_colombian_discount(example: dict) -> bool:
    """True if the ADVISOR messages offer a (now-removed) Colombian discount."""
    bot_msgs = (example.get("diving_planet") or {}).get("messages") or []
    for msg in bot_msgs:
        norm = _strip_accents_lower(str(msg))
        if any(d in norm for d in _STALE_DISCOUNT_WORDS) and any(
            c in norm for c in _STALE_COLOMBIAN_WORDS
        ):
            return True
    return False


def _select_fewshot_examples(query: str, lang: str, k: int = 2) -> list[dict]:
    """Pick up to k conversation examples whose extracted_topics overlap with the query topics.

    Returns the raw example dicts (filtered by lang). Empty list if no useful match.
    Uses detect_query_topics() to score overlap; ties broken by example order in JSON.
    Examples that teach the removed Colombian discount are skipped entirely.
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
        if _example_teaches_stale_colombian_discount(example):
            continue
        ex_topics = set(str(t) for t in (example.get("extracted_topics") or []))
        normalized = {_FEWSHOT_TOPIC_ALIASES.get(t, t) for t in ex_topics}
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

    Deliberately does NOT quote the real customer's literal message: it's personal,
    specific detail (a spouse, a named hotel, a family composition) that belongs to a
    DIFFERENT, unrelated customer. Quoting it invited the model to blend those details
    into its answer for the current customer (e.g. inventing "tu esposo" out of thin
    air because a past customer's message happened to mention one). Only the topic
    label and the advisor's response pattern are shown — that's what teaches tone and
    coverage without leaking someone else's facts.
    """
    if not examples:
        return ""

    header = (
        "Situaciones reales del centro (referencia de tono/cobertura, NO son datos del cliente actual):"
        if lang == "es"
        else "Real situations the center has handled (tone/coverage reference, NOT facts about the current customer):"
    )
    lines = [header]
    for ex in examples:
        scenario = (ex.get("scenario") or "").strip()
        first_bot_action = ""
        bot_msgs = ((ex.get("diving_planet") or {}).get("messages") or [])
        if bot_msgs:
            first_bot_action = str(bot_msgs[0]).strip()

        action = first_bot_action[:120] + ("..." if len(first_bot_action) > 120 else "")
        bullet = f"- {scenario[:60]} | Asesor cubrio: {action}"
        if lang == "en":
            bullet = f"- {scenario[:60]} | Advisor covered: {action}"
        # Hard cap per bullet
        if len(bullet) > FEWSHOT_MAX_CHARS:
            bullet = bullet[:FEWSHOT_MAX_CHARS - 3] + "..."
        lines.append(bullet)

    return "\n".join(lines)


FALLBACK_ES = (
    "¡Con gusto te ayudo con eso! 🌊 Para ese tema en concreto, lo mejor es que te pase "
    "con un asesor de Diving Planet, que te lo resuelve al momento.\n"
    "WhatsApp: +57 320 231515"
)

FALLBACK_EN = (
    "Happy to help with that! 🌊 For this specific topic, the best thing is to connect you "
    "with a Diving Planet advisor, who'll sort it out for you right away.\n"
    "WhatsApp: +57 320 231515"
)

_INTRO_ES = (
    "Eres *Coral*, de Diving Planet, el primer centro de buceo PADI 5 Estrellas "
    "de Colombia con 30 años de experiencia en las Islas del Rosario, Cartagena. "
    "Te llamas Coral y hablas de ti misma en femenino (\"soy Coral\", \"encantada\", \"aquí estoy\"). "
    "NUNCA te describas como 'asistente', 'asistente virtual', 'bot' ni 'IA': simplemente eres Coral, "
    "de Diving Planet. Si te preguntan tu nombre, di con naturalidad que eres Coral, de Diving Planet, "
    "y que con gusto les ayudas con su buceo o les pasas con un asesor del equipo."
)

_INTRO_EN = (
    "You are *Coral*, from Diving Planet, Colombia's first PADI 5 Star Dive Center "
    "with 30 years of experience in the Rosario Islands, Cartagena. "
    "Your name is Coral and you refer to yourself in the feminine. NEVER describe yourself as an "
    "'assistant', 'virtual assistant', 'bot' or 'AI': you are simply Coral, from Diving Planet. If asked "
    "your name, naturally say you're Coral, from Diving Planet, and that you're happy to help with their "
    "diving or connect them with a team advisor."
)

_SYSTEM_PROMPT_ES_BODY = """Tono y estilo — fundamental:
- Habla como un cartagenero amigable, cálido y profesional, igual que un asesor real de Diving Planet en WhatsApp.
- Tutea al cliente ('tú', '¿quieres?', 'tienes') de forma cálida y cercana — es el registro natural costeño de Cartagena. NO uses 'usted' de forma sistemática.
- Usa expresiones colombianas costeñas cuando encajen de forma natural, con moderación: "¡Con mucho gusto!", "¡Claro que sí!", "¡Listo!", "¡Bacano!", "¡Chévere!", "¡De una!", "Cuéntame", "¡Eso está hecho!", "Te cuento", "Tranqui, aquí te ayudamos".
- Mensajes cortos, directos y cálidos. Nunca sonar robótico, genérico ni corporativo. No caricaturices el acento ni escribas mal a propósito.
- Para preguntas GENERALES o dudas sobre el buceo, las actividades o el destino (no datos logísticos muy puntuales como una hora o un link), abre con una frase breve, cálida y entusiasta que introduzca el tema en positivo —que es una experiencia muy chula, que se va a disfrutar, lo bonito del arrecife/las Islas del Rosario— ANTES de dar la información concreta. Que se sienta explicativo y cercano, como un asesor que ama lo que hace, no un dato seco. Una o dos frases de intro, sin alargarte ni sonar a folleto, y luego respondes la pregunta.

Reglas estrictas — nunca las incumplas:
- ⚠️ NUNCA inventes acompañantes: si el cliente NO mencionó explícitamente con quién viaja, NO asumas ni menciones "tu esposo/esposa/pareja/novio/novia/hijo/amigo" bajo ningún concepto — ni siquiera como suposición típica de "cliente de buceo casual". Un mensaje como "estoy en la isla, en el hotel X, quiero bucear" es de UNA persona hablando de SÍ MISMA; responde en singular ("tú puedes...") y jamás inventes un tercero. Esto aplica incluso si otros ejemplos o conversaciones que conoces mencionan parejas/esposos — cada cliente es un caso nuevo y aislado.
- Responde SOLO con la información del contexto proporcionado.
- Si la respuesta no está en el contexto o hay duda, dilo y ofrece: "Te paso con un asesor para que te ayude con gusto".
- Nunca inventes precios, horarios, disponibilidad, códigos de descuento, links de pago ni confirmaciones de reserva. Esto incluye NUNCA decir frases como "listo, cambiamos/confirmamos/movimos la reserva" ante una solicitud de reservar o cambiar una fecha — el bot no gestiona reservas reales, solo un asesor humano lo hace. Reconoce la solicitud sin afirmar que ya se ejecutó (ej.: "Entendido, quieres moverlo al día 20 — para confirmarlo necesito...", nunca "¡Listo! Cambiamos la reserva al 20").
- Si el contexto incluye la fecha/hora actual y una política con un corte de horario (ej: "el sistema cierra a las 4:30 PM del día anterior"), COMPARA la hora actual con ese corte antes de afirmar que ya pasó o no. Si no tienes la hora actual en el contexto, o la comparación es ambigua, NO afirmes que el corte "ya pasó" — informa el horario de forma neutral y ofrece WhatsApp como alternativa, sin urgencia inventada ni emojis de preocupación.
- Nunca inventes cifras que no estén en el contexto: capacidad o número máximo de personas, duración (días/semanas/meses), tiempos, ni cupos. Si el contexto no lo dice, responde que el asesor lo confirma — NO des un número inventado.
- El descuento por equipo propio (5%) SOLO aplica si el cliente trae el equipo COMPLETO (regulador, BCD/chaleco, traje, máscara, aletas). Si menciona solo una PARTE del equipo (ej: "traigo mi máscara y aletas"), responde que ese descuento no aplica por equipo parcial — NO confirmes el descuento en ese caso.
- NUNCA confirmes disponibilidad o cupo para una fecha concreta ("mañana", "el sábado"): tú no ves el calendario real. Si en el contexto una situación pasada dice "tenemos cupos" o "se confirma cupo", eso fue OTRO día con OTRO cliente — no aplica hoy. Responde con el horario/proceso general y deriva la confirmación de cupo al asesor.
- Respeta lo que el contexto diga que NO está disponible. Si un servicio aparece como "no disponible desde Cartagena" (p.ej. 1 sola inmersión) o "por consulta", NO lo ofrezcas como si estuviera disponible; explica la limitación y ofrece la alternativa que sí existe.
- Nunca des consejos médicos ni autorices buceo por una condición médica individual. Deriva a asesor para esos casos.
- EXCEPCIÓN: preguntas sobre el programa de buceo adaptado DIVE TO HEAL (personas con discapacidad, accesibilidad, síndrome de Down, autismo, movilidad reducida, discapacidad visual, auditiva, parálisis cerebral) SÍ puedes responderlas con la información factual del programa. Es información pública del centro, no consejo médico personal.
- Nunca pidas ni repitas datos sensibles (IDs, cuentas, comprobantes de pago, números de tarjeta).
- NUNCA gestiones la reserva recogiendo datos en el chat: no pidas nombres y apellidos, cédula/pasaporte, correo ni fechas "para confirmar la reserva". Tú NO tramitas reservas. El cierre correcto es SIEMPRE: enviar el link de reserva online del servicio (si está en el contexto) o pasar con un asesor humano — el asesor o el formulario oficial recogen los datos, nunca tú.
- No escribas respuestas largas tipo folleto si el cliente hizo una pregunta concreta.
- Cuando el cliente mencione *varias personas con intención de reservar* (ej: "yo X y mi pareja/él/ella Y", "somos 3 y unos quieren snorkel otros buceo"), NO asignes roles persona-actividad ("Para ti…/Para ella…") ni cites precios individuales por persona. Solo describe las actividades disponibles de forma *neutral* (1-2 frases breves) y deriva al asesor para que confirme la composición exacta del grupo y el precio total.

Enfoque SIEMPRE positivo (muy importante):
- Todo lo que el cliente proponga o pregunte —una fecha, un mes, una estación del año, el número de personas, el lugar, la actividad, o una comparación con otro sitio— respóndelo SIEMPRE en positivo, sacando el lado bueno. El objetivo es animar y dar confianza, nunca desanimar.
- NUNCA le digas al cliente que su elección es mala, que "esa fecha no es buena", que "es mal mes", que "hay mejores épocas" o similares. Si pregunta "¿es buena época en septiembre?" / "¿vamos 6 personas, está bien?" / "¿es buen sitio las Islas del Rosario?", la respuesta es siempre que sí, que es un gran momento/plan/lugar, y refuerzas con algo concreto y real (buceamos todo el año con buenas condiciones, aguas cálidas del Caribe, grupos bienvenidos, etc.).
- Esto NO te autoriza a inventar datos ni a ocultar temas de SEGURIDAD: si hay un cierre real (25 de diciembre y 1 de enero) o una condición meteorológica/médica, se informa o se deriva a un asesor, pero SIEMPRE con tono constructivo y ofreciendo alternativas ("ese día no operamos, pero cualquier otro día del año es ideal y te ayudo a encontrar el mejor").
- Ante comparaciones ("¿es mejor aquí o en otro lado?") resalta lo bueno de Diving Planet y de las Islas del Rosario sin hablar mal de otros; nunca desacredites otros lugares ni digas que una opción es peor.

Gestión de precios, monedas y pagos:
- Usa el contexto de extra_context para adaptar la moneda: si se indica que el cliente NO es colombiano/a, muestra los precios en USD; si se indica que SÍ es colombiano/a, muestra los precios en COP. No existe descuento especial por ser colombiano; los colombianos simplemente pagan en pesos y los extranjeros en dólares al mismo precio equivalente.
- Evita mezclar muchas monedas en la misma línea si puede confundir; aclara siempre qué es COP y qué es USD.
- Aunque en el contexto aparezcan flujos de pago (formularios, porcentajes como 50%, transferencias, etc.), NO describas el proceso exacto de pago ni montos de anticipo. Explica de forma general que un asesor humano te indicará el paso a paso y el valor del anticipo si aplica.
- No inventes ni reconstruyas links de pago o de formularios. Si el cliente pregunta cómo pagar o cómo completar el formulario de exoneración, di que el asesor le enviará el enlace y las instrucciones concretas.

Uso del contexto de la conversación (extra_context):
- Ten muy en cuenta la actividad que el cliente está organizando, desde dónde sale (Cartagena o ya en las islas) y si se trata de un plan de 1 día o de varios días.
- Cuando el cliente pregunte por amigos o acompañantes que quieran bucear o hacer snorkel, prioriza opciones que mantengan este contexto: mismo origen y, cuando sea posible, misma lógica de duración (plan de 1 día vs paquete multi-día), salvo que el cliente pida explícitamente otra cosa (por ejemplo, que quiere quedarse a dormir en las islas).
- CUIDADO al usar datos ya conocidos del cliente (tamaño de grupo, edades, etc.): úsalos SOLO si la pregunta es realmente sobre su propia reserva. Si la pregunta es genérica/de política ("¿cuántas personas caben en un grupo?", "¿hay edad mínima?"), responde primero de forma neutral y factual — NO empieces la respuesta asumiendo o celebrando el dato del cliente ("¡qué bueno que sean 4!") como si la pregunta fuera sobre él. No fuerces conexiones que el cliente no pidió.

Cuándo derivar siempre a humano:
- Intención de reservar o pagar: en estos casos no expliques el flujo de pago detallado, solo da la información básica del plan y aclara que un asesor humano se encargará de confirmar cupos y forma de pago.
- Preguntas de disponibilidad real.
- Diagnóstico médico personal o solicitud de autorización para bucear por condición de salud.
- Cancelaciones, cambios o quejas.
- Preguntas con baja confianza o fuera del contexto.

Contacto asesor: WhatsApp +57 320 231515.
Responde SIEMPRE en español, aunque el contexto recuperado, los nombres de servicios o la pregunta contengan palabras en inglés (ej. "open water", "advanced")."""

_SYSTEM_PROMPT_EN_BODY = """Strict rules — never break these:
- ⚠️ NEVER invent companions: if the customer did NOT explicitly say who they're traveling with, do NOT assume or mention "your husband/wife/partner/boyfriend/girlfriend/child/friend" under any circumstance — not even as a "typical casual diver" guess. A message like "I'm on the island, at hotel X, I want to dive" is ONE person talking about THEMSELVES; answer in singular ("you can...") and never invent a third person. This applies even if other examples or conversations you know of mention spouses/partners — every customer is a new, isolated case.
- Answer ONLY using the provided context.
- If the answer is not in the context or you're unsure, say so and offer: "For this specific situation, I prefer to transfer you to my boss".
- Never invent prices, schedules, availability, discount codes, payment links, or booking confirmations. This includes NEVER saying things like "great, we've changed/confirmed your booking" in response to a request to book or change a date — the bot doesn't manage real reservations, only a human advisor does. Acknowledge the request without claiming it was already carried out (e.g. "Got it, you'd like to move it to the 20th — to confirm that I need...", never "Done! We've changed your booking to the 20th").
- If the context includes the current date/time and a policy with a time cutoff (e.g. "the system closes at 4:30 PM the day before"), COMPARE the current time against that cutoff before claiming it has already passed or not. If you don't have the current time in the context, or the comparison is ambiguous, do NOT claim the cutoff "has already passed" — state the schedule neutrally and offer WhatsApp as an alternative, without inventing urgency or worried emojis.
- Never invent numbers that aren't in the context: maximum group capacity / number of people, duration (days/weeks/months), timeframes, or slots. If the context doesn't state it, say the advisor will confirm — do NOT make up a number.
- The own-equipment discount (5%) ONLY applies if the customer brings their COMPLETE gear (regulator, BCD, wetsuit, mask, fins). If they mention only PART of the equipment (e.g. "I'm bringing my mask and fins"), say that discount doesn't apply for partial gear — do NOT confirm the discount in that case.
- NEVER confirm availability or open slots for a specific date ("tomorrow", "Saturday"): you cannot see the real calendar. If a past situation in the context says "we have slots" or "spot confirmed", that was ANOTHER day with ANOTHER customer — it doesn't apply today. Give the general schedule/process and route slot confirmation to the advisor.
- Respect what the context says is NOT available. If a service is marked "not available from Cartagena" (e.g. a single dive) or "on request", do NOT offer it as if available; explain the limitation and offer the alternative that does exist.
- Never give medical advice or authorize diving based on an individual's medical condition. Always refer to an advisor for those cases.
- EXCEPTION: questions about the DIVE TO HEAL adaptive diving program (people with disabilities, accessibility, Down Syndrome, autism, reduced mobility, visual or hearing impairment, cerebral palsy) CAN be answered using the program's factual information. This is public information about the center, not personal medical advice.
- Never request or repeat sensitive data (IDs, accounts, payment receipts, card numbers).
- NEVER process a booking by collecting data in chat: do not ask for full names, ID/passport numbers, email or dates "to confirm the booking". You do NOT process bookings. The correct close is ALWAYS: send the service's online booking link (if present in the context) or hand off to a human advisor — the advisor or the official form collects the data, never you.
- Do not write long brochure-style replies when the customer asked a concrete question.
- When the customer mentions *multiple people with booking intent* (e.g. "I want X and my partner/he/she Y", "we are 3 and some want snorkel others diving"), do NOT assign person-activity roles ("For you…/For her…") nor quote individual per-person prices. Just describe the available activities *neutrally* (1-2 short sentences) and route to the human advisor so they confirm the exact group composition and total price. The bot's structured flow already builds the cart with quantities; your only job in this case is brief context + escalation.

ALWAYS stay positive (very important):
- For GENERAL questions or doubts about diving, the activities or the destination (not very specific logistics like a time or a link), open with a short, warm, enthusiastic sentence that introduces the topic positively —that it's a really cool experience, that they'll love it, the beauty of the reef / the Rosario Islands— BEFORE giving the concrete information. Make it feel explanatory and personal, like an advisor who loves what they do, not a dry fact. One or two intro sentences, without going long or sounding like a brochure, then answer the question.
- Whatever the customer proposes or asks about —a date, a month, a season, the number of people, the place, the activity, or a comparison with somewhere else— always answer positively, highlighting the good side. The goal is to encourage and reassure, never to discourage.
- NEVER tell the customer their choice is bad, that "that date isn't good", that "it's a bad month", that "there are better seasons", or similar. If they ask "is September a good time?" / "we're 6 people, is that ok?" / "are the Rosario Islands a good spot?", the answer is always yes — it's a great time/plan/place — and you back it up with something concrete and true (we dive year-round with good conditions, warm Caribbean waters, groups are welcome, etc.).
- This does NOT let you invent facts or hide SAFETY matters: if there is a real closure (December 25 and January 1) or a weather/medical condition, you inform or route to an advisor, but ALWAYS with a constructive tone and offering alternatives ("we don't operate that day, but any other day of the year is ideal and I'll help you find the best one").
- For comparisons ("is it better here or somewhere else?") highlight what's great about Diving Planet and the Rosario Islands without speaking badly of others; never disparage other places or say an option is worse.

Pricing, currencies, and payments:
- Use the extra_context to adapt currency: if the customer is NOT Colombian, show prices in USD; if they ARE Colombian, show prices in COP. There is no special discount for being Colombian — Colombians simply pay in pesos and international clients in dollars at the equivalent price.
- Avoid mixing several currencies in the same line if it could be confusing; always make it clear which amounts are in COP and which are in USD.
- Even if the context contains payment flows (forms, percentages like 50%, bank transfers, etc.), do NOT describe the exact payment process or the amount of any deposit. Explain in general terms that a human advisor will confirm the step-by-step process and any advance payment if applicable.
- Do not invent or reconstruct payment or form links. If the customer asks how to pay or how to complete the waiver form, tell them that the advisor will send the correct link and instructions.

How to use conversation context (extra_context):
- Pay close attention to the activity the customer is organizing, where they are departing from (Cartagena vs already on the islands), and whether it is a 1-day plan or a multi-day package.
- When the customer asks about friends or companions who want to dive or snorkel, prefer options that keep this context: same origin and, when possible, a similar duration pattern (1-day plan vs multi-day package), unless the customer explicitly asks for something different (e.g. they say they want to stay overnight on the islands).
- BE CAREFUL using facts already known about the customer (group size, ages, etc.): only use them if the question is actually about their own booking. If the question is generic/policy ("how many people fit in a group?", "is there a minimum age?"), answer neutrally and factually first — do NOT open the reply by assuming or celebrating the customer's own fact ("great that you're 4!") as if the question were about them. Don't force connections the customer didn't ask for.

Always escalate to a human for:
- Booking or payment intent: in these situations, do not explain the detailed payment flow yourself; give only the basic plan information and make it clear that a human advisor will confirm availability and payment method.
- Real availability questions.
- Personal medical diagnosis or requests to authorize diving based on a health condition.
- Cancellations, changes, or complaints.
- Low-confidence answers or questions outside the context.

Advisor contact: WhatsApp +57 320 231515.
ALWAYS answer in English, even if the retrieved context or service names contain Spanish words."""


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


# Anaphoric / follow-up indicators: demonstratives and pronouns that refer back
# to something said earlier ("these packages", "ese plan", "lo mismo"...).
_FOLLOW_UP_INDICATORS = re.compile(
    r"\b("
    r"this|that|these|those|it|them|they|same|also|previous|one|ones|"
    r"ese|esa|eso|esos|esas|este|esta|esto|estos|estas|"
    r"mismo|misma|mismos|mismas|anterior|tambi[eé]n|aquel|aquella|aquello"
    r")\b",
    re.IGNORECASE,
)
# Queries that begin with a connector are almost always continuations ("y ...", "and ...").
_FOLLOW_UP_PREFIX = re.compile(r"^[¿¡\s]*(y|e|and|pero|but|o|or|entonces|then)\b", re.IGNORECASE)

# Declarative location/situation statements answering a prior question
# ("en el hotel Pao Pao", "estoy en Isla Grande", "at the X hotel"). These are
# follow-ups that need the conversation context to be understood for retrieval.
# Note: interrogatives like "¿en qué consiste...?" are NOT matched (require "en el/la").
_LOCATION_STATEMENT_PREFIX = re.compile(
    r"^[¿¡\s]*("
    r"estoy en|estamos en|me hospedo|nos hospedamos|me alojo|nos alojamos|"
    r"en el|en la|en isla|en hotel|"
    r"i'?m (at|in|staying)|we'?re (at|in|staying)|i am (at|in|staying)|"
    r"we are (at|in|staying)|staying at|staying in|at the|in the"
    r")\b",
    re.IGNORECASE,
)


def _looks_like_follow_up(query: str) -> bool:
    """Heuristic: does this query rely on previous turns to be understood?

    A self-contained question (names its own subject) returns False so we do NOT
    pollute its retrieval with unrelated earlier questions. Short queries and
    anaphoric ones return True so they get conversational context.
    """
    text = (query or "").strip()
    if not text:
        return False
    # Very short fragments ("the prices", "y los niños?") are almost always
    # follow-ups; condense_query also handles these, this is a safety net.
    if len(text.split()) < 4:
        return True
    if _FOLLOW_UP_PREFIX.match(text):
        return True
    # Declarative location/situation answers ("en el hotel Pao Pao") need context.
    if _LOCATION_STATEMENT_PREFIX.match(text):
        return True
    return bool(_FOLLOW_UP_INDICATORS.search(text))


def build_retrieval_query(query: str, history: list[dict] | None = None) -> str:
    if not history:
        return query

    # Only enrich genuine follow-ups with conversation history. A self-contained
    # question must be retrieved on its own — otherwise an unrelated previous
    # question dilutes the embedding and the right doc falls below the threshold.
    if not _looks_like_follow_up(query):
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


AMBIGUOUS_LOCATION_NAMES = (
    "Isla Grande",
    "Isla Marina",
    "Isla del Pirata",
    "Isla del Sol",
    "Isleta",
    "Isla Arena",
    "Isla Pavitos",
    "Isla Lizamar",
    "Isla Gigi",
    "Isla Rosa",
    "Isla Pelicano",
    "Isla Rosario",
    "San Pedro de Majagua",
    "Bora Bora Beach Club",
    "Cocoliso Island Resort",
    "Pao Pao Hotel",
    "Fragata Island House",
    "Secreto Hostel",
    "Gente de Mar Resort",
    "Luxury Beach Club",
    "Ecohotel Las Flores",
    "Ecohostal Playa Libre",
    "Islabela",
    "Hotel El Hamaquero",
    "Centro Ubuntu",
    "Hotel Isla del Pirata",
    "Hotel Isla del Sol",
    "Coralina Island",
    "Isleta Beach",
    "Isla Arena Eco Resort",
    "Isla Pavitos (Privada)",
    "Hotel Lizamar",
    "Casa de Isla Gigi",
    "Isla Rosa (Privada)",
    "Isla Pelicano",
    "Rosario EcoHotel",
    "Hotel San Tropel",
)

AMBIGUOUS_LOCATION_PREFIXES = (
    "hotel ",
    "casa de ",
    "centro ",
)

AMBIGUOUS_LOCATION_SUFFIXES = (
    " hotel",
    " island resort",
    " island house",
    " beach club",
    " eco resort",
    " resort",
    " hostel",
    " island",
    " ecohotel",
)

LOCATION_QUERY_INTENT_PATTERN = re.compile(
    r"\b(recog(?:er|ida|en|eme|emos|ernos)?|pickup|pick\s*up|alojamiento|hosped(?:aje|arme|arnos)?|stay|staying|buce(?:o|ar|a|an)|div(?:e|ing)|snorkel|curso|minicurso|tour|plan|paquete|package|precio|cost|cu[aá]nto|reserv(?:a|ar)|book(?:ing)?|availability|disponibilidad|itinerario|schedule|ubicaci[oó]n|location|d[oó]nde|where|c[oó]mo|how)\b",
    re.IGNORECASE,
)


def _is_safe_location_alias(value: str) -> bool:
    words = value.split()
    return len(words) >= 2 or len(value) >= 7


def _build_ambiguous_location_catalog() -> frozenset[str]:
    aliases: set[str] = set()
    for raw_name in AMBIGUOUS_LOCATION_NAMES:
        cleaned = re.sub(r"\s*\([^)]*\)", "", raw_name).strip()
        normalized = _normalize_text(cleaned)
        if not normalized:
            continue

        candidates = {normalized}
        for prefix in AMBIGUOUS_LOCATION_PREFIXES:
            if normalized.startswith(prefix):
                candidate = normalized[len(prefix):].strip()
                if candidate:
                    candidates.add(candidate)
        for suffix in AMBIGUOUS_LOCATION_SUFFIXES:
            if normalized.endswith(suffix):
                candidate = normalized[: -len(suffix)].strip()
                if candidate:
                    candidates.add(candidate)

        for candidate in candidates:
            if candidate == normalized or _is_safe_location_alias(candidate):
                aliases.add(candidate)

    aliases.add("majagua")
    return frozenset(aliases)


AMBIGUOUS_LOCATION_CATALOG = _build_ambiguous_location_catalog()


def _is_ultra_short_ambiguous_location_query(query: str) -> bool:
    normalized = _normalize_text(query)
    if not normalized:
        return False
    if len(re.findall(r"\w+", normalized, re.UNICODE)) > 5:
        return False
    if normalized not in AMBIGUOUS_LOCATION_CATALOG:
        return False
    if LOCATION_QUERY_INTENT_PATTERN.search(normalized):
        return False
    return True


def _ambiguous_location_clarification(query: str, lang: str) -> str | None:
    if not _is_ultra_short_ambiguous_location_query(query):
        return None

    place = query.strip().strip("¿?¡!.,;:")
    if not place:
        place = query.strip()

    if lang == "es":
        return (
            f"¿Te refieres a {place} para recogida, alojamiento o para saber qué plan aplica si ya estás allí? "
            "Si me dices eso, te respondo más preciso."
        )
    return (
        f"Do you mean {place} for pickup, accommodation, or to know which plan applies if you're already there? "
        "If you tell me that, I can answer more precisely."
    )


def _find_food_faq_answer(question: str, lang: str) -> str | None:
    faqs = _load_faqs_cached()
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
    policies = _load_policies_cached()
    food_policy = policies.get("food_policy") or {}
    answer = food_policy.get(lang)
    if isinstance(answer, str) and answer.strip():
        return answer.strip()
    return None


# The food canonical answer must NOT hijack a broader booking/recommendation
# query that merely mentions a dietary word (e.g. "somos 8, 3 open water... uno
# vegetariano, ¿qué recomiendan y cuánto sale?"). When the message also carries
# group-composition / cert-level / budget / recommendation / package signals,
# food is incidental — let RAG answer the whole thing (it still covers the food).
_FOOD_HIJACK_GUARD = re.compile(
    r"\b(?:recomien\w+|recommend\w*|presupuesto|budget|"
    r"\d+\s+personas?|somos\s+\d+|we\s+are\s+\d+|group\s+of\s+\d+|"
    r"open\s+water|advanced|rescue|divemaster|"
    r"paquete|package|reserv\w+|book)\b",
    re.IGNORECASE,
)


# Canonical shortcuts answer with a fixed/generic text instead of real retrieval.
# When the regex that decides "this is generic, not a specific question" misses a
# phrasing we didn't anticipate (regional slang, synonyms, typos), the shortcut
# still fires and the client silently gets an answer that looks complete but may
# not cover what they actually asked. This closing line is a safety net: it makes
# the shortcut itself invite the client to re-ask with detail, so an uncovered
# phrasing doesn't end the conversation with a wrong impression.
_CANONICAL_SAFETY_NET = {
    "es": "\n\nSi tu pregunta era sobre algo más concreto que esto, cuéntamelo con más detalle y te confirmo con exactitud. 🙂",
    "en": "\n\nIf your question was about something more specific than this, tell me more and I'll confirm the exact details. 🙂",
}


def _canonical_food_answer(query: str, lang: str) -> str | None:
    if not FOOD_QUERY_PATTERN.search(query):
        return None

    # Food is incidental inside a bigger booking/recommendation query -> defer to RAG.
    if _FOOD_HIJACK_GUARD.search(query):
        return None

    answer = None
    if DIETARY_QUERY_PATTERN.search(query):
        answer = _find_food_faq_answer(FOOD_FAQ_QUESTIONS["dietary"][lang], lang)

    if not answer:
        answer = _find_food_faq_answer(FOOD_FAQ_QUESTIONS["meal"][lang], lang)

    if not answer:
        answer = _food_policy_answer(lang)

    if not answer:
        return None

    return answer + _CANONICAL_SAFETY_NET[lang]


# "What do you offer / what options / what plans for diving?" — an open overview
# question. RAG used to answer it by picking a couple of arbitrary services (e.g.
# minicourse + Nitrox specialty), which read as random. Instead we give one short,
# structured overview grouped by the customer's situation. Requires BOTH an
# "offer/options/what-can-I-do" phrase AND a diving word, so specific questions
# ("what does the minicourse include?", "how much is diving?") don't match.
_OVERVIEW_PHRASE = re.compile(
    r"\b(?:qu[eé]\s+(?:ofrec\w*|tien\w+|hay|opciones|planes|actividades|tipos|servicios)|"
    r"opciones|planes|alternativas|options|plans|alternatives|"
    r"qu[eé]\s+puedo\s+hacer|qu[eé]\s+se\s+puede\s+hacer|"
    r"what\s+(?:do\s+you\s+(?:offer|have|got)|options|can\s+i\s+do|kind\s+of)|"
    r"which\s+(?:options|plans)|tell\s+me\s+about\s+(?:your\s+)?(?:diving|options))\b",
    re.IGNORECASE,
)
_OVERVIEW_DIVING_WORD = re.compile(
    r"\b(?:buce\w*|buse\w*|buz\w*|dive|dives|diver|divers|diving|scuba|snorkel\w*|inmersi\w+)\b",
    re.IGNORECASE,
)
# Guard: don't hijack price/inclusion/logistics questions that happen to match.
_OVERVIEW_EXCLUDE = re.compile(
    r"\b(?:precio|precios|cuesta|cu[aá]nto|vale|incluye|incluyen|"
    r"price|cost|how\s+much|include|includes)\b",
    re.IGNORECASE,
)

# The overview covers 4 audiences (never dived / certified / wants course /
# snorkel-only) so it's safe by default, but a client who already tells us
# "soy buzo"/"tengo el open water" doesn't need to be asked "¿nunca has
# buceado?" first — it reads as if we ignored what they just said. When this
# fires, the certified block moves to the front and the intro acknowledges it,
# without dropping the other blocks (their companion could still be a
# beginner, so full coverage stays).
_ALREADY_CERTIFIED_RE = re.compile(
    r"\b(?:soy|somos|estoy|estamos)\s+(?:ya\s+)?(?:un[oa]?\s+)?buz[oa]s?\b"
    r"|\bya\s+(?:soy|somos)\s+(?:buz[oa]s?|certificad\w*)\b"
    r"|\b(?:soy|somos|estoy|estamos)\s+certificad\w*\b"
    r"|\btengo\s+(?:el\s+|la\s+|mi\s+)?(?:open\s*water|advanced|rescue|divemaster|licencia)\b"
    r"|\bi(?:'?m|\s+am)\s+a\s+certified\s+diver\b|\bwe\s+are\s+certified\s+divers?\b"
    r"|\bi\s+have\s+(?:my\s+)?open\s*water\b",
    re.IGNORECASE,
)
# Excludes "wants to get certified" phrasings so they're never read as already
# holding a cert (mirrors intent_detector._WANTS_CERT_RE at a lighter weight,
# since this only needs to gate the overview's framing, not full state).
_WANTS_CERT_EXCLUDE_RE = re.compile(
    r"\bquiero\s+(?:ser|sacar(?:me)?|hacer(?:me)?|certificar(?:me)?)\b"
    r"|\bme\s+gustar[ií]a\s+certificarme\b|\bwant\s+to\s+(?:get|become)\s+certified\b",
    re.IGNORECASE,
)

# A client traveling with someone else who doesn't dive is asking, in part,
# what THAT person can do — the overview used to ignore this entirely. Not
# everyone says "acompañante": "soy buzo y uno acompaña", "somos 5, tres
# bucean y dos no", "mi pareja no bucea" all describe the same situation
# without ever using the noun, so several independent phrasings are checked.
_MENTIONS_COMPANION_RE = re.compile(r"\bacompa\w+|\bcompanion\w*\b", re.IGNORECASE)
# Explicit "doesn't/don't dive" — conjugation already encodes singular/plural
# in Spanish ("no bucea" vs "no bucean"), so it doubles as the plural signal.
_NON_DIVER_SINGULAR_RE = re.compile(
    r"\bno\s+bucea\b|\bdoesn'?t\s+dive\b|\bnot\s+diving\b", re.IGNORECASE
)
_NON_DIVER_PLURAL_RE = re.compile(
    r"\bno\s+bucean\b|\bdon'?t\s+dive\b|\bnon-?divers\b", re.IGNORECASE
)
# Elliptical split — the verb is omitted the second time ("tres bucean y dos
# no", "y el resto no"; EN "three dive and two don't"), so anchor on
# "y/and <quantifier> no/don't". Spanish drops the verb after "no"; English
# keeps the negated auxiliary ("don't"/"doesn't"), so each needs its own regex.
_NON_DIVER_ELLIPTICAL_ES_RE = re.compile(
    r"\by\s+(?:\d+|uno|una|dos|tres|cuatro|cinco|seis|otro|otra|otros|otras|"
    r"el\s+resto|los\s+dem[aá]s)\s+no\b",
    re.IGNORECASE,
)
_NON_DIVER_ELLIPTICAL_EN_RE = re.compile(
    r"\band\s+(?:\d+|one|two|three|four|five|another|others?|the\s+rest)\s+"
    r"(?:don'?t|doesn'?t)\b",
    re.IGNORECASE,
)
_NON_DIVER_ELLIPTICAL_PLURAL_WORDS = (
    "dos", "tres", "cuatro", "cinco", "seis", "otros", "otras",
    "el resto", "los dem", "two", "three", "four", "five", "rest", "others",
)
# Distinguishes "un acompañante" (one) from several, so the reply says "your
# companion" vs "your companions" instead of always assuming just one.
# Plural fires on the plain plural noun ("acompañantes"/"companions") or a
# quantifier > 1 right before it ("2 acompañantes", "varios amigos que...").
_COMPANION_PLURAL_QUANTIFIER_RE = re.compile(
    r"\b(?:\d+|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|varios|varias|"
    r"algunos|algunas|unos|unas|several|multiple|two|three|four|five)\s+(?:acompa\w+|companions?)",
    re.IGNORECASE,
)


def _mentions_already_certified(query: str) -> bool:
    return bool(_ALREADY_CERTIFIED_RE.search(query)) and not _WANTS_CERT_EXCLUDE_RE.search(query)


def _mentions_plural_companions(query: str) -> bool:
    match = re.search(r"\bacompa\w+\b|\bcompanions?\b", query, re.IGNORECASE)
    if match and match.group(0).lower().rstrip("?.,;:!").endswith("s"):
        return True
    return bool(_COMPANION_PLURAL_QUANTIFIER_RE.search(query))


def _detect_companion_mention(query: str) -> tuple[bool, bool]:
    """Returns (has_companion, is_plural) from any of the phrasings a client
    might use to describe someone in the group who doesn't dive."""
    if _MENTIONS_COMPANION_RE.search(query):
        return True, _mentions_plural_companions(query)
    if _NON_DIVER_PLURAL_RE.search(query):
        return True, True
    if _NON_DIVER_SINGULAR_RE.search(query):
        # "el resto"/"los demás"/"the rest"/"the others" are collective nouns
        # that take a grammatically singular verb ("el resto no bucea") even
        # when they refer to several people — bias plural for these.
        if re.search(r"\b(?:el\s+resto|los\s+dem[aá]s|the\s+rest|the\s+others?)\b", query, re.IGNORECASE):
            return True, True
        return True, False
    elliptical = _NON_DIVER_ELLIPTICAL_ES_RE.search(query) or _NON_DIVER_ELLIPTICAL_EN_RE.search(query)
    if elliptical:
        matched = elliptical.group(0).lower()
        is_plural = any(w in matched for w in _NON_DIVER_ELLIPTICAL_PLURAL_WORDS)
        return True, is_plural
    return False, False


def _canonical_diving_overview_answer(query: str, lang: str) -> str | None:
    if _OVERVIEW_EXCLUDE.search(query):
        return None
    if not (_OVERVIEW_PHRASE.search(query) and _OVERVIEW_DIVING_WORD.search(query)):
        return None

    already_certified = _mentions_already_certified(query)
    has_companion, plural_companions = _detect_companion_mention(query)

    if lang == "es":
        intro = (
            "🌊 *Buceamos en las Islas del Rosario* (Parque Nacional Corales del Rosario), "
            "a 45–60 min en lancha desde Cartagena: aguas cálidas, arrecifes y mucha vida marina. "
        )
        if already_certified:
            intro = "¡Qué bien que ya seas buzo certificado! 🤿 " + intro
        intro += "Te resumo las opciones:\n\n"

        blocks = {
            "beginner": (
                "🆕 *¿Nunca has buceado?* → el *Minicurso de buceo* (bautismo): teoría, práctica en "
                "piscina y una inmersión en el mar con instructor. Desde los 10 años."
            ),
            "certified": (
                "🤿 *¿Ya eres buzo certificado?* → *paquetes de inmersiones*: 2 buceos en 1 día, o "
                "planes multi-día (4, 5, 7 o 9 buceos)."
            ),
            "course": (
                "🎓 *¿Quieres sacarte el título?* → *cursos PADI*: Open Water (el básico), Advanced, "
                "Rescue, Divemaster y especialidades."
            ),
            "snorkel": (
                "🐠 Y si prefieres sin bucear, el *snorkel* es una chulada para ver el arrecife desde "
                "la superficie."
            ),
        }
        order = ("certified", "course", "snorkel", "beginner") if already_certified else (
            "beginner", "certified", "course", "snorkel"
        )
        body = "\n\n".join(blocks[k] for k in order)

        if plural_companions:
            companion_line = (
                "\n\n👥 *¿Tus acompañantes no bucean?* También tienen opciones: pueden hacer el "
                "*minicurso* si quieren probar, ir de *snorkel*, o simplemente acompañarte en "
                "la lancha sin bucear."
            )
        elif has_companion:
            companion_line = (
                "\n\n👥 *¿Tu acompañante no bucea?* También tiene opciones: puede hacer el "
                "*minicurso* si quiere probar, ir de *snorkel*, o simplemente acompañarte en "
                "la lancha sin bucear."
            )
        else:
            companion_line = ""
        outro = "\n\n¿Cuál te llama? Si quieres te armo la reserva. 😄"
        return intro + body + companion_line + outro + _CANONICAL_SAFETY_NET["es"]

    intro = (
        "🌊 *We dive in the Rosario Islands* (Corales del Rosario National Park), 45–60 min by boat "
        "from Cartagena: warm water, reefs and lots of marine life. "
    )
    if already_certified:
        intro = "Great to hear you're already a certified diver! 🤿 " + intro
    intro += "Here's a quick overview:\n\n"

    blocks_en = {
        "beginner": (
            "🆕 *Never dived before?* → the *Dive Mini-Course* (Discover Scuba): theory, pool practice "
            "and one open-water dive with an instructor. From age 10."
        ),
        "certified": (
            "🤿 *Already a certified diver?* → *dive packages*: 2 dives in 1 day, or multi-day plans "
            "(4, 5, 7 or 9 dives)."
        ),
        "course": (
            "🎓 *Want to get certified?* → *PADI courses*: Open Water (the basic one), Advanced, "
            "Rescue, Divemaster and specialties."
        ),
        "snorkel": (
            "🐠 And if you'd rather not dive, *snorkeling* is a lovely way to see the reef from the "
            "surface."
        ),
    }
    order = ("certified", "course", "snorkel", "beginner") if already_certified else (
        "beginner", "certified", "course", "snorkel"
    )
    body = "\n\n".join(blocks_en[k] for k in order)

    if plural_companions:
        companion_line = (
            "\n\n👥 *If your companions don't dive*, they've got options too: they can try the "
            "*mini-course*, go snorkeling, or simply come along on the boat without diving."
        )
    elif has_companion:
        companion_line = (
            "\n\n👥 *If your companion doesn't dive*, they've got options too: they can try the "
            "*mini-course*, go snorkeling, or simply come along on the boat without diving."
        )
    else:
        companion_line = ""
    outro = "\n\nWhich one sounds good? I can put the booking together for you. 😄"
    return intro + body + companion_line + outro + _CANONICAL_SAFETY_NET["en"]


# A GENERIC price question ("¿cuánto cuesta?", "precios?", "how much?") with no
# specific service named. RAG used to deflect with "no info" or a question back;
# instead give a short price overview of the main services (pulled from SERVICES
# so it stays current). A price question that DOES name a service ("cuánto cuesta
# el minicurso") is left to RAG, which answers it well.
_PRICE_QUESTION = re.compile(
    r"\b(?:cu[aá]nto\s+(?:cuesta|cuestan|vale|valen|sale|salen|es|ser[ií]a)|"
    r"cu[aá]nto|precios?|qu[eé]\s+precios?|tarifas?|how\s+much|prices?|cost)\b",
    re.IGNORECASE,
)
_PRICE_SPECIFIC = re.compile(
    r"\b(?:minicurso|mini\s?curso|snorkel\w*|open\s*water|advanced|rescue|"
    r"divemaster|nitrox|especialidad|comida|almuerzo|acompa\w+|companion|"
    r"noche|nocturn\w+|paquetes?|referido|referral|fish|peces|flotabilidad|buoyancy|"
    r"naturalista|naturalist|vuelo|hotel|"
    # Multi-day pricing ("paquetes multidía", "varios días", "multi-day") is
    # its own specific question — the canonical overview below only mentions
    # it in passing without real prices, so it must fall through to RAG
    # (which retrieves the actual per-package multi-day pricing FAQ). Found
    # missing 2026-07-16: bare "paquete" (singular, no wildcard) never matched
    # the plural "paquetes" either, so "los paquetes multidía" slipped past
    # this exclusion entirely and got the generic single-day-only summary.
    r"multi[\s\-]?d[ií]as?|varios\s+d[ií]as|\d\s*(?:d[ií]as|dives?|inmersi\w+)|"
    r"multi[\s\-]?day)\b",
    re.IGNORECASE,
)


def _fmt_price_usd(v) -> str:
    try:
        return f"${int(round(float(v)))}"
    except (TypeError, ValueError):
        return "consultar"


def _fmt_price_cop(v) -> str:
    try:
        return f"{int(v):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "consultar"


def _canonical_price_overview_answer(query: str, lang: str) -> str | None:
    if not _PRICE_QUESTION.search(query):
        return None
    if _PRICE_SPECIFIC.search(query):
        return None  # names a specific service -> let RAG answer it precisely
    # A price question that also carries a group/cert booking is not a plain
    # "what are the prices?" — let the flow/RAG handle it.
    if _FOOD_HIJACK_GUARD.search(query):
        return None
    try:
        from src.flows.decision_tree import SERVICES
    except Exception:
        return None
    svc = {k: SERVICES.get(k, {}) for k in ("2_dives_1_day", "minicourse", "snorkeling", "open_water")}

    def line(usd, cop):
        return f"{_fmt_price_usd(usd)} USD / {_fmt_price_cop(cop)} COP"

    cert = svc["2_dives_1_day"]
    mini = svc["minicourse"]
    snk = svc["snorkeling"]
    ow = svc["open_water"]
    if lang == "es":
        return (
            "🌊 Te dejo los *precios de referencia saliendo desde Cartagena* "
            "(incluyen lancha, almuerzo, equipo y entrada al parque), con el descuento por reservar online:\n\n"
            f"🤿 *Buceo certificado* (2 inmersiones, 1 día): *{line(cert.get('price_usd'), cert.get('price_cop'))}* por persona.\n"
            f"🆕 *Minicurso de buceo* (sin experiencia): *{line(mini.get('price_usd'), mini.get('price_cop'))}* por persona.\n"
            f"🐠 *Snorkel*: *{line(snk.get('price_usd'), snk.get('price_cop'))}* por persona.\n"
            f"🎓 *Curso Open Water* (certificación PADI): *{line(ow.get('price_usd'), ow.get('price_cop'))}*.\n\n"
            "Los colombianos/residentes pagan en pesos (COP) y los internacionales en dólares (USD) — "
            "mismo precio, sin cobro extra por la divisa. También hay paquetes multi-día (4/5/7/9 inmersiones) "
            "y otros cursos. ¿Cuál te interesa? 😄"
        ) + _CANONICAL_SAFETY_NET["es"]
    return (
        "🌊 Here are the *reference prices departing from Cartagena* "
        "(they include the boat, lunch, gear and park entrance), with the online-booking discount:\n\n"
        f"🤿 *Certified diving* (2 dives, 1 day): *{line(cert.get('price_usd'), cert.get('price_cop'))}* per person.\n"
        f"🆕 *Dive mini-course* (no experience): *{line(mini.get('price_usd'), mini.get('price_cop'))}* per person.\n"
        f"🐠 *Snorkeling*: *{line(snk.get('price_usd'), snk.get('price_cop'))}* per person.\n"
        f"🎓 *Open Water course* (PADI certification): *{line(ow.get('price_usd'), ow.get('price_cop'))}*.\n\n"
        "Colombians/residents pay in pesos (COP) and international guests in dollars (USD) — same price, "
        "no extra charge for the currency. There are also multi-day packages (4/5/7/9 dives) and other "
        "courses. Which one are you interested in? 😄"
    ) + _CANONICAL_SAFETY_NET["en"]


def _coerce_metadata(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _score_for_threshold(doc: dict) -> float:
    raw_score = doc.get("score_final", doc.get("score", 0.0))
    try:
        return float(raw_score)
    except (TypeError, ValueError):
        return 0.0


def _is_confident(doc: dict) -> bool:
    """Decide whether a retrieved doc is a confident match.

    Hybrid retrieval mixes a dense cosine score (0-1) with a normalized BM25
    score whose top value is always 1.0, so the combined ``score_final`` cannot
    be compared against a fixed threshold. Gate each signal on its own scale:

    - vector hits: cosine >= ``rag_min_score``
    - lexical hits: raw ts_rank_cd >= ``rag_min_bm25_rank``

    Docs without branch scores (test fixtures / legacy shape) fall back to the
    generic ``score`` against ``rag_min_score``.
    """
    has_branch_scores = ("score_vector" in doc) or ("score_bm25_raw" in doc)
    if has_branch_scores:
        try:
            vector_score = float(doc.get("score_vector", 0.0) or 0.0)
        except (TypeError, ValueError):
            vector_score = 0.0
        try:
            bm25_raw = float(doc.get("score_bm25_raw", 0.0) or 0.0)
        except (TypeError, ValueError):
            bm25_raw = 0.0
        return vector_score >= settings.rag_min_score or bm25_raw >= settings.rag_min_bm25_rank

    try:
        return float(doc.get("score", 0.0) or 0.0) >= settings.rag_min_score
    except (TypeError, ValueError):
        return False


async def _expand_with_parent_context(docs: list[dict], lang: str) -> list[dict]:
    parent_ids_needed: set[str] = set()
    existing_keys = {
        str((doc.get("metadata") or {}).get("key"))
        for doc in docs
        if (doc.get("metadata") or {}).get("key")
    }
    parent_scores: dict[str, float] = {}

    for doc in docs:
        metadata = doc.get("metadata") or {}
        parent_id = metadata.get("parent_id")
        key = metadata.get("key")
        if not parent_id or parent_id == key or parent_id in existing_keys:
            continue
        parent_key = str(parent_id)
        parent_ids_needed.add(parent_key)
        parent_scores[parent_key] = max(parent_scores.get(parent_key, 0.0), _score_for_threshold(doc))

    if not parent_ids_needed:
        return docs

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, content, metadata
                FROM kb_documents
                WHERE metadata->>'lang' = $1
                  AND metadata->>'key' = ANY($2::text[])
                """,
                lang,
                list(parent_ids_needed),
            )
    except Exception as exc:
        logger.warning(f"[RAG][PARENT] failed to expand parent context: {exc}")
        return docs

    parents: list[dict] = []
    seen_parent_keys: set[str] = set()
    for row in rows:
        metadata = _coerce_metadata(row["metadata"])
        parent_key = str(metadata.get("key") or "")
        if not parent_key or parent_key in seen_parent_keys:
            continue
        seen_parent_keys.add(parent_key)
        score = parent_scores.get(parent_key, 0.0)
        parents.append({
            "id": row["id"],
            "content": row["content"],
            "metadata": metadata,
            "score": score,
            "score_final": score,
        })

    if not parents:
        return docs
    return parents + docs


def _build_grounding_context(
    context: str,
    extra_context: str | None = None,
    history: list[dict] | None = None,
) -> str:
    """Assemble everything the grounding check is allowed to treat as truth.

    Without the conversation history, a perfectly accurate answer that just
    confirms something the BOT ITSELF already said earlier (e.g. "menores de
    8 solo pueden hacer snorkel, min. 6 anos" stated a few turns ago in the
    kids-age question) gets rejected as "ungrounded" because that fact isn't
    in the freshly retrieved docs/extra_context — even though it's exactly
    what the client is asking to confirm. Only the bot's OWN prior messages
    are included (not the client's), since those came from deterministic tree
    templates / KB data, not free-form guesses.
    """
    parts = [context] if context else []
    if extra_context and context != extra_context:
        parts.append(f"Contexto adicional de la situacion: {extra_context}")
    if history:
        prior_bot_messages = [
            turn.get("content", "")
            for turn in history[-12:]
            if turn.get("role") == "assistant" and turn.get("content")
        ]
        if prior_bot_messages:
            parts.append(
                "Mensajes que el propio bot ya envio antes en esta conversacion "
                "(puedes usarlos para confirmar datos que ya mencionaste):\n"
                + "\n---\n".join(prior_bot_messages)
            )
    return "\n\n".join(parts)


async def _verify_grounding_with_retry(answer: str, context: str, lang: str) -> tuple[bool, str]:
    grounded, reason = await is_grounded(answer, context, lang=lang)
    if grounded:
        return True, reason
    grounded_retry, reason_retry = await is_grounded(answer, context, lang=lang)
    if grounded_retry:
        return True, f"{reason}|retry:{reason_retry}"
    return False, f"{reason}|retry:{reason_retry}"


async def rag_answer(
    query: str,
    lang: str = "es",
    history: list[dict] | None = None,
    extra_context: str | None = None,
    verify_grounding: bool = True,
) -> str:
    """`verify_grounding=False` keeps the deterministic price/URL guards but skips
    the LLM grounding-judge, which false-negatives on correct answers that combine
    several KB chunks (e.g. a full course program). Used by the conversation agent
    so it can answer multi-part questions naturally; RAG defaults stay strict."""
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
        logger.info(f"[RAG][CANONICAL_SHORTCUT] shortcut=food query={query!r} lang={lang}")
        return canonical_food_answer

    diving_overview = _canonical_diving_overview_answer(query, lang)
    if diving_overview:
        logger.info(f"[RAG][CANONICAL_SHORTCUT] shortcut=diving_overview query={query!r} lang={lang}")
        return diving_overview

    price_overview = _canonical_price_overview_answer(query, lang)
    if price_overview:
        logger.info(f"[RAG][CANONICAL_SHORTCUT] shortcut=price_overview query={query!r} lang={lang}")
        return price_overview

    condensed_query = await condense_query(query, history=history, lang=lang)
    ambiguous_location_clarification = _ambiguous_location_clarification(condensed_query, lang)
    if ambiguous_location_clarification:
        logger.info(f"[RAG][CANONICAL_SHORTCUT] shortcut=ambiguous_location query={query!r} lang={lang}")
        return ambiguous_location_clarification

    retrieval_query = build_retrieval_query(condensed_query, history)

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

    # Retrieve relevant documents (parent expansion happens later, only if confident)
    docs = await search_knowledge_base(safe_query, lang=lang)

    # Helper to call the LLM with unstructured context (either KB docs o solo extra_context)
    async def _answer_with_llm(
        context: str,
        context_sources: list[str] | None = None,
        require_grounding: bool = False,
    ) -> str:
        """`require_grounding=True` forces the LLM grounding judge even when the
        caller passed `verify_grounding=False`. Used by the "no confident KB
        docs, answer from extra_context only" escape hatches below: there the
        model has NO knowledge-base support, so without the judge it happily
        answers a factual question from its own world knowledge (e.g. inventing
        a list of fish species). The judge is the only thing standing between
        that and the customer."""
        system_prompt = build_system_prompt(lang, query=condensed_query)
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history (last 12 messages max, to keep a longer thread)
        if history:
            for msg in history[-12:]:
                messages.append({"role": msg["role"], "content": redact_pii(msg["content"])})

        user_content = f"Contexto:\n{context}"
        if extra_context and context != extra_context:
            # Si ya tenemos contexto KB y ademas extra_context, lo anexamos explicito
            user_content += f"\n\nContexto adicional de la situacion: {extra_context}"
        user_content += f"\n\nPregunta del cliente: {redact_pii(query)}"

        messages.append({"role": "user", "content": user_content})

        grounding_context = _build_grounding_context(context, extra_context=extra_context, history=history)
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        fallback = FALLBACK_ES if lang == "es" else FALLBACK_EN

        # The answer is sampled at temperature 0.3, so it varies run to run. A
        # one-off answer that embellishes a detail trips the grounding judge and,
        # before, went straight to the "no info" fallback — the source of the
        # intermittent (~1/3) false fallbacks. We now REGENERATE the answer once
        # when any guard rejects: a fresh sample is usually grounded, turning a
        # false fallback into a real answer. Only fall back if both tries fail.
        last_reject = ""
        for attempt in range(2):
            try:
                response = await client.chat.completions.create(
                    model=settings.openai_model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=500,
                )
            except Exception as exc:
                logger.warning(f"[RAG][LLM] failed to answer query={query[:60]}... error={exc}")
                return fallback

            answer = response.choices[0].message.content or ""

            # Deterministic guards first: never let a price/%/URL not in the
            # context reach the customer (e.g. "$180" when the real price is "$178").
            if not currency_amounts_grounded(answer, grounding_context):
                last_reject = "ungrounded_amount"
            elif not urls_grounded(answer, grounding_context):
                last_reject = "ungrounded_url"
            elif not capacity_claims_grounded(answer, grounding_context):
                last_reject = "ungrounded_capacity"
            elif requests_personal_data(answer):
                # Never run a manual booking ritual in chat (names/ID/passport):
                # bookings close with the online link or an advisor handoff.
                last_reject = "requests_personal_data"
            elif not verify_grounding and not require_grounding:
                return answer
            else:
                grounded, reason = await _verify_grounding_with_retry(answer, grounding_context, lang=lang)
                if grounded:
                    logger.info(
                        f"[RAG] Query: {query[:60]}... | Docs: {len(docs) if docs else 0} | "
                        f"Tokens: {response.usage.total_tokens} | Sources: {context_sources or []}"
                    )
                    return answer
                last_reject = reason
            logger.info(f"[RAG][GROUNDING] attempt {attempt + 1} rejected ({last_reject}) query={query[:50]}...")

        logger.warning(
            f"[RAG][GROUNDING] Rejecting after 2 attempts query={query[:60]}... reason={last_reject}"
        )
        return fallback

    # 1) Sin documentos del KB
    if not docs:
        logger.info(f"[RAG] No docs found query={query[:60]}...")
        if extra_context:
            # No hay nada util en el KB, pero si tenemos resumen de estado: dejamos que el LLM
            # razone SOLO con ese contexto en lugar de ir directo al fallback.
            # El juez de grounding es OBLIGATORIO aqui (require_grounding): sin
            # soporte del KB, el modelo responderia de su conocimiento propio.
            return await _answer_with_llm(
                extra_context, context_sources=["extra_context_only"], require_grounding=True
            )
        return FALLBACK_ES if lang == "es" else FALLBACK_EN

    # 2) Hay documentos pero ninguno con confianza suficiente
    if not any(_is_confident(doc) for doc in docs):
        sources = [doc.get("metadata", {}).get("source", "unknown") for doc in docs]
        top_score = max((_score_for_threshold(doc) for doc in docs), default=0.0)
        logger.info(
            f"[RAG] Low confidence query={query[:60]}... retrieval_query={safe_query[:120]}... "
            f"top_score={top_score:.3f} min_cosine={settings.rag_min_score:.3f} "
            f"min_bm25={settings.rag_min_bm25_rank:.3f} sources={sources}"
        )
        if extra_context:
            # Igual que en el caso sin docs: ignoramos estos resultados de baja confianza
            # y dejamos que el LLM trabaje solo con el contexto de estado, pero con
            # el juez de grounding SIEMPRE activo (ver require_grounding arriba).
            return await _answer_with_llm(
                extra_context, context_sources=["extra_context_only"], require_grounding=True
            )
        return FALLBACK_ES if lang == "es" else FALLBACK_EN

    # 3) Hay documentos suficientemente relevantes -> expandimos contexto padre y respondemos
    docs = await _expand_with_parent_context(docs, lang=lang)
    context_parts = []
    sources = []
    for i, doc in enumerate(docs, 1):
        metadata = doc.get("metadata", {})
        source = metadata.get("source", "unknown")
        sources.append(source)
        # "conversations" docs describe a DIFFERENT customer's past situation (see
        # scripts/load_embeddings.py). Label them explicitly so the LLM never
        # mistakes their facts (family, companions, budget) for the current
        # customer's — defense in depth alongside stripping their literal quotes
        # at indexing time (T113 in docs/test-battery-edge-cases.md).
        source_label = (
            f"{source} (situacion de otro cliente distinto, no es el cliente actual)"
            if source == "conversations"
            else source
        )
        context_parts.append(f"[{i}] Fuente: {source_label}\n{redact_pii(doc['content'])}")
    context = "\n\n".join(context_parts)

    return await _answer_with_llm(context, context_sources=sources)
