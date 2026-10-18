"""mod-2 (18-oct): el respaldo común de `llm_client.crear_con_respaldo`.

Ronda mod-F: el extractor en Haiku por OpenRouter tenía la mediana bien (1,14 s) pero 2 colas de 4-5 s en 47 turnos.
Si el principal no contesta en `segundos`, la misma petición va al respaldo y gana la primera; si el principal falla,
contesta el respaldo; sin respaldo, la llamada de siempre.
"""

import asyncio

import pytest

from src.llm_client import crear_con_respaldo


class _Cliente:
    """Cliente falso: cada modelo tarda lo que diga `tiempos` (o falla si es una excepción)."""

    def __init__(self, tiempos: dict):
        self.tiempos, self.llamados = tiempos, []
        cliente = self

        class _Completions:
            @staticmethod
            async def create(**kwargs):
                modelo = kwargs["model"]
                cliente.llamados.append(modelo)
                t = cliente.tiempos[modelo]
                if isinstance(t, Exception):
                    raise t
                await asyncio.sleep(t)
                return f"respuesta de {modelo}"

        class _Chat:
            completions = _Completions

        self.chat = _Chat


@pytest.mark.asyncio
async def test_si_el_principal_contesta_a_tiempo_no_se_llama_al_respaldo():
    c = _Cliente({"principal": 0.01, "respaldo": 0.01})
    r = await crear_con_respaldo(c, respaldo="respaldo", segundos=0.2, pieza="extractor", model="principal")
    assert r == "respuesta de principal" and c.llamados == ["principal"]


@pytest.mark.asyncio
async def test_si_el_principal_se_queda_en_la_cola_gana_el_respaldo():
    c = _Cliente({"principal": 2.0, "respaldo": 0.01})
    r = await crear_con_respaldo(c, respaldo="respaldo", segundos=0.05, pieza="extractor", model="principal")
    assert r == "respuesta de respaldo" and c.llamados == ["principal", "respaldo"]


@pytest.mark.asyncio
async def test_si_el_principal_falla_contesta_el_respaldo():
    c = _Cliente({"principal": RuntimeError("OpenRouter caído"), "respaldo": 0.01})
    r = await crear_con_respaldo(c, respaldo="respaldo", segundos=0.5, pieza="extractor", model="principal")
    assert r == "respuesta de respaldo"


@pytest.mark.asyncio
async def test_sin_respaldo_es_la_llamada_de_siempre():
    c = _Cliente({"principal": 0.01})
    r = await crear_con_respaldo(c, respaldo="", segundos=0.05, pieza="extractor", model="principal")
    assert r == "respuesta de principal" and c.llamados == ["principal"]


@pytest.mark.asyncio
async def test_si_fallan_los_dos_sube_la_excepcion():
    c = _Cliente({"principal": RuntimeError("uno"), "respaldo": RuntimeError("dos")})
    with pytest.raises(RuntimeError):
        await crear_con_respaldo(c, respaldo="respaldo", segundos=0.5, pieza="extractor", model="principal")
