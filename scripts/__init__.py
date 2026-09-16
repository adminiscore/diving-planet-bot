"""Scripts de operacion y medicion (`python -m scripts.<nombre>`).

Todo lo que se lanza como `python -m scripts.X` pasa primero por aqui, y aqui se
apaga el tracing de observabilidad ANTES de importar `src` (2026-09-14; migrado
de LangSmith a Langfuse el 2026-09-16, tarea 8).

Por que aqui y no en cada script: una bateria o el eval-set llaman al extractor
sin pasar por el grafo, asi que cada llamada al LLM es una traza raiz propia --
una sesion de A/B (bateria + eval-set, ida y vuelta) son ~1.000-1.300 trazas y
gastan cuota (y llenaban la salida de 429 cuando la cuota se acababa). Un flag por
script se olvida; un paquete que lo aplica a todos, no. Vale igual para los
scripts que se anadan mas adelante.

`LANGFUSE_TRACING_ENABLED=false` lo lee `observability.langfuse_enabled` (y el
propio SDK de Langfuse): en el contenedor de PRE hay claves de Langfuse en el
`.env`, asi que sin esto una bateria dentro del contenedor SI trazaria.

Para trazar una ejecucion concreta a proposito: `SCRIPTS_TRACING=true`.
"""

import os

if os.environ.get("SCRIPTS_TRACING", os.environ.get("SCRIPTS_LANGSMITH_TRACING", "")).strip().lower() != "true":
    os.environ["LANGFUSE_TRACING_ENABLED"] = "false"
    # LangSmith (legacy, se retira en el paso 6): apagado por si queda algo cableado.
    for _var in ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2"):
        os.environ[_var] = "false"
