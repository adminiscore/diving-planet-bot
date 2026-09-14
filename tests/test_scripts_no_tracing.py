"""Los scripts (`python -m scripts.X`) no trazan en LangSmith por defecto
(ver scripts/__init__.py para el porque). Se prueba en un subproceso limpio con
el entorno que trae el contenedor de PRE: tracing encendido y API key puesta."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_PROBE = (
    "import scripts\n"
    "from src.config import settings\n"
    "from langsmith import utils\n"
    "print(settings.langchain_tracing_v2, utils.tracing_is_enabled())\n"
)


_TRACING_VARS = ("LANGSMITH_TRACING", "LANGSMITH_TRACING_V2", "LANGCHAIN_TRACING",
                 "LANGCHAIN_TRACING_V2", "SCRIPTS_LANGSMITH_TRACING")


def _run(extra_env):
    # Entorno limpio de tracing: otros tests importan `scripts`, que apaga el
    # tracing en el entorno de ESTE proceso, y el subproceso lo heredaria.
    env = {k: v for k, v in os.environ.items() if k not in _TRACING_VARS}
    # Lo que trae el contenedor de PRE desde `.env.pre`.
    env.update({"LANGCHAIN_TRACING_V2": "true", "LANGSMITH_API_KEY": "lsv2-fake-for-test"})
    env.update(extra_env)
    out = subprocess.run([sys.executable, "-c", _PROBE], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip().splitlines()[-1]


def test_scripts_package_turns_tracing_off_even_if_the_env_turns_it_on():
    assert _run({}) == "False False"


def test_tracing_can_be_turned_back_on_on_purpose():
    assert _run({"SCRIPTS_LANGSMITH_TRACING": "true"}) == "True True"
