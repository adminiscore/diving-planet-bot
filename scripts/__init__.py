"""Scripts de operacion y medicion (`python -m scripts.<nombre>`).

Todo lo que se lanza como `python -m scripts.X` pasa primero por aqui, y aqui se
apaga el tracing de LangSmith ANTES de importar `src` (2026-09-14).

Por que aqui y no en cada script: una bateria o el eval-set llaman al extractor
sin pasar por el grafo, asi que cada llamada al LLM es una traza raiz propia --
una sesion de A/B (bateria + eval-set, ida y vuelta) son ~1.000-1.300 trazas de
un plan de 5.000/mes, y ademas llenan la salida de 429 cuando la cuota se acaba.
Un flag por script se olvida; un paquete que lo aplica a todos, no. Vale igual
para los scripts que se anadan mas adelante.

El contenedor trae `LANGCHAIN_TRACING_V2=true` desde el `.env`, por eso se
SOBRESCRIBE (no `setdefault`): `config._activate_langsmith_tracing` usa
`setdefault` y el SDK lee estas variables del entorno.

Para trazar una ejecucion concreta a proposito: `SCRIPTS_LANGSMITH_TRACING=true`.
"""

import os

if os.environ.get("SCRIPTS_LANGSMITH_TRACING", "").strip().lower() != "true":
    for _var in ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2"):
        os.environ[_var] = "false"
