"""ARQ-2b (22-oct, flag `cache_anthropic`): el prompt de sistema de los modelos de Anthropic por OpenRouter se marca
para la caché y Haiku sale con un orden fijo de proveedores (con «el más rápido» saltaba entre ellos y perdía la caché).
OpenAI y DeepSeek cachean solos: a ellos no se les toca."""
from src import llm_client
from src.config import settings

MENSAJES = [{"role": "system", "content": "reglas del extractor"}, {"role": "user", "content": "hola"}]


def _kw(modelo):
    return llm_client.parametros_openrouter({"model": modelo, "messages": list(MENSAJES)})


def test_con_el_flag_el_sistema_de_anthropic_va_marcado_y_con_orden_fijo(monkeypatch):
    monkeypatch.setattr(settings, "cache_anthropic", True)
    monkeypatch.setattr(settings, "openrouter_proveedores", "google-vertex,anthropic,amazon-bedrock")
    kw = _kw("anthropic/claude-haiku-5.5")
    [bloque] = kw["messages"][0]["content"]
    assert bloque["cache_control"] == {"type": "ephemeral"} and bloque["text"] == "reglas del extractor"
    assert kw["messages"][1]["content"] == "hola"
    proveedor = kw["extra_body"]["provider"]
    assert proveedor["order"][0] == settings.cache_anthropic_proveedor and "sort" not in proveedor
    assert proveedor["allow_fallbacks"] and set(proveedor["order"]) == {"google-vertex", "anthropic", "amazon-bedrock"}
    assert proveedor["data_collection"] == "deny"


def test_sin_el_flag_o_con_otro_modelo_no_cambia(monkeypatch):
    monkeypatch.setattr(settings, "cache_anthropic", False)
    assert _kw("anthropic/claude-haiku-5.5")["messages"][0]["content"] == "reglas del extractor"
    monkeypatch.setattr(settings, "cache_anthropic", True)
    kw = _kw("deepseek/deepseek-v4.1-flash")
    assert kw["messages"][0]["content"] == "reglas del extractor" and kw["extra_body"]["provider"].get("sort") == "latency"
