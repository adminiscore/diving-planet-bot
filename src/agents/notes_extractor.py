"""Fase C del plan de memoria (docs/future/decision-tree-reorg.md §2) —
re-cableado al núcleo (2026-07-28, decisión owner: con LLM).

Captura "hechos abiertos" (notes) que un asesor de buceo querría recordar y que
NO encajan en los slots estructurados del núcleo (actividad, grupo, ubicación,
certificación, fechas): condiciones médicas/lesiones, necesidades de
accesibilidad, restricciones alimentarias, ocasiones especiales (aniversario,
luna de miel, cumpleaños) y restricciones duras (agenda/presupuesto ajustados).

Corre ALONGSIDE del slot-filling; nunca lo reemplaza. `extract_notes()` devuelve
solo las notas NUEVAS (las que no están ya en `existing_notes`). En cualquier
error/timeout/respuesta malformada devuelve `[]` — un fallo aquí nunca puede
romper el turno (mismo principio que `llm_extractor.fill_gaps`).

El escritor del núcleo (`conversational_core._maybe_capture_notes`) persiste el
resultado en `state.remembered_facts["notes"]`, que ya se renderiza en
`supervisor._build_extra_context` (contexto del LLM) y en la nota de lead del
asesor. Antes de Fase 4 esto lo hacía la tool `remember` del orquestador
(borrada con el orquestador); este módulo la sustituye.
"""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger("uvicorn.error")

_TOOL = {
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


def _system_prompt(lang: str, existing_notes: list[str]) -> str:
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


async def extract_notes(
    message: str,
    *,
    history: list[dict] | None = None,
    existing_notes: list[str] | None = None,
    lang: str = "es",
    client: AsyncOpenAI | None = None,
) -> list[str]:
    """Return NEW open-fact notes from `message` (not already in
    `existing_notes`). On any error/timeout/malformed response returns [] so a
    failure here never breaks the turn."""
    if not message or not message.strip():
        return []
    existing = existing_notes or []
    existing_lower = {n.strip().lower() for n in existing}

    messages: list[dict] = [{"role": "system", "content": _system_prompt(lang, existing)}]
    for turn in (history or [])[-settings.history_retrieval_enrichment_window:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    try:
        client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.extraction_model,
            messages=messages,
            tools=[_TOOL],
            tool_choice={"type": "function", "function": {"name": "capture_notes"}},
            temperature=0.0,
            max_tokens=200,
        )
        choice = response.choices[0].message
        tool_calls = getattr(choice, "tool_calls", None)
        if not tool_calls:
            return []
        args = json.loads(tool_calls[0].function.arguments or "{}")
    except (json.JSONDecodeError, TypeError, AttributeError, IndexError) as exc:
        logger.warning(f"[NOTES_EXTRACTOR] malformed response: {exc}")
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[NOTES_EXTRACTOR] error: {exc}")
        return []

    raw = (args or {}).get("notes") or []
    if not isinstance(raw, list):
        return []
    # Keep only real, new, deduped strings.
    out: list[str] = []
    seen = set(existing_lower)
    for n in raw:
        if not isinstance(n, str):
            continue
        n = n.strip()
        key = n.lower()
        if n and key not in seen:
            out.append(n)
            seen.add(key)
    if out:
        logger.info(f"[NOTES_EXTRACTOR] captured={out} msg={message[:60]!r}")
    return out
