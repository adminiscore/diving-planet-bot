"""Cambio de modelos, fase 0 (8-oct): los modelos de la API nueva (gpt-5/gpt-6/serie o) rechazan `max_tokens` y gpt-6
razona por defecto. `llm_client.adaptar_parametros` lo traduce en un solo sitio para todas las llamadas del bot."""

from src.config import settings
from src.llm_client import adaptar_parametros


def test_los_modelos_de_hoy_no_se_tocan():
    for model in ("gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1"):
        kw = {"model": model, "max_tokens": 200, "temperature": 0.0}
        assert adaptar_parametros(kw) == kw


def test_gpt6_usa_max_completion_tokens_y_sin_razonamiento():
    out = adaptar_parametros({"model": "gpt-6-luna", "max_tokens": 200, "temperature": 0.3})
    assert out == {"model": "gpt-6-luna", "max_completion_tokens": 200, "temperature": 0.3,
                   "reasoning_effort": settings.razonamiento_modelos_nuevos}
    assert settings.razonamiento_modelos_nuevos == "none"


def test_un_esfuerzo_pedido_por_la_llamada_se_respeta():
    out = adaptar_parametros({"model": "gpt-6-luna", "max_completion_tokens": 500, "reasoning_effort": "low"})
    assert out["reasoning_effort"] == "low" and "max_tokens" not in out


def test_gpt5_traduce_el_tope_pero_no_impone_esfuerzo():
    out = adaptar_parametros({"model": "gpt-5-mini", "max_tokens": 300})
    assert out == {"model": "gpt-5-mini", "max_completion_tokens": 300}


def test_los_modelos_con_proveedor_salen_por_openrouter(monkeypatch):
    from src.llm_client import es_de_openrouter, parametros_openrouter

    assert es_de_openrouter("deepseek/deepseek-v4.1-flash")
    assert not es_de_openrouter("gpt-6-luna") and not es_de_openrouter("gpt-4.1-mini")
    monkeypatch.setattr(settings, "openrouter_proveedores", "baseten, fireworks/us")
    out = parametros_openrouter({"model": "deepseek/deepseek-v4.1-flash", "max_tokens": 500, "temperature": 0.3})
    assert out["max_tokens"] == 500 and out["temperature"] == 0.3
    assert out["extra_body"]["provider"] == {"only": ["baseten", "fireworks/us"], "sort": "latency",
                                             "allow_fallbacks": True, "data_collection": "deny"}
    assert out["extra_body"]["reasoning"] == {"enabled": False}
