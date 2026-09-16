"""Los scripts (`python -m scripts.X`) no trazan en Langfuse por defecto
(ver scripts/__init__.py para el porque). Se prueba en un subproceso limpio con
el entorno que trae el contenedor de PRE: claves de Langfuse puestas.

Se comprueba `observability.langfuse_enabled(settings)` (no importa `langfuse`,
asi que vale en Python 3.14 local, donde el `api` generado de langfuse no
importa) en vez de tocar el SDK."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_PROBE = (
    "import scripts\n"
    "from src.config import settings\n"
    "from src.observability import langfuse_enabled\n"
    "print(langfuse_enabled(settings))\n"
)


_TRACING_VARS = ("LANGFUSE_TRACING_ENABLED", "SCRIPTS_TRACING", "SCRIPTS_LANGSMITH_TRACING",
                 "LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2")


def _run(extra_env):
    # Entorno limpio de tracing: otros tests importan `scripts`, que apaga el
    # tracing en el entorno de ESTE proceso, y el subproceso lo heredaria.
    env = {k: v for k, v in os.environ.items() if k not in _TRACING_VARS}
    # Lo que trae el contenedor de PRE desde `.env.pre`: claves de Langfuse.
    env.update({"LANGFUSE_PUBLIC_KEY": "pk-lf-fake", "LANGFUSE_SECRET_KEY": "sk-lf-fake"})
    env.update(extra_env)
    out = subprocess.run([sys.executable, "-c", _PROBE], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip().splitlines()[-1]


def test_scripts_package_turns_tracing_off_even_if_the_env_has_keys():
    assert _run({}) == "False"


def test_tracing_can_be_turned_back_on_on_purpose():
    assert _run({"SCRIPTS_TRACING": "true"}) == "True"
