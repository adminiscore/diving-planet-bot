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
from src.prompts.memory import NOTES_TOOL, notes_system_prompt

logger = logging.getLogger("uvicorn.error")


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

    messages: list[dict] = [{"role": "system", "content": notes_system_prompt(lang, existing)}]
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
            tools=[NOTES_TOOL],
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
