"""Paso 10 (28-sep): los interruptores que PRE fija en `docker-compose.vps.yml` tienen el MISMO valor por
defecto en el código. Hasta hoy 14 flags promocionados seguían apagados por defecto: un `.env.dev` sin
ellos (o la suite) medía otro bot distinto del de PRE — la misma trampa que `test_models_pinned` cierra
para los modelos.

Excepción a propósito: `app_env` (cada entorno el suyo). `jev_router_enabled` ya no existe (sim-6): Jev va siempre y,
sin la clave de OpenRouter, se aparta solo y decide el router LLM.
"""

from scripts.check_deploy import expected_from_compose
from src.config import Settings

EXCEPCIONES = {"app_env"}


def test_los_interruptores_de_pre_son_el_valor_por_defecto_del_codigo():
    distintos = {
        k: (Settings.model_fields[k].default, v)
        for k, v in expected_from_compose().items()
        if k not in EXCEPCIONES and isinstance(v, bool) and Settings.model_fields[k].default != v
    }
    assert not distintos, f"código != PRE, (código, compose): {distintos}"
