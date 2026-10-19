"""ex-9b (19-oct, flag `openrouter_respaldo_segundos`): en la ronda ex9b-3 una llamada a OpenRouter (la reescritura de
DeepSeek) se quedó colgada 30 s, el límite general, y el turno tardó 34 s. Con el flag, si OpenRouter no contesta en
esos segundos, la misma petición sale por OpenAI y gana la primera que termine bien, en un solo sitio
(`llm_client._por_proveedor`)."""

import asyncio

import pytest

from src import llm_client
from src.config import settings


class _Lento:
    """Un `create` falso que tarda `segundos` (o falla) y apunta con qué modelos se le llama."""

    def __init__(self, segundos: float = 0.0, falla: bool = False):
        self.segundos, self.falla, self.modelos = segundos, falla, []

    async def create(self, *args, **kwargs):
        self.modelos.append(kwargs["model"])
        await asyncio.sleep(self.segundos)
        if self.falla:
            raise RuntimeError("502 bad gateway")
        return f"respuesta de {kwargs['model']}"


def _con(monkeypatch, openrouter: _Lento, segundos: float):
    monkeypatch.setattr(llm_client, "_openrouter", lambda: type("C", (), {"chat": type("Ch", (), {
        "completions": openrouter})})())
    monkeypatch.setattr(settings, "respaldo_si_openrouter_falla", "gpt-5.4-mini")
    monkeypatch.setattr(settings, "openrouter_respaldo_segundos", segundos)


async def test_si_openrouter_se_cuelga_gana_el_respaldo(monkeypatch):
    openrouter, openai = _Lento(segundos=5), _Lento()
    _con(monkeypatch, openrouter, 0.05)
    r = await asyncio.wait_for(
        llm_client._por_proveedor(openai.create, model="deepseek/deepseek-v4.1-flash", messages=[]), timeout=2)
    assert r == "respuesta de gpt-5.4-mini" and openai.modelos == ["gpt-5.4-mini"]


async def test_si_openrouter_contesta_a_tiempo_no_sale_el_respaldo(monkeypatch):
    openrouter, openai = _Lento(segundos=0), _Lento()
    _con(monkeypatch, openrouter, 0.5)
    r = await llm_client._por_proveedor(openai.create, model="deepseek/deepseek-v4.1-flash", messages=[])
    assert r == "respuesta de deepseek/deepseek-v4.1-flash" and openai.modelos == []


async def test_si_openrouter_falla_antes_contesta_el_respaldo(monkeypatch):
    openrouter, openai = _Lento(falla=True), _Lento()
    _con(monkeypatch, openrouter, 0.5)
    r = await llm_client._por_proveedor(openai.create, model="deepseek/deepseek-v4.1-flash", messages=[])
    assert r == "respuesta de gpt-5.4-mini"


async def test_apagado_espera_a_openrouter_como_siempre(monkeypatch):
    openrouter, openai = _Lento(segundos=0.2), _Lento()
    _con(monkeypatch, openrouter, 0)
    r = await llm_client._por_proveedor(openai.create, model="deepseek/deepseek-v4.1-flash", messages=[])
    assert r == "respuesta de deepseek/deepseek-v4.1-flash" and openai.modelos == []


async def test_un_modelo_de_openai_no_pasa_por_aqui(monkeypatch):
    openrouter, openai = _Lento(), _Lento()
    _con(monkeypatch, openrouter, 0.05)
    r = await llm_client._por_proveedor(openai.create, model="gpt-6-luna", messages=[])
    assert r == "respuesta de gpt-6-luna" and openrouter.modelos == []


@pytest.mark.parametrize("cuelgue", [True])
async def test_si_fallan_los_dos_sube_el_error(monkeypatch, cuelgue):
    openrouter, openai = _Lento(segundos=0.2, falla=True), _Lento(falla=True)
    _con(monkeypatch, openrouter, 0.05)
    with pytest.raises(RuntimeError):
        await llm_client._por_proveedor(openai.create, model="deepseek/deepseek-v4.1-flash", messages=[])
