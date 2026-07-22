"""
LLM-based intent classifier for free-text messages inside menu steps.

When the customer is in a menu step and types free text that does not match a
button (digit, exact value, fuzzy title), this classifier maps the message to
either a button value, a navigation action, or a "RAG" fallback.

Used to make the cart-style mixed-group flow feel natural: "quiero añadir otro"
maps to the cart "add" action; "en pesos" maps to currency_switch_cop.
"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger("uvicorn.error")

# Reserved action values returned by the classifier
ACTION_RAG = "RAG"
ACTION_BACK = "back"
ACTION_RESTART = "restart"
ACTION_CURRENCY_COP = "currency_switch_cop"
ACTION_CURRENCY_USD = "currency_switch_usd"

_RESERVED_ACTIONS = {ACTION_RAG, ACTION_BACK, ACTION_RESTART,
                     ACTION_CURRENCY_COP, ACTION_CURRENCY_USD}


def _build_prompt(message: str, step_name: str, button_options: list[dict], lang: str) -> str:
    options_lines = []
    for opt in button_options:
        title = opt.get("title", "")
        value = opt.get("value", "")
        options_lines.append(f'  - "{value}": {title}')
    options_lines.append('  - "back": volver / cancelar')
    options_lines.append('  - "restart": empezar de nuevo / reset')
    options_lines.append('  - "currency_switch_cop": ver precio en pesos colombianos')
    options_lines.append('  - "currency_switch_usd": ver precio en dolares')

    if lang == "es":
        return (
            "Eres un clasificador de intención para un bot de menú de Diving Planet.\n"
            f"El usuario está en el paso: {step_name}\n"
            "Opciones disponibles:\n"
            + "\n".join(options_lines)
            + f'\n\nMensaje del usuario: "{message}"\n\n'
            "Responde SOLO con el valor exacto de la opción que mejor coincida.\n"
            'Si el mensaje es una pregunta abierta que requiere búsqueda, responde "RAG".\n'
            "No escribas ninguna explicación, solo el valor."
        )
    return (
        "You are an intent classifier for a Diving Planet menu bot.\n"
        f"User is on step: {step_name}\n"
        "Available options:\n"
        + "\n".join(options_lines)
        + f'\n\nUser message: "{message}"\n\n'
        "Reply with ONLY the exact value of the option that best matches.\n"
        'If the message is an open question that requires search, reply "RAG".\n'
        "No explanation, just the value."
    )


async def classify_menu_intent(
    message: str,
    step_name: str,
    button_options: list[dict],
    lang: str = "es",
) -> str:
    """
    Classify a free-text message into a button value or reserved action.

    Returns one of:
      - a button value present in `button_options`
      - "back", "restart"
      - "currency_switch_cop", "currency_switch_usd"
      - "RAG" (no match, route to retrieval)
    """
    if not message or not message.strip():
        return ACTION_RAG

    prompt = _build_prompt(message, step_name, button_options, lang)
    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=20,
        )
        raw = (response.choices[0].message.content or "").strip()
        # Strip surrounding quotes / punctuation
        raw = raw.strip('"').strip("'").strip().strip(".").strip()
        logger.info(
            f"[INTENT] step={step_name} msg={message[:40]!r} -> {raw!r}"
        )

        # Validate the returned action
        valid_values = {opt.get("value") for opt in button_options if opt.get("value")}
        valid_values |= _RESERVED_ACTIONS

        if raw in valid_values:
            return raw
        # Try a lowercase / case-insensitive match
        for v in valid_values:
            if v and raw.lower() == v.lower():
                return v
        logger.info(f"[INTENT] unrecognized response {raw!r} -> RAG fallback")
        return ACTION_RAG
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[INTENT] classifier error: {exc} -> RAG fallback")
        return ACTION_RAG
