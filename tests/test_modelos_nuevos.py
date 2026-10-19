"""Cambio de modelos, fase 0 (8-oct): los modelos de la API nueva (gpt-5/gpt-6/serie o) rechazan `max_tokens` y gpt-6
razona por defecto. `llm_client.adaptar_parametros` lo traduce en un solo sitio para todas las llamadas del bot."""

import pytest

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


def test_gpt5_4_en_adelante_sin_razonamiento():
    """MOD (18-oct): gpt-5.4-mini/nano aceptan "none" y, sin él, razonan (lentos): candidatos de la fase MOD."""
    out = adaptar_parametros({"model": "gpt-5.4-mini", "max_tokens": 300})
    assert out == {"model": "gpt-5.4-mini", "max_completion_tokens": 300,
                   "reasoning_effort": settings.razonamiento_modelos_nuevos}


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


class _Falso:
    """Un `create` falso que apunta los modelos con los que se le llama y falla si se le pide."""

    def __init__(self, falla: bool = False):
        self.modelos, self.falla = [], falla

    async def create(self, *args, **kwargs):
        self.modelos.append(kwargs["model"])
        if self.falla:
            raise RuntimeError("Error code: 402 - key limit exceeded")
        return f"respuesta de {kwargs['model']}"


@pytest.mark.asyncio
@pytest.mark.parametrize("falla", [False, True])
async def test_si_openrouter_falla_contesta_el_respaldo_de_openai(monkeypatch, falla):
    """18-oct (ronda mod-G): con la clave de OpenRouter sin crédito fallaban Jev, DeepSeek y Haiku a la vez, y el
    revisor dejaba pasar las respuestas sin revisar. Si OpenRouter falla, la misma petición va al modelo de OpenAI."""
    from src import llm_client

    openrouter, openai = _Falso(falla=falla), _Falso()
    monkeypatch.setattr(llm_client, "_openrouter", lambda: type("C", (), {"chat": type("Ch", (), {
        "completions": openrouter})})())
    monkeypatch.setattr(settings, "respaldo_si_openrouter_falla", "gpt-5.4-mini")
    r = await llm_client._por_proveedor(openai.create, model="deepseek/deepseek-v4.1-flash", messages=[])
    if falla:
        assert r == "respuesta de gpt-5.4-mini" and openai.modelos == ["gpt-5.4-mini"]
    else:
        assert r == "respuesta de deepseek/deepseek-v4.1-flash" and openai.modelos == []


@pytest.mark.asyncio
async def test_sin_respaldo_el_fallo_de_openrouter_sube(monkeypatch):
    from src import llm_client

    openrouter = _Falso(falla=True)
    monkeypatch.setattr(llm_client, "_openrouter", lambda: type("C", (), {"chat": type("Ch", (), {
        "completions": openrouter})})())
    monkeypatch.setattr(settings, "respaldo_si_openrouter_falla", "")
    with pytest.raises(RuntimeError):
        await llm_client._por_proveedor(_Falso().create, model="deepseek/deepseek-v4.1-flash", messages=[])


def test_nada_sale_por_openrouter_sin_tapar_los_datos_personales():
    """MOD-7 (decisión de Gadea): todo lo que va a OpenRouter lleva los datos personales tapados, en un solo sitio;
    los precios del contexto se quedan y el prompt de sistema no se toca."""
    from src.llm_client import parametros_openrouter

    mensajes = [{"role": "system", "content": "Detecta el idioma."},
                {"role": "user", "content": "escríbeme al 300 123 4567\nel paquete cuesta 1.429.000 COP"},
                {"role": "assistant", "content": "Tu cédula es 1.023.456.789"}]
    out = parametros_openrouter({"model": "deepseek/deepseek-v4.1-flash", "messages": mensajes})
    assert out["messages"][0] == mensajes[0]
    assert "300 123 4567" not in out["messages"][1]["content"] and "1.429.000 COP" in out["messages"][1]["content"]
    assert "1.023.456.789" not in out["messages"][2]["content"]
    assert mensajes[1]["content"].startswith("escríbeme al 300")  # no cambia la lista de quien llama


@pytest.mark.asyncio
@pytest.mark.parametrize("estructurada, esperado", [(True, 400), (False, 140)])
async def test_las_respuestas_estructuradas_tienen_un_tope_minimo(monkeypatch, estructurada, esperado):
    """19-oct (ex-9b): el router de respaldo pedía 140 tokens y DeepSeek dejaba el JSON sin cerrar (~1 de cada 9 en PRE):
    sin señales de IA, decidían las listas de palabras. Con herramienta o JSON, al menos 400; el texto libre, como pida."""
    from src import llm_client

    visto = {}

    async def original(*args, **kwargs):
        visto.update(kwargs)
        return "ok"

    extra = {"tools": [{"type": "function"}]} if estructurada else {}
    await llm_client._por_proveedor(original, model="gpt-4o-mini", max_tokens=140, messages=[], **extra)
    assert visto["max_tokens"] == esperado
