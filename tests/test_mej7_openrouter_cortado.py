"""MEJ-7 (23-oct, flag `openrouter_corte_segundos`): con un 401/402/403 de OpenRouter (la clave o el crédito; el 21-oct,
ronda respaldo-luna, 401 en cada pieza de las 93 vueltas) se deja de llamar a OpenRouter un rato: cada pieza va directa
a su respaldo de OpenAI y Jev se salta. Un fallo pasajero (500, timeout) no corta. Sin red."""
import pytest

from src import llm_client
from src.agents import jev_router
from src.config import settings


class _Fallo(Exception):
    def __init__(self, status_code):
        super().__init__(f"error {status_code}")
        self.status_code = status_code


class _OpenRouter:
    def __init__(self, status_code):
        self.llamadas = 0
        self.status_code = status_code
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        self.llamadas += 1
        raise _Fallo(self.status_code)


@pytest.fixture
def con_corte(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_corte_segundos", 300.0)
    monkeypatch.setattr(settings, "openrouter_respaldo_segundos", 0.0)
    monkeypatch.setattr(settings, "respaldo_si_openrouter_falla", "gpt-5.4-mini")
    monkeypatch.setattr(llm_client, "_openrouter_cortado_hasta", 0.0)


def _openai():
    modelos = []

    async def original(*args, **kwargs):
        modelos.append(kwargs["model"])
        return "ok"

    return original, modelos


@pytest.mark.asyncio
async def test_un_401_corta_y_las_siguientes_van_directas_al_respaldo(con_corte, monkeypatch):
    falso = _OpenRouter(401)
    monkeypatch.setattr(llm_client, "_openrouter", lambda: falso)
    original, modelos = _openai()
    for _ in range(3):
        assert await llm_client._por_proveedor(original, model="deepseek/deepseek-v4.1-flash", messages=[]) == "ok"
    assert falso.llamadas == 1 and modelos == ["gpt-5.4-mini"] * 3
    assert llm_client.openrouter_cortado()


@pytest.mark.asyncio
async def test_un_fallo_pasajero_no_corta(con_corte, monkeypatch):
    falso = _OpenRouter(500)
    monkeypatch.setattr(llm_client, "_openrouter", lambda: falso)
    original, _ = _openai()
    for _ in range(2):
        await llm_client._por_proveedor(original, model="deepseek/deepseek-v4.1-flash", messages=[])
    assert falso.llamadas == 2 and not llm_client.openrouter_cortado()


@pytest.mark.asyncio
async def test_apagado_se_intenta_siempre(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_corte_segundos", 0.0)
    monkeypatch.setattr(settings, "openrouter_respaldo_segundos", 0.0)
    monkeypatch.setattr(llm_client, "_openrouter_cortado_hasta", 0.0)
    falso = _OpenRouter(401)
    monkeypatch.setattr(llm_client, "_openrouter", lambda: falso)
    original, _ = _openai()
    for _ in range(2):
        await llm_client._por_proveedor(original, model="deepseek/deepseek-v4.1-flash", messages=[])
    assert falso.llamadas == 2 and not llm_client.openrouter_cortado()


@pytest.mark.asyncio
async def test_con_openrouter_cortado_jev_no_se_llama(con_corte, monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "sk-or-test")
    llm_client.cortar_openrouter_si_es_la_clave(402, "test")

    class _NoLlamar:
        async def post(self, *a, **k):
            raise AssertionError("con OpenRouter cortado no se llama a Jev")

    monkeypatch.setattr(jev_router, "_http", lambda: _NoLlamar())
    assert await jev_router.detect_routing_signals_jev_full("¿cuánto cuesta el snorkel?") == (None, {})


def test_el_corte_sale_en_turn_metrics():
    import json

    from src.observability import turn_metrics_line

    linea = turn_metrics_line("c1", {"openrouter": "cortado"}, "2026-10-23T12:00:00Z", 1.0)
    assert json.loads(linea[linea.index("{"):])["openrouter"] == "cortado"
