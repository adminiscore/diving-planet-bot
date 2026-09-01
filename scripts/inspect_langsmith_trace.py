"""Inspecciona las llamadas LLM reales de una conversacion de PRE via LangSmith.

Nacio el 2026-09-01 investigando el bug de reparto de grupos mixtos que se
corrompe a mitad de conversacion (ver docs/multi-agent-refactor-plan.md
seccion "6.bis Problema ABIERTO"). Sin acceso a LLM en local, esta es la
unica forma de ver que devolvio cada llamada real (fill_gaps/extract_fields,
detect_special_signals/detect_signals, detect_routing_signals) para un turno
concreto de una conversacion reproducida en vivo contra PRE.

Uso:
    1. Lanza la conversacion contra PRE con pre_driver.py (o el driver que
       exista en ese momento) -- apunta el conversation_id que imprime.
    2. python scripts/inspect_langsmith_trace.py <conversation_id> [minutos_atras=15]

Requiere LANGSMITH_API_KEY en .env.dev (o pasala por variable de entorno).

OJO -- lecciones aprendidas (documentadas tambien en el plan):
- El tool `detect_special_signals` (Python) se registra en las trazas como
  `detect_signals`, no con su nombre real.
- Los snapshots de `conv_state` en el nodo "LangGraph chain" (el mas externo)
  NO son fiables para comparar antes/despues -- conv_state es un objeto
  mutable compartido por referencia, y la serializacion de LangSmith parece
  capturarlo tarde. Para snapshots fiables usa los outputs de los nodos de
  FASE (`slotfill_close`, `extraction`, etc.), que devuelven su valor de
  retorno real (`{"reply": ...}` o `{"carry": ...}`), no una referencia.
"""
import datetime
import json
import os
import re
import sys


def _load_api_key() -> str:
    key = os.environ.get("LANGSMITH_API_KEY")
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.dev")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^LANGSMITH_API_KEY=(.+)$", line.strip())
            if m:
                return m.group(1).strip()
    raise SystemExit("LANGSMITH_API_KEY no encontrada (ni en env ni en .env.dev)")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(f"Uso: python {sys.argv[0]} <conversation_id> [minutos_atras=15]")
    conv_id = sys.argv[1]
    minutes = int(sys.argv[2]) if len(sys.argv) > 2 else 15

    from langsmith import Client
    client = Client(api_key=_load_api_key())

    start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minutes)
    runs = list(client.list_runs(project_name="diving-planet-bot-pre", start_time=start))
    roots = [r for r in runs if r.parent_run_id is None]
    turns = [r for r in roots if (r.inputs or {}).get("conv_state", {}).get("conversation_id") == conv_id]
    turns.sort(key=lambda r: r.start_time)

    if not turns:
        print(f"No se encontraron turnos para conversation_id={conv_id!r} en los ultimos {minutes} min.")
        return

    for i, root in enumerate(turns):
        message = (root.inputs or {}).get("message")
        print(f"\n{'=' * 70}\nTURNO {i + 1}: trace_id={root.id}  msg={message!r}\n{'=' * 70}")

        trace_runs = list(client.list_runs(project_name="diving-planet-bot-pre", trace_id=root.id))
        for r in trace_runs:
            if r.name == "ChatOpenAI":
                try:
                    fn = r.outputs["choices"][0]["message"]["tool_calls"][0]["function"]
                    print(f"  [LLM tool] {fn['name']}: {fn['arguments']}")
                except Exception:
                    content = (r.outputs or {}).get("choices", [{}])[0].get("message", {}).get("content")
                    if content:
                        print(f"  [LLM text] {content[:200]!r}")
            elif r.name in ("slotfill_close", "extraction", "routing", "availability", "setup"):
                out = r.outputs or {}
                if "reply" in out:
                    print(f"  [{r.name}] reply={out['reply'][:200]!r}")
                elif "carry" in out:
                    carry = out["carry"]
                    print(f"  [{r.name}] carry.prev_group_allocation={carry.get('prev_group_allocation')} "
                          f"carry.prev_pending={carry.get('prev_pending')}")


if __name__ == "__main__":
    main()
