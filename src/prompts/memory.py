"""Prompts de **memoria** — transversales (`docs/agent-arch-design.md` §7).

- `NOTES_TOOL` · `notes_system_prompt` — `notes_extractor.extract_notes`, que
  el subgrafo de booking invoca en la fase `setup`: captura "hechos abiertos"
  (condiciones médicas, accesibilidad, dieta, ocasiones especiales,
  restricciones duras) que NO son slots de la reserva.
- `SUMMARY_SYSTEM_*` — `conversation_summarizer.maybe_update_summary`, que
  corre post-turno en `route_message`: resumen rodante de la conversación.

La Fase 4.3 del plan unifica esta memoria en el `BotState`; los prompts ya
viven aquí para que ese paso mueva cableado, no texto.
"""

from __future__ import annotations

# ── Hechos abiertos (notes) · `notes_extractor.extract_notes` ───────────────

NOTES_TOOL = {
    "type": "function",
    "function": {
        "name": "capture_notes",
        "description": (
            "Capture durable, open facts about the customer that a scuba diving "
            "advisor would want to remember, that do NOT fit the structured "
            "booking fields (activity, group size, location, dates, "
            "certification, nationality). Examples worth capturing: medical "
            "conditions or injuries ('father has an operated knee'), "
            "accessibility needs, dietary restrictions, special occasions "
            "(anniversary, honeymoon, birthday), and hard constraints (very "
            "tight schedule, limited budget). Return an EMPTY list if the "
            "message has none — never invent, never restate the booking slots, "
            "and never capture plain questions or greetings."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "notes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Short, self-contained note phrases (max ~12 words each) "
                        "in the customer's language. Empty if nothing relevant."
                    ),
                }
            },
            "required": ["notes"],
        },
    },
}


def notes_system_prompt(lang: str, existing_notes: list[str]) -> str:
    already = ""
    if existing_notes:
        joined = "; ".join(existing_notes)
        already = (
            f" Ya tienes anotado (NO lo repitas): {joined}."
            if lang == "es"
            else f" Already noted (do NOT repeat): {joined}."
        )
    if lang == "es":
        return (
            "Eres una capa de memoria para un bot de buceo (Diving Planet, "
            "Cartagena/Islas del Rosario). Tu única tarea es capturar 'hechos "
            "abiertos' que un asesor querría recordar y que NO son datos de "
            "reserva (actividad, cuántos son, dónde, certificación, fechas): "
            "lesiones/condiciones médicas, accesibilidad, restricciones "
            "alimentarias, ocasiones especiales (aniversario, luna de miel, "
            "cumpleaños) o restricciones duras (agenda/presupuesto). Llama a "
            "`capture_notes` con SOLO lo que el mensaje diga de verdad; lista "
            "vacía si no hay nada. Nunca inventes ni repitas los datos de "
            "reserva." + already
        )
    return (
        "You are a memory layer for a scuba diving bot (Diving Planet, "
        "Cartagena/Rosario Islands). Your only job is to capture 'open facts' an "
        "advisor would want to remember that are NOT booking data (activity, "
        "group size, location, certification, dates): injuries/medical "
        "conditions, accessibility, dietary restrictions, special occasions "
        "(anniversary, honeymoon, birthday) or hard constraints "
        "(schedule/budget). Call `capture_notes` with ONLY what the message "
        "actually states; empty list if none. Never invent or restate the "
        "booking data." + already
    )


# ── Resumen rodante de la conversación · `conversation_summarizer.maybe_update_summary` ────

SUMMARY_SYSTEM_ES = (
    "Mantienes un resumen breve y factual de una conversación de reserva de "
    "buceo/snorkel entre un cliente y un asistente. Se te da el resumen "
    "anterior (puede estar vacío) y el tramo nuevo de conversación. Actualiza "
    "el resumen incorporando lo nuevo relevante, sin perder los detalles "
    "importantes del resumen anterior. Prioriza: composición del grupo, "
    "certificación, ubicación/hotel, preferencias o restricciones "
    "(salud, movilidad, horarios, presupuesto), decisiones ya tomadas y dudas "
    "ya resueltas. No inventes nada que no se haya dicho. Sé conciso (máximo "
    "unas 150 palabras). Responde SOLO con el resumen actualizado, sin "
    "prefijos ni explicaciones."
)


SUMMARY_SYSTEM_EN = (
    "You maintain a short, factual summary of a diving/snorkeling booking "
    "conversation between a customer and an assistant. You're given the "
    "previous summary (may be empty) and the new conversation segment. "
    "Update the summary incorporating relevant new information, without "
    "losing important details from the previous summary. Prioritize: group "
    "composition, certification, location/hotel, preferences or "
    "constraints (health, mobility, timing, budget), decisions already "
    "made, and questions already resolved. Don't invent anything that "
    "wasn't said. Be concise (about 150 words max). Respond ONLY with the "
    "updated summary, no prefixes or explanations."
)
