"""CAL-A (fase CAL, 16-oct): que el RAG conteste TODO lo que pregunta el cliente, repartiendo el trabajo.

Diagnóstico (docs/robustness/investigacion/diagnostico-73-fallos.md): el RAG no falla por tener mucha información
(~8.000 tokens de contexto, igual en los aciertos que en los fallos) sino porque UNA llamada hace demasiado: entender
la pregunta, elegir entre 50 reglas, aplicar moneda y origen y redactar breve. Y el revisor solo castiga inventar,
nunca dejarse algo: decir menos es lo más seguro. Aquí:

- `planificar` (A2, flag `rag_plan_primero`): una llamada barata saca la LISTA de lo que el cliente pregunta o pide en
  su último mensaje (con las implicaciones obvias). La redacción recibe esa lista y la contesta punto por punto.
- `puntos_sin_cubrir` (A3, flag `rag_revisor_completitud`): tras el revisor de siempre, otra llamada barata comprueba
  que la respuesta cubre cada punto (con un dato o diciendo que no lo tiene); si falta alguno, se reintenta una vez
  con lo que falta.

Si una llamada falla, se sigue como hoy (sin lista, o sin la comprobación). CAL-G medirá lanzar el plan en paralelo
con la búsqueda.
"""
from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from src.config import settings
from src.llm_client import trace_openai

logger = logging.getLogger("uvicorn.error")

_MAX_PUNTOS = 6

_PLAN_ES = """Eres el planificador de Coral, la asistente de Diving Planet (buceo y snorkel en las Islas del Rosario). NO contestas al cliente: lees su ÚLTIMO mensaje (con la conversación para entenderlo y para saber lo que ya ha contado) y haces la lista de lo que la respuesta tiene que cubrir.

Reglas:
- Un punto por cada cosa que el cliente pregunta o pide en ese mensaje, en una frase corta ("precio del minicurso para 2", "si el almuerzo incluye opción vegetariana", "cómo se reserva").
- Añade solo las implicaciones obvias de lo que pide (si da sus fechas y pregunta por un plan de varios días, "si el plan cabe en sus fechas"; si pregunta por dos planes, uno por cada plan).
- AVISOS: añade también, empezando por "Aviso:", lo que el cliente NECESITA saber aunque no lo pregunte, por lo que ha contado en la conversación y lo que pide ahora: que el plan no cabe en sus fechas u horas, que lo que pide no da lo que quiere (p. ej. un minicurso no certifica), un requisito que se le puede pasar (un documento, un formulario), que no operamos donde dice, o en qué moneda paga si ya se sabe si es extranjero o colombiano. Solo si sale de lo que ha dicho; nunca un precio que no ha pedido.
- No inventes preguntas que no hace, ni temas que el bot querría ofrecer.
- Si el mensaje no pide nada (un saludo, "gracias", un dato suelto que contesta al bot) y no hace falta ningún aviso, la lista va vacía.
- Como mucho 6 puntos.

Devuelve solo JSON: {"puntos": ["...", "..."]}"""

_PLAN_EN = """You are the planner for Coral, Diving Planet's assistant (diving and snorkeling in the Rosario Islands). You do NOT answer the customer: you read their LAST message (with the conversation to understand it and to know what they already told) and list what the answer has to cover.

Rules:
- One item for each thing the customer asks or requests in that message, in a short phrase ("price of the mini course for 2", "whether lunch has a vegetarian option", "how to book").
- Add only the obvious implications of what they ask (if they give their dates and ask about a multi-day plan, "whether the plan fits their dates"; if they ask about two plans, one item per plan).
- WARNINGS: also add, starting with "Warning:", what the customer NEEDS to know even if they don't ask, from what they told in the conversation and what they ask now: that the plan doesn't fit their dates or times, that what they ask for doesn't give what they want (e.g. a mini course doesn't certify), a requirement they may miss (a document, a form), that we don't operate where they say, or which currency they pay in if it is already known whether they are foreign or Colombian. Only if it follows from what they said; never a price they didn't ask for.
- Do not invent questions they did not ask, nor topics the bot would like to offer.
- If the message asks for nothing (a greeting, "thanks", a bare fact answering the bot) and no warning is needed, the list is empty.
- At most 6 items.

Return only JSON: {"puntos": ["...", "..."]}"""

