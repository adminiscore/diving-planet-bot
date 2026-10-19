"""ex-3 (fase EX): respuestas de texto fijo ACTIVAS que pasan al RAG, una por flag (`atajo_resumen_por_rag`,
`atajo_nacionalidad_por_rag`, `atajo_alergia_por_rag`). Inventario y motivos: docs/robustness/atajos/inventario-ex3.md.

Sin red: apagado, cada atajo contesta como hoy; encendido, no contesta y la pregunta sigue al RAG. ex-9b: el resumen
fijo de "¿qué ofrecen?" y la respuesta fija de "¿cambia el precio si es colombiano?" (sus flags están encendidos en
PRE) se borraron; queda fijado que la pregunta abierta llega al RAG.
"""
import pytest

from src.agents import rag_agent, supervisor
from src.config import settings


class _AlRag(Exception):
    """La pregunta llegó a la búsqueda del RAG (no la contestó el atajo)."""


@pytest.mark.asyncio
async def test_resumen_de_opciones_lo_contesta_el_rag(monkeypatch):
    async def busqueda(*args, **kwargs):
        raise _AlRag

    async def reescribir(query, **kwargs):
        return query

    monkeypatch.setattr(rag_agent, "search_knowledge_base", busqueda)
    monkeypatch.setattr(rag_agent, "condense_query", reescribir)
    with pytest.raises(_AlRag):
        await rag_agent.rag_answer("¿qué ofrecen para bucear?", lang="es")


@pytest.mark.parametrize("encendido", [False, True])
def test_alergia_a_un_alimento(monkeypatch, encendido):
    monkeypatch.setattr(settings, "atajo_alergia_por_rag", encendido)
    texto = supervisor._alcohol_and_food_policy_answer("soy alérgico a los mariscos, ¿pueden atenderme?", "es")
    assert (texto is None) if encendido else bool(texto)


def test_con_alcohol_la_alergia_sigue_en_el_texto_fijo(monkeypatch):
    # La política de alcohol no está en la base del RAG: si el mensaje habla de las dos cosas, va todo junto, como hoy.
    mensaje = "queremos bucear mañana, anoche tomamos alcohol y uno es alérgico a los mariscos"
    monkeypatch.setattr(settings, "atajo_alergia_por_rag", False)
    hoy = supervisor._alcohol_and_food_policy_answer(mensaje, "es")
    monkeypatch.setattr(settings, "atajo_alergia_por_rag", True)
    assert supervisor._alcohol_and_food_policy_answer(mensaje, "es") == hoy
