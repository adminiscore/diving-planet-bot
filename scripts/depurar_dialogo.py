"""Reproduce UN diálogo del golden en LOCAL (extracción y Jev reales; el RAG es un «RAG» fijo) y enseña el estado
de la reserva turno a turno. Sirve para encontrar QUÉ camino del flujo dispara una repregunta o un supuesto (s4-26).

    python -m scripts.depurar_dialogo manual-duracion-curso
"""
import asyncio
import os
import sys

os.environ.update({
    "ENV_FILE": ".env.dev", "APP_ENV": "development",
    "LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": "",
    "CHATWOOT_API_TOKEN": "", "CHATWOOT_BASE_URL": "http://127.0.0.1:9", "CHATWOOT_API_BASE_URL": "http://127.0.0.1:9",
})
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scripts.replay_golden_local import _noop, _rag, dialogues  # noqa: E402
from src.agents import conversational_core as core  # noqa: E402
from src.agents import escalation, supervisor  # noqa: E402
from src.flows.state import ConversationState  # noqa: E402

CAMPOS = ("core_pending_slot", "detected_activity", "detected_group_size", "detected_group_allocation", "location",
          "is_certified", "solo_traveler_confirmed", "needs_companion_activity", "companion_activity_deferred",
          "pending_companion_activity", "pending_undecided_qty", "detected_duration", "hotel")


async def main(did: str) -> None:
    supervisor.rag_answer = _rag
    core.compose_acknowledgement = lambda *a, **k: asyncio.sleep(0, result="")
    escalation.escalate_to_human = _noop
    supervisor.escalate_to_human = _noop
    turns = dict(dialogues())[did]
    st = ConversationState(conversation_id=f"dbg-{did}")
    for i, msg in enumerate(turns, 1):
        resp = await supervisor.route_message(st, msg)
        print(f"\n== T{i} CLIENTE: {msg[:150]}")
        print(f"   BOT: {resp[-260:]!r}")
        print("   ESTADO:", {c: getattr(st, c, None) for c in CAMPOS if getattr(st, c, None) not in (None, False, "", [], {})})


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
