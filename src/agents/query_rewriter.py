import logging

from openai import AsyncOpenAI

from src.config import settings
from src.llm_client import trace_openai
from src.observability import con_pieza_llm
from src.privacy import redact_pii
from src.prompts.info import QUERY_REWRITE_EN, QUERY_REWRITE_ES

logger = logging.getLogger("uvicorn.error")


# CAL-D (16-oct, flag `consulta_con_lo_sabido`): lo que se le añade al reescritor para que la consulta nombre el
# asunto. Es una regla para TODAS las preguntas, no para un caso: una consulta con una elipsis no se puede buscar.
_NOMBRA_EL_ASUNTO_ES = (
    "IMPORTANTE: la consulta tiene que NOMBRAR de qué va la pregunta, con lo que diga la conversación y lo que ya "
    "sabemos del cliente: la actividad o el plan, desde dónde sale y si es buzo certificado, cuando consten. Una "
    "consulta que deja una elipsis o un pronombre ('por día', 'ese', 'en concepto', 'y el otro') NO es "
    "autosuficiente: escríbela entera. No inventes datos que no consten."
)
_NOMBRA_EL_ASUNTO_EN = (
    "IMPORTANT: the query must NAME what the question is about, using the conversation and what we already know "
    "about the customer: the activity or plan, where they depart from and whether they are a certified diver, when "
    "those are known. A query that keeps an ellipsis or a pronoun ('per day', 'that one', 'the concept', 'and the "
    "other') is NOT self-contained: write it out in full. Do not invent facts that are not there."
)


def _should_condense(query: str, history: list[dict] | None) -> bool:
    if not query or not history:
        return False
    if len(query.split()) >= 8:
        return False
    # A single prior user turn is enough to condense a follow-up — a 2-turn
    # conversation (1 Q + 1 follow-up) only has 1 user message in history.
    user_msgs = [m for m in history if m.get("role") == "user"]
    return len(user_msgs) >= 1


def _format_history_for_prompt(history: list[dict], lang: str, max_turns: int = 4) -> str:
    customer_label = "Cliente" if lang == "es" else "Customer"
    advisor_label = "Asesor" if lang == "es" else "Advisor"
    lines: list[str] = []
    for msg in history[-max_turns:]:
        content = redact_pii((msg.get("content") or "").strip())
        if not content:
            continue
        role = customer_label if msg.get("role") == "user" else advisor_label
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def lo_sabido(hechos: dict | None, lang: str) -> str:
    """CAL-D (16-oct): lo que ya sabemos del cliente en campos ESTRUCTURADOS del estado (los mismos hechos que eligen
    los avisos), en una línea, para que la consulta de búsqueda nombre de qué va la pregunta. Vacío si no se sabe nada.

    Medido con `scripts/sonda_senales.py`: el reescritor dejaba "And how much is per a day" en "How much is the price
    per day?" (gramática, no contenido), y la búsqueda traía la política del segundo día y los paquetes de varios días
    en vez de la ficha del plan de un día. El dato que faltaba (un día de buceo, desde Cartagena, buzo certificado) ya
    estaba en el estado."""
    if not hechos:
        return ""
    partes: list[str] = []
    actividades = sorted(hechos.get("actividades") or [])
    if actividades:
        partes.append(("actividad: " if lang == "es" else "activity: ") + ", ".join(actividades))
    origen = hechos.get("origen")
    if origen:
        desde = {"cartagena": "sale desde Cartagena", "island": "ya está en las Islas del Rosario"}.get(origen) \
            if lang == "es" else {"cartagena": "departs from Cartagena",
                                  "island": "is already on the Rosario Islands"}.get(origen)
        if desde:
            partes.append(desde)
    nacionalidad = hechos.get("nacionalidad")
    if nacionalidad:
        partes.append(("nacionalidad: " if lang == "es" else "nationality: ") + nacionalidad)
    return "; ".join(partes)


@con_pieza_llm("reescritura")
async def condense_query(
    query: str,
    history: list[dict] | None = None,
    lang: str = "es",
    hechos: dict | None = None,
) -> str:
    if not _should_condense(query, history):
        return query

    system = QUERY_REWRITE_ES if lang == "es" else QUERY_REWRITE_EN
    sabido = lo_sabido(hechos, lang) if settings.consulta_con_lo_sabido else ""
    if settings.consulta_con_lo_sabido:
        # CAL-D: la consulta tiene que NOMBRAR el asunto. Sin esto, el reescritor arregla la frase y deja la elipsis
        # ("per day", "en concepto"), que es justo lo que la búsqueda no sabe buscar.
        system = f"{system} {_NOMBRA_EL_ASUNTO_ES if lang == 'es' else _NOMBRA_EL_ASUNTO_EN}"
    history_block = _format_history_for_prompt(history or [], lang=lang)
    safe_query = redact_pii(query)

    if lang == "es":
        user_content = (
            f"Conversacion previa:\n{history_block}\n\n"
            + (f"Lo que ya sabemos del cliente: {sabido}\n\n" if sabido else "")
            + f"Pregunta a reescribir: {safe_query}"
        )
    else:
        user_content = (
            f"Prior conversation:\n{history_block}\n\n"
            + (f"What we already know about the customer: {sabido}\n\n" if sabido else "")
            + f"Question to rewrite: {safe_query}"
        )

    try:
        client = trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=80,
        )
        rewritten = (response.choices[0].message.content or "").strip()
        if not rewritten:
            return query
        logger.info(
            f"[RAG][REWRITE] original={safe_query[:40]}... rewritten={rewritten[:60]}..."
        )
        return rewritten
    except Exception as exc:
        logger.warning(f"[RAG][REWRITE] failed, using original query: {exc}")
        return query
