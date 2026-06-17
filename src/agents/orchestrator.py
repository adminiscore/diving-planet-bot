"""
Tool-calling orchestrator for free-text messages inside the cart-style mixed flow.

This is the Fase 2 piece of docs/conversation-orchestrator-plan.md. Instead of
only mapping free text to an existing on-screen button (the job of the legacy
`classify_menu_intent`), the orchestrator uses OpenAI function calling to pick a
*structured action* that the supervisor then executes deterministically against
the existing decision tree. This lets natural language actually change the tree
state ("estoy en las islas" -> set_location(island), "quita el snorkel" ->
remove_item(snorkel), "quiero reservarlo" -> checkout) instead of just chatting.

Design notes:
- The LLM never performs the booking itself; it only chooses an action + args.
- `answer_question` is the fall-through: the supervisor routes it to RAG.
- On any error/timeout the caller is expected to fall back to the legacy
  classifier so the bot degrades gracefully.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger("uvicorn.error")

# Canonical activity identifiers shared with the cart (`mixed_cart` item types).
ACTIVITY_VALUES = ["certified", "beginner", "snorkel", "course", "companion"]
# Map orchestrator activity names -> internal cart item `type`.
ACTIVITY_TO_CART_TYPE = {
    "certified": "cert",
    "beginner": "beginner",
    "snorkel": "snorkel",
    "course": "course",
    "companion": "companion",
}

# Tool names (also used as the decision.tool value).
TOOL_SET_LOCATION = "set_location"
TOOL_START_BOOKING = "start_booking"
TOOL_ADD_TO_CART = "add_to_cart"
TOOL_CART_ACTION = "cart_action"
TOOL_REMOVE_ITEM = "remove_item"
TOOL_SET_PROFILE = "set_profile"
TOOL_NOTE_LOGISTICS = "note_logistics"
TOOL_ESCALATE = "escalate"
TOOL_ANSWER_QUESTION = "answer_question"

ALL_TOOL_NAMES = {
    TOOL_SET_LOCATION,
    TOOL_START_BOOKING,
    TOOL_ADD_TO_CART,
    TOOL_CART_ACTION,
    TOOL_REMOVE_ITEM,
    TOOL_SET_PROFILE,
    TOOL_NOTE_LOGISTICS,
    TOOL_ESCALATE,
    TOOL_ANSWER_QUESTION,
}


# OpenAI function-calling tool schemas (see plan §3.2.2).
TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": TOOL_SET_LOCATION,
            "description": (
                "Set where the customer departs from / currently is. Use when the "
                "customer says things like 'estoy en las islas', 'salgo desde "
                "Cartagena', 'ya estoy en Isla Grande'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "string",
                        "enum": ["cartagena", "island"],
                        "description": "cartagena = departs from Cartagena; island = already on the Rosario Islands.",
                    }
                },
                "required": ["origin"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": TOOL_START_BOOKING,
            "description": (
                "Start / move into the booking cart for a given activity when the "
                "customer expresses intent to book or add an activity but no quantity "
                "is given yet (e.g. 'quiero reservar buceo', 'añade snorkel')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "activity": {
                        "type": "string",
                        "enum": ACTIVITY_VALUES,
                    }
                },
                "required": ["activity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": TOOL_ADD_TO_CART,
            "description": (
                "Add a specific quantity of an activity to the cart when the customer "
                "states a count (e.g. 'somos 3 certificados', 'añade 2 snorkel')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "activity": {"type": "string", "enum": ACTIVITY_VALUES},
                    "qty": {"type": "integer", "minimum": 1, "maximum": 99},
                },
                "required": ["activity", "qty"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": TOOL_CART_ACTION,
            "description": (
                "Perform a cart-level action: 'confirm' to checkout/reserve the cart, "
                "'add' to add another activity, 'modify' to edit quantities, 'remove' "
                "to open the remove menu, 'change_origin' to change departure point, "
                "'restart' to clear the cart and start over."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "confirm",
                            "add",
                            "modify",
                            "remove",
                            "change_origin",
                            "restart",
                        ],
                    }
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": TOOL_REMOVE_ITEM,
            "description": (
                "Remove a specific activity from the cart directly by name, e.g. "
                "'quita el snorkel', 'elimina el curso'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "activity": {"type": "string", "enum": ACTIVITY_VALUES},
                },
                "required": ["activity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": TOOL_SET_PROFILE,
            "description": (
                "Record a boolean profile fact stated by the customer: whether they "
                "are a certified diver, whether they are Colombian (local pricing), or "
                "whether they want a refresher."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": ["certified", "colombian", "refresher"],
                    },
                    "value": {"type": "boolean"},
                },
                "required": ["field", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": TOOL_NOTE_LOGISTICS,
            "description": (
                "Record logistics details the customer mentions so they reach the "
                "advisor: hotel name, island name, whether they want pickup, or whether "
                "they want a private boat. Only include fields explicitly mentioned."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "hotel": {"type": "string"},
                    "island": {"type": "string"},
                    "wants_pickup": {"type": "boolean"},
                    "wants_private_boat": {"type": "boolean"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": TOOL_ESCALATE,
            "description": (
                "Escalate to a human advisor for medical concerns, real-time "
                "availability, complaints, payments, or anything the bot must not "
                "handle on its own."
            ),
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": TOOL_ANSWER_QUESTION,
            "description": (
                "The message is an informational question (prices, what's included, "
                "schedules, policies, etc.) that should be answered from the knowledge "
                "base. Use this whenever no concrete tree action is required."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


@dataclass
class OrchestratorDecision:
    """Structured result of an orchestrator call."""

    tool: str = TOOL_ANSWER_QUESTION
    args: dict = field(default_factory=dict)
    # Raw text the model may have produced alongside / instead of a tool call.
    raw_text: str | None = None

    @property
    def is_answer(self) -> bool:
        return self.tool == TOOL_ANSWER_QUESTION


def _system_prompt(lang: str, state_snapshot: str | None) -> str:
    rules_es = (
        "Eres el orquestador de un bot de reservas de buceo (Diving Planet) en las "
        "Islas del Rosario, Cartagena. El cliente está dentro del flujo de carrito de "
        "reservas. Tu trabajo es decidir UNA acción estructurada (function call) que "
        "modifique el árbol de decisión, o responder una pregunta informativa.\n\n"
        "Reglas:\n"
        "- Si el cliente quiere reservar, cambiar el carrito, cambiar el origen, "
        "añadir o quitar actividades → USA una herramienta. NUNCA describas tú el "
        "proceso de reserva ni inventes pasos.\n"
        "- Si es una pregunta informativa (precios, qué incluye, horarios, políticas) "
        "→ usa answer_question.\n"
        "- Si es algo médico, disponibilidad en tiempo real, queja o pago → escalate.\n"
        "- Nunca inventes precios, hoteles, enlaces ni disponibilidad.\n"
        "- Conserva los nombres propios (hoteles, islas) tal cual los escribe el cliente.\n"
        "- Elige exactamente una herramienta."
    )
    rules_en = (
        "You are the orchestrator of a scuba-diving booking bot (Diving Planet) in the "
        "Rosario Islands, Cartagena. The customer is inside the booking cart flow. Your "
        "job is to choose ONE structured action (function call) that changes the "
        "decision tree, or to answer an informational question.\n\n"
        "Rules:\n"
        "- If the customer wants to book, change the cart, change the origin, add or "
        "remove activities → USE a tool. NEVER describe the booking process yourself or "
        "make up steps.\n"
        "- If it is an informational question (prices, what's included, schedules, "
        "policies) → use answer_question.\n"
        "- If it is medical, real-time availability, a complaint or payment → escalate.\n"
        "- Never invent prices, hotels, links or availability.\n"
        "- Keep proper nouns (hotels, islands) exactly as the customer wrote them.\n"
        "- Choose exactly one tool."
    )
    base = rules_es if lang == "es" else rules_en
    if state_snapshot:
        label = "\n\nEstado actual de la conversación:\n" if lang == "es" else "\n\nCurrent conversation state:\n"
        base += label + state_snapshot
    return base


def _allowed_tools(allowed_actions: set[str] | None) -> list[dict]:
    if not allowed_actions:
        return TOOLS
    names = set(allowed_actions) | {TOOL_ANSWER_QUESTION}
    return [t for t in TOOLS if t["function"]["name"] in names]


async def orchestrate(
    message: str,
    *,
    state_snapshot: str | None = None,
    history: list[dict] | None = None,
    lang: str = "es",
    allowed_actions: set[str] | None = None,
    client: AsyncOpenAI | None = None,
) -> OrchestratorDecision:
    """Pick a structured action for a free-text message.

    Returns an OrchestratorDecision. On any failure returns an
    answer_question decision so the caller can fall back to RAG.
    """
    if not message or not message.strip():
        return OrchestratorDecision(tool=TOOL_ANSWER_QUESTION)

    tools = _allowed_tools(allowed_actions)
    messages: list[dict] = [{"role": "system", "content": _system_prompt(lang, state_snapshot)}]
    for turn in (history or [])[-12:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    try:
        client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.0,
            max_tokens=150,
        )
        choice = response.choices[0].message
        tool_calls = getattr(choice, "tool_calls", None)
        if not tool_calls:
            logger.info(f"[ORCHESTRATOR] no tool_call -> answer_question msg={message[:40]!r}")
            return OrchestratorDecision(
                tool=TOOL_ANSWER_QUESTION, raw_text=(choice.content or None)
            )

        call = tool_calls[0]
        name = call.function.name
        try:
            args = json.loads(call.function.arguments or "{}")
        except (json.JSONDecodeError, TypeError):
            args = {}

        if name not in ALL_TOOL_NAMES:
            logger.info(f"[ORCHESTRATOR] unknown tool {name!r} -> answer_question")
            return OrchestratorDecision(tool=TOOL_ANSWER_QUESTION)

        logger.info(f"[ORCHESTRATOR] tool={name} args={args} msg={message[:40]!r}")
        return OrchestratorDecision(tool=name, args=args or {})
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[ORCHESTRATOR] error: {exc} -> answer_question fallback")
        return OrchestratorDecision(tool=TOOL_ANSWER_QUESTION)
