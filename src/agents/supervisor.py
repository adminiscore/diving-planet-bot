"""
LangGraph Supervisor Agent.

Routes incoming messages to the appropriate handler:
- Decision tree: for structured menu flows (user is navigating options)
- RAG agent: for free-text questions outside the menu flow
- Escalation: when user explicitly asks for a human

The routing logic is deterministic (no LLM call for routing),
keeping costs minimal.
"""

import logging

from src.flows.decision_tree import DecisionTree, ConversationState, Step
from src.agents.rag_agent import rag_answer
from src.privacy import detect_pii, privacy_block_message

logger = logging.getLogger("uvicorn.error")

decision_tree = DecisionTree()

# Steps where the user is actively navigating the decision tree menu
MENU_STEPS = {
    Step.WELCOME,
    Step.LANGUAGE,
    Step.MAIN_MENU,
    Step.TOURS_EXPERIENCE,
    Step.TOURS_CERTIFIED,
    Step.TOURS_BEGINNER,
    Step.COURSES_MENU,
    Step.SERVICE_DETAIL,
    Step.LOCATION,
    Step.COLOMBIAN,
}

# Keywords that indicate the user wants to go back to the menu
MENU_KEYWORDS = {
    "menu", "menú", "inicio", "start", "opciones", "options",
    "volver", "back", "atras", "atrás",
}

# Keywords that indicate escalation to a human
ESCALATION_KEYWORDS = {
    "humano", "human", "agente", "agent", "asesor", "advisor",
    "persona", "person", "hablar con", "speak with", "talk to",
}


async def route_message(state: ConversationState, message: str) -> str:
    """
    Supervisor: decides how to handle each incoming message.

    Routing rules (no LLM call):
    1. If user is in a menu step AND sends a number -> decision tree
    2. If user sends a menu/back keyword -> reset to main menu
    3. If user sends an escalation keyword -> escalate
    4. If user is in SUMMARY/ESCALATE/FREE_TEXT step -> RAG agent
    5. If user sends free text while in a menu step -> RAG agent
    """
    msg_lower = message.strip().lower()

    pii_hits = detect_pii(message)
    if pii_hits:
        state.step = Step.ESCALATE
        logger.warning(f"[SUPERVISOR][PRIVACY] PII detected hits={pii_hits} step={state.step.value}")
        return privacy_block_message(state.language)

    # Check for escalation keywords
    if any(kw in msg_lower for kw in ESCALATION_KEYWORDS):
        state.step = Step.ESCALATE
        from src.flows.decision_tree import MESSAGES
        logger.info(f"[SUPERVISOR] Escalation triggered by keyword")
        return MESSAGES["escalate"][state.language]

    # Check for menu reset keywords
    if msg_lower in MENU_KEYWORDS:
        state.step = Step.MAIN_MENU
        from src.flows.decision_tree import MESSAGES
        logger.info(f"[SUPERVISOR] Menu reset triggered by keyword")
        return MESSAGES["main_menu"][state.language]

    # If user is in a menu step
    if state.step in MENU_STEPS:
        # If it looks like a menu choice (number), use decision tree
        if msg_lower.isdigit():
            response = decision_tree.process_message(state, message)
            logger.info(f"[SUPERVISOR] Decision tree -> step={state.step.value}")
            return response

        # If it's the welcome/language step, always use decision tree
        if state.step in (Step.WELCOME, Step.LANGUAGE):
            response = decision_tree.process_message(state, message)
            logger.info(f"[SUPERVISOR] Decision tree (early step) -> step={state.step.value}")
            return response

        # Free text while in menu -> use RAG but keep menu state
        logger.info(f"[SUPERVISOR] RAG (free text in menu step={state.step.value})")
        state.history.append({"role": "user", "content": message})
        answer = await rag_answer(message, lang=state.language, history=state.history)
        state.history.append({"role": "assistant", "content": answer})
        return answer

    # Post-menu steps (SUMMARY, ESCALATE, FREE_TEXT) -> RAG agent
    if state.step in (Step.SUMMARY, Step.FREE_TEXT):
        # Check if user wants to restart
        if msg_lower in ("1", "si", "sí", "yes"):
            state.step = Step.MAIN_MENU
            from src.flows.decision_tree import MESSAGES
            return MESSAGES["main_menu"][state.language]
        if msg_lower in ("2", "no", "gracias", "thanks"):
            if state.language == "es":
                return (
                    "¡Gracias por contactar a Diving Planet! 🤿\n"
                    "Si necesitas algo más, escribe *menu* para volver al inicio.\n"
                    "¡Te esperamos en las Islas del Rosario!"
                )
            return (
                "Thank you for contacting Diving Planet! 🤿\n"
                "If you need anything else, type *menu* to go back.\n"
                "We look forward to seeing you at the Rosario Islands!"
            )

        # Free text question
        state.step = Step.FREE_TEXT
        state.history.append({"role": "user", "content": message})
        answer = await rag_answer(message, lang=state.language, history=state.history)
        state.history.append({"role": "assistant", "content": answer})
        logger.info(f"[SUPERVISOR] RAG (post-menu)")
        return answer

    # Escalate step -> let them ask freely via RAG
    if state.step == Step.ESCALATE:
        state.step = Step.FREE_TEXT
        state.history.append({"role": "user", "content": message})
        answer = await rag_answer(message, lang=state.language, history=state.history)
        state.history.append({"role": "assistant", "content": answer})
        return answer

    # Fallback: welcome
    response = decision_tree.process_message(state, message)
    return response