_COMPLETA_ES = """Compruebas si la RESPUESTA de un asistente cubre cada PUNTO de la lista. Un punto está cubierto si la respuesta lo contesta con un dato o dice claramente que no tiene ese dato o que lo confirma un asesor. No juzgas si los datos son correctos (eso lo hace otro revisor), solo si falta algún punto.

Devuelve solo JSON: {"faltan": ["punto tal como viene en la lista", ...]} (lista vacía si están todos)."""

_COMPLETA_EN = """You check whether an assistant's ANSWER covers each ITEM in the list. An item is covered if the answer addresses it with a fact or clearly says it doesn't have that fact or that an advisor will confirm it. You do not judge whether the facts are right (another reviewer does), only whether any item is missing.

Return only JSON: {"faltan": ["item exactly as listed", ...]} (empty list if all are covered)."""


def _cliente():
    return trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))


def _ultimas_lineas(history: list[dict] | None, n: int = 8) -> str:
    lineas = []
    for m in (history or [])[-n:]:
        if m.get("content"):
            quien = "Cliente" if m.get("role") == "user" else "Bot"
            lineas.append(f"{quien}: {m['content'][:1500]}")
    return "\n".join(lineas) or "(sin conversación previa)"


async def planificar(query: str, history: list[dict] | None, lang: str) -> list[str] | None:
    """Los puntos que la respuesta tiene que cubrir, o None si la llamada falló (se sigue sin lista)."""
    try:
        resp = await _cliente().chat.completions.create(
            model=settings.rag_plan_model, temperature=0, max_tokens=250, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": _PLAN_ES if lang == "es" else _PLAN_EN},
                      {"role": "user", "content": f"Conversación reciente:\n{_ultimas_lineas(history)}\n\n"
                                                  f"ÚLTIMO MENSAJE DEL CLIENTE:\n{query}"}])
        puntos = json.loads(resp.choices[0].message.content or "{}").get("puntos") or []
    except Exception as exc:  # noqa: BLE001 — nunca romper el turno
        logger.warning(f"[RAG][PLAN] falló, se sigue sin lista: {exc}")
        return None
    puntos = [str(p).strip() for p in puntos if str(p).strip()][:_MAX_PUNTOS]
    logger.info(f"[RAG][PLAN] {len(puntos)} puntos: {puntos}")
    return puntos


def bloque_de_puntos(puntos: list[str], lang: str) -> str:
    """Lo que se añade al mensaje de la redacción: la lista a contestar, en positivo."""
    lista = "\n".join(f"- {p}" for p in puntos)
    if lang == "es":
        return ("PUNTOS QUE TU RESPUESTA TIENE QUE CUBRIR (contesta cada uno con el contexto, en el orden que sea "
                "natural; si de alguno no tienes el dato, dilo para ese punto y contesta los demás):\n" + lista)
    return ("ITEMS YOUR ANSWER HAS TO COVER (answer each one with the context, in whatever order is natural; if you "
            "don't have the fact for one, say so for that item and answer the rest):\n" + lista)


async def puntos_sin_cubrir(puntos: list[str], answer: str, lang: str) -> list[str]:
    """Los puntos de la lista que la respuesta no cubre ([] si están todos o si la llamada falló)."""
    if not puntos:
        return []
    lista = "\n".join(f"- {p}" for p in puntos)
    try:
        resp = await _cliente().chat.completions.create(
            model=settings.rag_plan_model, temperature=0, max_tokens=200, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": _COMPLETA_ES if lang == "es" else _COMPLETA_EN},
                      {"role": "user", "content": f"PUNTOS:\n{lista}\n\nRESPUESTA:\n{answer}"}])
        faltan = json.loads(resp.choices[0].message.content or "{}").get("faltan") or []
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[RAG][COMPLETITUD] falló, no se comprueba: {exc}")
        return []
    faltan = [str(p).strip() for p in faltan if str(p).strip()]
    if faltan:
        logger.info(f"[RAG][COMPLETITUD] faltan {faltan}")
    return faltan


def feedback_de_faltan(faltan: list[str], lang: str) -> str:
    lista = "\n".join(f"- {p}" for p in faltan)
    if lang == "es":
        return ("Tu respuesta no cubre estos puntos que preguntó el cliente:\n" + lista + "\nReescríbela añadiéndolos "
                "con el contexto (o di que no tienes ese dato), sin quitar lo que ya estaba bien.")
    return ("Your answer does not cover these items the customer asked about:\n" + lista + "\nRewrite it adding "
            "them from the context (or say you don't have that fact), keeping what was already right.")
