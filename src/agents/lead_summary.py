"""
Lead summary generator for human handoff.

Builds a structured internal note from ConversationState so that
the human agent who picks up the conversation has full context.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.flows.decision_tree import ConversationState

# Pure button-choice inputs we don't want to echo back to the advisor as
# "client messages": menu numbers ("1", "2", "6+"), and navigation tokens.
_BUTTON_NUMBER_RE = re.compile(r"^\d+\+?$")
_NAV_TOKENS = {"back", "volver", "atras", "atrás", "inicio", "home", "menu", "menú", "start"}


def _is_free_text(content: str) -> bool:
    """True only for genuine free-text messages (not button picks/navigation).

    Filters out menu number choices ("1", "2", "6+") and navigation keywords so
    the advisor only sees what the client actually typed in their own words.
    """
    text = (content or "").strip()
    if not text:
        return False
    if _BUTTON_NUMBER_RE.match(text):
        return False
    if text.lower() in _NAV_TOKENS:
        return False
    return True


def _service_display_name(service_id: str, lang: str) -> str:
    """Resolve a service id to its human-readable name for the advisor note.

    Falls back to the raw id only if the catalog has no name for it.
    """
    try:
        from src.flows.decision_tree import SERVICES
    except Exception:
        return service_id
    service = SERVICES.get(service_id) or {}
    name = service.get(f"name_{lang}") or service.get("name_es") or service.get("name_en")
    return name or service_id


def build_lead_summary(state: "ConversationState", escalation_reason: str = "") -> str:
    lines = ["🤿 *Lead Diving Planet*", "─────────────────────"]

    lang_label = "Español" if state.language == "es" else "English"
    lines.append(f"🌐 Idioma: {lang_label}")

    # Solo mostramos "Servicio de interés" en flujos de servicio único. En grupo
    # mixto el carrito (más abajo) refleja el interés real; el selected_service
    # suele quedar obsoleto de cuando el cliente navegó por Información.
    if state.selected_service and not state.mixed_cart:
        lines.append(
            f"🎯 Servicio de interés: {_service_display_name(state.selected_service, state.language)}"
        )

    if state.location == "cartagena":
        lines.append("📍 Salida desde: Cartagena")
    elif state.location == "island":
        lines.append("📍 Ya en: Islas del Rosario")

    if state.island:
        lines.append(f"🏝️ Isla: {state.island}")
    if state.hotel:
        lines.append(f"🏨 Hotel: {state.hotel}")

    if state.is_certified is True:
        lines.append("🏅 Certificación: Sí")
    elif state.is_certified is False:
        lines.append("🏅 Certificación: No (principiante)")

    if state.is_colombian is True:
        lines.append("🇨🇴 Colombiano/residente: Sí")
    elif state.is_colombian is False:
        lines.append("🇨🇴 Colombiano/residente: No")

    # Ages mentioned in free text — surface minors so the advisor knows the
    # activity constraints (snorkel from 6, Bubble Makers 8-10, diving from 10).
    ages = sorted({a for a in (getattr(state, "detected_ages", None) or []) if 1 <= a <= 99})
    if ages:
        line = "👶 Edades mencionadas: " + ", ".join(str(a) for a in ages)
        minors = [a for a in ages if a < 18]
        if minors:
            line += f" (⚠️ menor(es): {', '.join(str(a) for a in minors)})"
        lines.append(line)

    if state.last_dive_over_2_years is True:
        lines.append("⏱️ Último buceo: hace más de 2 años")
    elif state.last_dive_over_2_years is False:
        lines.append("⏱️ Último buceo: reciente")

    if state.has_500_dives_or_dive_master is True:
        lines.append("🌟 Perfil: +500 buceos o Divemaster")

    if state.refresher_interested is True:
        lines.append("🔄 Interesado en refresher: Sí")
    elif state.refresher_interested is False:
        lines.append("🔄 Interesado en refresher: No")

    if state.mixed_cart:
        lines.append("─────────────────────")
        lines.append("👥 *Grupo mixto (carrito)*")
        for item in state.mixed_cart:
            lines.append(f"  • {item.get('qty', 0)} × {item.get('label', item.get('type', ''))}")
        if any(it.get("qty", 0) >= 6 for it in state.mixed_cart):
            lines.append("  • 🚨 Grupo grande (6+ en algún subgrupo)")
        if state.mixed_final_is_colombian is True:
            lines.append("  • 🇨🇴 Colombiano/residente: Sí (precio en COP)")
        elif state.mixed_final_is_colombian is False:
            lines.append("  • 🇨🇴 Colombiano/residente: No")
        kids_under_8 = state.kids_under_8_count or 0
        kids_8_10 = state.kids_eight_to_ten_count or 0
        if kids_under_8 > 0:
            label = "menor de 8" if kids_under_8 == 1 else "menores de 8"
            lines.append(f"  • 👶 {kids_under_8} {label}")
        if kids_8_10 > 0:
            label = "niño 8-10" if kids_8_10 == 1 else "niños 8-10"
            lines.append(f"  • 👶 {kids_8_10} {label} (Bubble Makers) — requiere supervisor")
        elif state.mixed_final_has_kids_8_10:
            lines.append("  • 👶 Niños 8-10 (Bubble Makers) — requiere supervisor")
        if state.mixed_final_wants_private:
            lines.append("  • 🚤 Solicita lancha privada exclusiva")

    recent_user_messages = [
        msg["content"]
        for msg in (state.history or [])[-6:]
        if msg.get("role") == "user" and _is_free_text(msg.get("content", ""))
    ]
    if recent_user_messages:
        lines.append("─────────────────────")
        lines.append("💬 Últimos mensajes del cliente:")
        for msg in recent_user_messages[-3:]:
            truncated = msg[:120] + "…" if len(msg) > 120 else msg
            lines.append(f"  • {truncated}")

    lines.append("─────────────────────")
    reason_label = escalation_reason or "solicitó asesor"
    lines.append(f"🔴 Estado: lead activo — {reason_label}")

    return "\n".join(lines)
