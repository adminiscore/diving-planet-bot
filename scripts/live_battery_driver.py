"""Ad-hoc driver to run test-battery messages against the real bot (real LLM + pgvector).

Usage: ENV_FILE=.env.dev python -m scripts.live_battery_driver
Import `send`/`new_state` from a REPL, or edit the __main__ block below.
"""

import asyncio
import sys

from src.flows.decision_tree import ConversationState
from src.agents.supervisor import route_message


def new_state(lang: str = "es") -> ConversationState:
    s = ConversationState(conversation_id="live-battery-test")
    s.language = lang
    return s


async def send(state: ConversationState, *messages: str) -> list[str]:
    out = []
    for m in messages:
        r = await route_message(state, m)
        out.append(r)
        print(f">>> {m}\n<<< {r}\n")
    return out


async def run(turns: list[str], lang: str = "es"):
    state = new_state(lang)
    await send(state, *turns)
    return state


if __name__ == "__main__":
    msgs = sys.argv[1:] or ["hola"]
    asyncio.run(run(msgs))
