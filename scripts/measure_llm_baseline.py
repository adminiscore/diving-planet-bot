"""Fase 0.4 (docs/multi-agent-refactor-plan.md) — baseline de métricas LLM/turno.

Corre un guion representativo contra el bot real (LLM real, sin mocks) e
instrumenta CADA llamada a la API de OpenAI (chat.completions + embeddings,
que son los dos métodos que usa todo `src/`, ver `grep .create` en el plan)
parcheando el método a nivel de CLASE — cubre las ~10 instanciaciones propias
de `AsyncOpenAI` en el código sin tocar ni un archivo de producción.

No depende de una cuenta LangSmith (no hay `LANGSMITH_API_KEY` en este
entorno dev): mide localmente nº de llamadas, latencia y tokens por turno,
para la tabla del Registro de ejecución (§8 del plan). Es la baseline que
Fase 3 usará de comparación tras mover las redes a nodos LangGraph.

Uso: ENV_FILE=.env.dev python -m scripts.measure_llm_baseline
"""

import asyncio
import time
from dataclasses import dataclass, field

from openai.resources.chat.completions.completions import AsyncCompletions
from openai.resources.embeddings import AsyncEmbeddings

from src.agents.supervisor import route_message
from src.flows.state import ConversationState

# Precios oficiales OpenAI (USD / 1M tokens) para los modelos que aparecen en
# settings.openai_model / settings.extraction_model / settings.openai_embedding_model.
_PRICING_PER_1M = {
    "gpt-4o": {"prompt": 2.50, "completion": 10.00},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "text-embedding-3-small": {"prompt": 0.02, "completion": 0.0},
}


@dataclass
class _CallRecord:
    kind: str  # "chat" | "embedding"
    model: str
    latency_s: float
    prompt_tokens: int
    completion_tokens: int


@dataclass
class _Instrumentation:
    calls: list[_CallRecord] = field(default_factory=list)

    def cost_usd(self) -> float:
        total = 0.0
        for c in self.calls:
            price = _PRICING_PER_1M.get(c.model)
            if not price:
                continue
            total += c.prompt_tokens / 1_000_000 * price["prompt"]
            total += c.completion_tokens / 1_000_000 * price["completion"]
        return total


def _instrument(instr: _Instrumentation):
    orig_chat_create = AsyncCompletions.create
    orig_embed_create = AsyncEmbeddings.create

    async def patched_chat_create(self, *args, **kwargs):
        start = time.perf_counter()
        resp = await orig_chat_create(self, *args, **kwargs)
        latency = time.perf_counter() - start
        usage = getattr(resp, "usage", None)
        instr.calls.append(_CallRecord(
            kind="chat",
            model=kwargs.get("model", "?"),
            latency_s=latency,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        ))
        return resp

    async def patched_embed_create(self, *args, **kwargs):
        start = time.perf_counter()
        resp = await orig_embed_create(self, *args, **kwargs)
        latency = time.perf_counter() - start
        usage = getattr(resp, "usage", None)
        instr.calls.append(_CallRecord(
            kind="embedding",
            model=kwargs.get("model", "?"),
            latency_s=latency,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=0,
        ))
        return resp

    AsyncCompletions.create = patched_chat_create
    AsyncEmbeddings.create = patched_embed_create
    return orig_chat_create, orig_embed_create


def _restore(orig_chat_create, orig_embed_create):
    AsyncCompletions.create = orig_chat_create
    AsyncEmbeddings.create = orig_embed_create


# Guion representativo: reserva de buceo certificado con acompañante,
# cubriendo greeting/idioma, extracción de intención, slot-filling
# (certificación/cantidad/ubicación) y cierre — el camino más transitado
# del núcleo conversacional.
SCRIPT_ES = [
    "hola",
    "quiero bucear, ya soy certificada open water, somos 2 personas",
    "salimos desde cartagena",
    "cuanto cuesta",
    "perfecto, reservamos",
]


async def run_baseline(turns: list[str] = SCRIPT_ES) -> None:
    instr = _Instrumentation()
    orig = _instrument(instr)
    per_turn_counts: list[int] = []
    try:
        state = ConversationState(conversation_id="baseline-0.4")
        for msg in turns:
            before = len(instr.calls)
            resp = await route_message(state, msg)
            per_turn_counts.append(len(instr.calls) - before)
            print(f">>> {msg}\n<<< {resp}\n")
    finally:
        _restore(*orig)

    total_calls = len(instr.calls)
    total_latency = sum(c.latency_s for c in instr.calls)
    total_prompt = sum(c.prompt_tokens for c in instr.calls)
    total_completion = sum(c.completion_tokens for c in instr.calls)
    n_turns = len(turns)

    print("=" * 70)
    print("BASELINE Fase 0.4 — nº de llamadas LLM / latencia / tokens por turno")
    print("=" * 70)
    for i, (msg, n) in enumerate(zip(turns, per_turn_counts), 1):
        print(f"  turno {i}: {n} llamada(s) — {msg!r}")
    print("-" * 70)
    print(f"Turnos:                 {n_turns}")
    print(f"Llamadas LLM totales:   {total_calls}  ({total_calls / n_turns:.2f} / turno)")
    print(f"Latencia total:         {total_latency:.2f}s  ({total_latency / n_turns:.2f}s / turno)")
    print(f"Latencia media/llamada: {total_latency / max(total_calls, 1):.2f}s")
    print(f"Tokens prompt:          {total_prompt}  ({total_prompt / n_turns:.0f} / turno)")
    print(f"Tokens completion:      {total_completion}  ({total_completion / n_turns:.0f} / turno)")
    print(f"Coste estimado:         ${instr.cost_usd():.4f} USD  (${instr.cost_usd() / n_turns:.4f} / turno)")
    print("=" * 70)
    by_model: dict[str, int] = {}
    for c in instr.calls:
        by_model[c.model] = by_model.get(c.model, 0) + 1
    print("Llamadas por modelo:", by_model)


if __name__ == "__main__":
    asyncio.run(run_baseline())
