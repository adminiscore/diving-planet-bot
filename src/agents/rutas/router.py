"""Lo que hace el nodo `router` del grafo (`orchestration/graph._router_node`) ANTES de clasificar: reiniciar la
memoria si el cliente empieza un escenario nuevo y marcar la mención de niños.

s4-2 (19-oct): movido tal cual desde `supervisor.py`, que lo re-exporta. Ver `src/agents/rutas/__init__.py`.
"""

import re

from src.flows.state import ConversationState
from src.utils.number_words import number_alt
from src.utils.text import strip_accents as _strip_accents

# --------------------------------------------------------------------------- #
# New-scenario memory reset (owner decision, 2026-07-20)
#
# A brand-new Chatwoot conversation already starts with empty memory. But within
# the SAME conversation, if the customer greets AND introduces a clearly new
# scenario (a new person/booking) while old memory is still around, that stale
# summary/facts/notes/slots would bleed into the new case. We reset ONLY in that
# narrow situation. Conservative on purpose (favors false-negatives): a bare
# "hola" mid-booking, or a greeting without a fresh self-introduction, does NOT
# reset — the customer usually greets and keeps going on the same reservation.
# --------------------------------------------------------------------------- #
_GREETING_START_RE = re.compile(
    r"^\s*[¡!]*\s*(?:hola|buenas|buenos\s+d[ií]as|buenas\s+tardes|buenas\s+noches|"
    r"hey|hi|hello|hey\s+there)\b",
    re.IGNORECASE,
)
# A fresh self-introduction — the strong signal that this is a new person/case.
# Name detection is CASE-SENSITIVE on purpose: "soy Sofía" (a capitalized name)
# is a new-person intro, but "soy certificado" (lowercase adjective) is a normal
# mid-booking answer and must NOT trigger a reset.
_NAME_INTRO_RE = re.compile(
    r"\bsoy\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+"
    r"|\bI'?m\s+[A-Z][a-z]+|\bI\s+am\s+[A-Z][a-z]+"
)
_INTRO_PHRASE_RE = re.compile(
    r"\bme\s+llamo\b|\bmi\s+nombre\s+es\b|\bmy\s+name\s+is\b"
    r"|\bsomos\s+\d|\bwe\s+are\s+\d",
    re.IGNORECASE,
)


def _has_accumulated_memory(state: ConversationState) -> bool:
    """True if the conversation already carries meaningful memory that would
    bleed into a new scenario if not cleared."""
    facts = state.remembered_facts or {}
    return bool(
        state.conversation_summary
        or any(v for v in facts.values())
        or state.is_certified is not None
        or getattr(state, "location", None)
        or getattr(state, "detected_group_size", None)
        or getattr(state, "mixed_cart", None)
        or len(state.history or []) >= 4
    )


def _is_new_scenario_restart(message: str, state: ConversationState) -> bool:
    """True only when the message greets AND introduces a clearly new scenario
    (self-introduction) while the conversation already holds accumulated memory.
    Deliberately narrow to never wipe legitimate mid-booking context."""
    if not (message and _GREETING_START_RE.match(message)):
        return False
    if not (_NAME_INTRO_RE.search(message) or _INTRO_PHRASE_RE.search(message)):
        return False
    # Needs some substance beyond "hola soy X" — a real new-scenario message.
    if len(message.strip()) < 25:
        return False
    return _has_accumulated_memory(state)


def _reset_to_fresh_scenario(state: ConversationState) -> None:
    """Wipe ALL conversation memory (summary, facts/notes, history, cart, every
    detected_* slot, adaptive context, step) while keeping only the stable
    identity: conversation_id and the already-detected language. Future-proof —
    resets to a fresh ConversationState's defaults, so new fields are covered
    automatically."""
    fresh = ConversationState(conversation_id=state.conversation_id, language=state.language)
    state.__dict__.update(fresh.__dict__)


def _normalize_for_menu_match(text: str) -> str:
    """Lowercase, drop diacritics, strip punctuation/emoji, collapse whitespace.

    Accent stripping is critical: users frequently type "informacion" instead of
    "información", "espanol" instead of "español", etc., and the matcher must
    treat these as equivalent to the button titles.

    Also splits number+companion-noun concatenations like "3amigos" or
    "sieteamigos" so the downstream count/intent regexes (which expect a space)
    can find both parts.
    """
    cleaned = _strip_accents(text.strip().lower())
    cleaned = re.sub(r"[¿¡?!.,;:()\[\]\"'/\\]", " ", cleaned)
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    # Split "3amigos" / "tresamigos" → "3 amigos" / "tres amigos" so person-count
    # parsing (which requires whitespace between the count and the noun) works.
    cleaned = re.sub(
        r"\b(?:uno|" + number_alt(2, 10, "es") + r"|\d+)(amig[oa]s?|person[ao]s?|companer[oa]s?|hij[oa]s?|herman[oa]s?|acompanantes?)\b",
        lambda m: m.group(0)[: -len(m.group(1))] + " " + m.group(1),
        cleaned,
    )
    return " ".join(cleaned.split())


def _detect_kids_mention(message: str) -> bool:
    """Detect mentions of kids/children/family in free text.

    Stricter than companion intent: only matches words that clearly imply minors
    (hijo, niño, menor, kid, child, sobrino, familia con hijos/niños). Excludes
    generic companion words (amigo, pareja, esposo) — those don't justify asking
    age ranges. Used to disparar la pregunta de edad en el cart-mixto cuando no
    haya minicurso ni snorkel pero el cliente sí trae niños.
    """
    normalized = _normalize_for_menu_match(message)
    if not normalized:
        return False
    tokens = set(normalized.split())

    kids_keywords = {
        "hijo", "hija", "hijos", "hijas",
        "nino", "nina", "ninos", "ninas",
        "menor", "menores",
        "sobrino", "sobrina", "sobrinos", "sobrinas",
        "nieto", "nieta", "nietos", "nietas",
        "bebe", "bebes",
        "kid", "kids", "child", "children",
        "grandchild", "grandchildren", "grandson", "granddaughter",
        "baby", "babies",
    }
    if tokens & kids_keywords:
        return True

    kids_patterns = (
        r"\bmi\s+(hij[oa]|sobrin[oa]|nin[oa]|niet[oa]|bebe)\b",
        r"\bmis\s+(hij[oa]s|sobrin[oa]s|nin[oa]s|niet[oa]s)\b",
        r"\bmi\s+familia\s+con\s+(hij[oa]s|nin[oa]s|menores)\b",
        r"\bmy\s+(grandchild|grandson|granddaughter|baby|kid|child)\b",
        r"\b(?:\d+|" + number_alt(2, 10, "es") + r")\s+(hij[oa]s|nin[oa]s|sobrin[oa]s|menores)\b",
    )
    return any(re.search(pattern, normalized) for pattern in kids_patterns)
