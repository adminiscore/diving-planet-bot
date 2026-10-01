"""1-oct (`docs/robustness/juez/README.md`): las dos formas de arreglar el juez que se comparan con el de hoy.

- J1: el juez es un modelo de razonamiento (gpt-5-mini): sin temperatura y con `reasoning_effort`.
- J2 (`juez_segunda_opinion`): si el juez rechaza, Jev revisa las frases marcadas NO; la respuesta pasa SOLO si
  ninguna afirma nada del negocio. Si Jev falla, el rechazo se mantiene.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents import grounding_check, juez_segunda_opinion
from src.config import settings


def _cliente(contenido: str):
    crear = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=contenido))]))
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=crear))), crear


@pytest.fixture
def juez(monkeypatch):
    def poner(contenido):
        cliente, crear = _cliente(contenido)
        monkeypatch.setattr(grounding_check, "AsyncOpenAI", lambda **k: cliente)
        monkeypatch.setattr(grounding_check, "trace_openai", lambda c: c)
        return crear
    monkeypatch.setattr(settings, "grounding_v3", True)
    monkeypatch.setattr(settings, "juez_por_tipo", False)
    return poner


RECHAZO_ASESOR = "- El pago se coordina con el equipo SÍ\n- Ese detalle no lo tengo a la mano, un asesor te lo confirma NO\nHALLUCINATED"
RECHAZO_DATO = "- Se suman impuestos al total NO\nHALLUCINATED"


@pytest.mark.asyncio
async def test_j2_si_ninguna_frase_rechazada_afirma_nada_pasa(juez, monkeypatch):
    juez(RECHAZO_ASESOR)
    monkeypatch.setattr(settings, "juez_segunda_opinion", True)
    vistas = []

    async def afirma(frase):
        vistas.append(frase)
        return 0.1

    monkeypatch.setattr(juez_segunda_opinion, "afirma", afirma)
    ok, _ = await grounding_check.is_grounded("respuesta", "contexto", "es")
    assert ok and vistas == ["Ese detalle no lo tengo a la mano, un asesor te lo confirma"]


@pytest.mark.asyncio
@pytest.mark.parametrize("p", [0.9, juez_segunda_opinion.SIN_DATOS_MAX, None])
async def test_j2_si_alguna_afirma_o_jev_no_contesta_el_rechazo_se_mantiene(juez, monkeypatch, p):
    juez(RECHAZO_DATO)
    monkeypatch.setattr(settings, "juez_segunda_opinion", True)
    monkeypatch.setattr(juez_segunda_opinion, "afirma", AsyncMock(return_value=p))
    ok, motivo = await grounding_check.is_grounded("respuesta", "contexto", "es")
    assert not ok and "impuestos" in motivo


@pytest.mark.asyncio
async def test_j2_apagado_no_pregunta_a_jev(juez, monkeypatch):
    juez(RECHAZO_ASESOR)
    monkeypatch.setattr(settings, "juez_segunda_opinion", False)
    afirma = AsyncMock(return_value=0.0)
    monkeypatch.setattr(juez_segunda_opinion, "afirma", afirma)
    ok, _ = await grounding_check.is_grounded("respuesta", "contexto", "es")
    assert not ok and afirma.await_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("modelo, razona", [("gpt-5-mini", True), ("gpt-4.1", False)])
async def test_j1_el_juez_de_razonamiento_va_sin_temperatura(juez, monkeypatch, modelo, razona):
    crear = juez("- (ninguno)\nGROUNDED")
    monkeypatch.setattr(settings, "grounding_v3_model", modelo)
    await grounding_check.is_grounded("respuesta", "contexto", "es")
    kw = crear.await_args.kwargs
    assert ("reasoning_effort" in kw and "temperature" not in kw) if razona else (kw["temperature"] == 0)
