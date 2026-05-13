"""
Lead summary generator for human handoff.

Builds a structured internal note from ConversationState so that
the human agent who picks up the conversation has full context.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.flows.decision_tree import ConversationState


def build_lead_summary(state: "ConversationState", escalation_reason: str = "") -> str:
    lines = ["🤿 *Lead Diving Planet*", "─────────────────────"]

    lang_label = "Español" if state.language == "es" else "English"
    lines.append(f"🌐 Idioma: {lang_label}")

    if state.selected_service:
        lines.append(f"🎯 Servicio de interés: {state.selected_service}")

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

    recent_user_messages = [
        msg["content"]
        for msg in (state.history or [])[-6:]
        if msg.get("role") == "user"
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
