"""Grafo LangGraph del refactor multiagente (docs/multi-agent-refactor-plan.md).

- `state.py`  → `BotState` (contrato de estado del grafo).
- `router.py` → `classify_route` (clasifica cada mensaje en una de las 5 rutas).
- `graph.py`  → `StateGraph`: router + nodos-agente, compilado detrás de
  `settings.agent_arch`.

En la Fase 1 los nodos de ruta son wrappers finos que delegan en la cascada
actual (`supervisor._shared_turn_handler`); en Fases 2-3 se sustituyen por su
lógica real, una ruta a la vez (strangler-fig).
"""
