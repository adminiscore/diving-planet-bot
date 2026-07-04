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
TOOL_REMEMBER = "remember"

# `remember` is a companion tool: the model may call it *alongside* a primary
# action to persist facts the customer volunteered. It never counts as the
# primary decision, so it is excluded from the "which action?" selection.
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
    TOOL_REMEMBER,
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
    {
        "type": "function",
        "function": {
            "name": TOOL_REMEMBER,
            "description": (
                "Persist any concrete facts the customer just volunteered so the bot "
                "never re-asks or ignores them. Call this ALONGSIDE another tool (or "
                "alongside answer_question) whenever the message contains group size, "
                "ages, experience, budget, days, certification, activity, location, or "
                "a preference/concern. Only include fields actually stated."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "group_size": {"type": "integer", "description": "Total people, e.g. 'somos 5' -> 5"},
                    "certified_count": {"type": "integer", "description": "How many are certified divers"},
                    "beginner_count": {"type": "integer", "description": "How many are beginners / not certified"},
                    "is_certified": {"type": "boolean", "description": "Whole group certified (true) or all beginners (false)"},
                    "experience_level": {
                        "type": "string",
                        "enum": ["never_dived", "beginner", "certified", "instructor"],
                        "description": "'nunca he buceado' -> never_dived",
                    },
                    "child_ages": {"type": "string", "description": "Ages of minors stated, e.g. '9, 14'"},
                    "budget": {"type": "string", "description": "Budget stated verbatim, e.g. '<300 EUR', '1 millon COP'"},
                    "days": {"type": "integer", "description": "Number of days available, e.g. '4 días' -> 4"},
                    "activity": {
                        "type": "string",
                        "enum": ACTIVITY_VALUES + ["padi_course", "unspecified"],
                        "description": "Activity the customer wants",
                    },
                    "location": {"type": "string", "enum": ["cartagena", "island"], "description": "Where they depart from / are"},
                    "hotel": {"type": "string", "description": "Hotel name exactly as written"},
                    "preference": {"type": "string", "description": "Any preference/concern, e.g. 'quieren ir juntos, no separarse'"},
                },
            },
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
    # Facts extracted via the companion `remember` tool call, if any. The caller
    # persists these to conversation state so the bot never re-asks them.
    remembered: dict | None = None

    @property
    def is_answer(self) -> bool:
        return self.tool == TOOL_ANSWER_QUESTION


def _system_prompt(lang: str, state_snapshot: str | None) -> str:
    rules_es = (
        "Eres el cerebro de enrutamiento de un bot de buceo (Diving Planet, Islas del "
        "Rosario, Cartagena). El cliente lleva la conversación; tu prioridad es ATENDER "
        "lo que dice, no arrastrarlo a un menú. Puedes estar al inicio de la charla o a "
        "mitad de una reserva (mira el estado). Eliges herramientas estructuradas que el "
        "supervisor ejecuta; NO redactas tú la respuesta salvo que no haya herramienta.\n\n"
        "En CADA mensaje:\n"
        "1) Si el cliente da CUALQUIER dato (personas, edades, experiencia, presupuesto, "
        "días, certificación, actividad, hotel, o una preferencia como 'queremos ir "
        "juntos') → llama `remember` con esos datos, ADEMÁS de la herramienta principal.\n"
        "2) Elige UNA herramienta principal:\n"
        "   - Pregunta informativa (precios, qué incluye, edad mínima, si un niño puede "
        "bucear, si operáis fuera de Cartagena, cómo es un curso, recomendación) → "
        "`answer_question`. NUNCA fuerces una reserva ni pidas certificación para responder "
        "una pregunta.\n"
        "   - Intención CLARA de reservar/añadir/quitar/cambiar origen o carrito → la "
        "herramienta de acción correspondiente (start_booking, add_to_cart, set_location, "
        "cart_action, remove_item, set_profile). NUNCA describas tú los pasos de reserva.\n"
        "   - Médico, disponibilidad en tiempo real, queja o problema de pago → `escalate`.\n\n"
        "Reglas: nunca inventes precios, hoteles, enlaces ni disponibilidad. Conserva los "
        "nombres propios tal cual. Ante la duda entre responder o reservar, RESPONDE "
        "(`answer_question`). Puedes llamar `remember` + una herramienta principal a la vez."
    )
    rules_en = (
        "You are the routing brain of a scuba bot (Diving Planet, Rosario Islands, "
        "Cartagena). The customer leads the conversation; your priority is to ADDRESS "
        "what they say, not drag them into a menu. You may be at the start of the chat or "
        "mid-booking (check the state). You pick structured tools the supervisor executes; "
        "you do NOT write the reply yourself unless no tool applies.\n\n"
        "On EVERY message:\n"
        "1) If the customer gives ANY fact (people, ages, experience, budget, days, "
        "certification, activity, hotel, or a preference like 'we want to stay together') "
        "→ call `remember` with it, IN ADDITION to the primary tool.\n"
        "2) Pick ONE primary tool:\n"
        "   - Informational question (prices, what's included, minimum age, whether a "
        "child can dive, whether you operate outside Cartagena, how a course works, a "
        "recommendation) → `answer_question`. NEVER force a booking or ask for "
        "certification just to answer a question.\n"
        "   - CLEAR intent to book/add/remove/change origin or cart → the matching action "
        "tool (start_booking, add_to_cart, set_location, cart_action, remove_item, "
        "set_profile). NEVER describe booking steps yourself.\n"
        "   - Medical, real-time availability, complaint or payment problem → `escalate`.\n\n"
        "Rules: never invent prices, hotels, links or availability. Keep proper nouns "
        "as written. When unsure whether to answer or book, ANSWER (`answer_question`). "
        "You may call `remember` + one primary tool together."
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

        # The model may return several tool calls (e.g. `remember` alongside a
        # primary action). Pull `remember` out as companion data and take the
        # first recognized non-remember tool as the primary decision.
        remembered: dict | None = None
        primary_name: str | None = None
        primary_args: dict = {}
        for call in tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except (json.JSONDecodeError, TypeError):
                args = {}
            if name == TOOL_REMEMBER:
                remembered = {k: v for k, v in (args or {}).items() if v not in (None, "", [])}
                continue
            if primary_name is None and name in ALL_TOOL_NAMES:
                primary_name, primary_args = name, args or {}

        if primary_name is None:
            primary_name = TOOL_ANSWER_QUESTION

        logger.info(
            f"[ORCHESTRATOR] tool={primary_name} args={primary_args} "
            f"remembered={remembered} msg={message[:40]!r}"
        )
        return OrchestratorDecision(
            tool=primary_name,
            args=primary_args,
            remembered=remembered,
            raw_text=(choice.content or None),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[ORCHESTRATOR] error: {exc} -> answer_question fallback")
        return OrchestratorDecision(tool=TOOL_ANSWER_QUESTION)
