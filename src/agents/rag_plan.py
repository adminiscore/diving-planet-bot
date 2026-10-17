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

- `avisos_que_faltan` (A4, flag `rag_revisor_avisos`): las medidas A0-A3 enseñaron que estos fallos no son preguntas sin
  contestar sino AVISOS que el cliente necesita y no pregunta ("os vais mañana: no os da tiempo a certificar"). El plan
  no puede saberlos (no lee la información de la empresa); este revisor lee lo mismo que el juez de siempre y busca como
  mucho 2 avisos imprescindibles que falten. Si falta alguno, se reintenta una vez con ellos.

- `aviso_al_final` (A6, flag `avisos_al_final`, 17-oct): lo que A4 y A5 enseñaron juntos. A4 (un modelo busca avisos
  en TODA la información) metía avisos que no tocaban; A5 (los elige el código con el estado) no ve las condiciones
  que el estado no tiene, y como iba en la redacción desplazaba lo que la respuesta tenía que decir. A6: la lista
  cerrada de avisos de A5, con sus condiciones en palabras, la juzga un modelo leyendo la CONVERSACIÓN; y si falta uno,
  se AÑADE una frase sin reescribir la respuesta (`insertar_frase`). Va a la vez que el juez de siempre.

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


_AVISOS_ES = """Revisas una respuesta de Coral, la asistente de Diving Planet (buceo y snorkel en las Islas del Rosario), ANTES de enviarla. Recibes la INFORMACIÓN de la empresa (con la conversación), el ÚLTIMO MENSAJE del cliente y la RESPUESTA.

Busca solo AVISOS IMPRESCINDIBLES que falten: un dato que está en la INFORMACIÓN y que el cliente necesita por lo que ha contado o pregunta, porque si no lo sabe le va a salir mal. Por ejemplo: con sus fechas u horas no le da tiempo; lo que pide no le da lo que quiere (un minicurso no certifica); tiene que traer o completar un documento o formulario; no operamos donde dice; en qué moneda paga si ya se sabe si es extranjero o colombiano; una condición de la empresa que cambia la respuesta a lo que pregunta.

NO cuentan: precios u ofertas que no pidió, otros planes, detalles agradables, cosas que la respuesta ya dice o que la INFORMACIÓN no trae. Si dudas, no falta. Como mucho 2.

Devuelve solo JSON: {"faltan": ["el aviso en una frase, con el dato de la INFORMACIÓN"]} (lista vacía si no falta nada)."""

_AVISOS_EN = """You review an answer from Coral, Diving Planet's assistant (diving and snorkeling in the Rosario Islands), BEFORE it is sent. You get the company INFORMATION (with the conversation), the customer's LAST MESSAGE and the ANSWER.

Look only for ESSENTIAL WARNINGS that are missing: a fact that is in the INFORMATION and that the customer needs given what they told or ask, because without it things will go wrong for them. For example: their dates or times don't leave enough time; what they ask for doesn't give what they want (a mini course doesn't certify); they must bring or complete a document or form; we don't operate where they say; which currency they pay in if it is already known whether they are foreign or Colombian; a company condition that changes the answer to what they ask.

These do NOT count: prices or offers they didn't ask for, other plans, nice-to-have details, things the answer already says or that the INFORMATION doesn't contain. If in doubt, it is not missing. At most 2.

Return only JSON: {"faltan": ["the warning in one sentence, with the fact from the INFORMATION"]} (empty list if nothing is missing)."""


async def avisos_que_faltan(query: str, informacion: str, answer: str, lang: str) -> list[str]:
    """Los avisos imprescindibles que la respuesta no da ([] si no falta ninguno o si la llamada falló)."""
    try:
        resp = await _cliente().chat.completions.create(
            model=settings.rag_plan_model, temperature=0, max_tokens=250, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": _AVISOS_ES if lang == "es" else _AVISOS_EN},
                      {"role": "user", "content": f"INFORMACIÓN:\n{informacion[-40000:]}\n\n"
                                                  f"ÚLTIMO MENSAJE DEL CLIENTE:\n{query}\n\nRESPUESTA:\n{answer}"}])
        faltan = json.loads(resp.choices[0].message.content or "{}").get("faltan") or []
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[RAG][AVISOS] falló, no se comprueba: {exc}")
        return []
    faltan = [str(p).strip() for p in faltan if str(p).strip()][:2]
    if faltan:
        logger.info(f"[RAG][AVISOS] faltan {faltan}")
    return faltan


def feedback_de_avisos(faltan: list[str], lang: str) -> str:
    lista = "\n".join(f"- {p}" for p in faltan)
    if lang == "es":
        return ("A tu respuesta le falta avisar al cliente de esto, que está en el contexto y necesita saber:\n" + lista
                + "\nReescríbela añadiéndolo en una frase, con el dato del contexto, sin quitar lo que ya estaba bien.")
    return ("Your answer is missing this warning, which is in the context and the customer needs to know:\n" + lista
            + "\nRewrite it adding it in one sentence, with the fact from the context, keeping what was already right.")


def feedback_de_faltan(faltan: list[str], lang: str) -> str:
    lista = "\n".join(f"- {p}" for p in faltan)
    if lang == "es":
        return ("Tu respuesta no cubre estos puntos que preguntó el cliente:\n" + lista + "\nReescríbela añadiéndolos "
                "con el contexto (o di que no tienes ese dato), sin quitar lo que ya estaba bien.")
    return ("Your answer does not cover these items the customer asked about:\n" + lista + "\nRewrite it adding "
            "them from the context (or say you don't have that fact), keeping what was already right.")


_AVISO_FINAL_ES = """Revisas una respuesta de Coral, la asistente de Diving Planet (buceo y snorkel en las Islas del Rosario), ANTES de enviarla. Recibes una lista cerrada de AVISOS (lo que un buen asesor le dice al cliente aunque no lo pregunte, cada uno con cuándo aplica), la CONVERSACIÓN, el ÚLTIMO MENSAJE del cliente y la RESPUESTA.

Decide si a la RESPUESTA le falta UNO de esos avisos. Falta solo si se cumplen las tres cosas:
1. APLICA a este cliente: su condición se cumple con lo que el CLIENTE ha dicho (no lo que dice el bot, ni lo que podría pasar). Tienes que poder citar sus palabras. De dónde sale, su nacionalidad, su nivel o sus fechas solo cuentan si el cliente LO DICE: nunca los deduzcas por el idioma en que escribe ni por lo que es probable.
2. Tiene que ver con su ÚLTIMO MENSAJE (lo que pregunta o cuenta ahora): sin el aviso, la respuesta a ESE mensaje le deja una idea equivocada o se le pasa algo que necesita. Un aviso que solo está relacionado con la conversación en general no falta.
3. Ni la RESPUESTA ni los mensajes anteriores del bot lo dicen ya, aunque sea con otras palabras.
Si un aviso tiene varias condiciones, tienen que cumplirse TODAS. Si las palabras del cliente pueden significar otra cosa (un "cierre" que puede ser del puerto o del sistema de reservas), no falta. Si dudas, no falta. Lo normal es que no falte ninguno. Como mucho UNO: el que más necesita el cliente.

Si falta, escribe la frase que se añadirá a la respuesta: UNA frase en el IDIOMA indicado, con el tono de Coral, que diga el aviso con sus datos exactos (sin cambiar días, horas ni cifras) y nada más: sin saludos, sin preguntas, sin pedirle datos (ni el hotel, ni el nivel, ni fechas: si el aviso lo menciona, dilo como información), sin precios y sin ofrecer otros planes. No afirmes nada del cliente que no haya dicho tal cual (si dijo "no soy colombiano", no digas que tampoco es residente): lo que dependa de eso, dilo como regla o con un "si".

Devuelve solo JSON: {"aviso": "<id del aviso>" o null, "cita_del_cliente": "las palabras exactas del cliente que cumplen la condición" o null, "cita_del_ultimo_mensaje": "las palabras exactas de su ÚLTIMO MENSAJE con las que tiene que ver el aviso" o null, "frase": "<la frase>" o null}"""

_AVISO_FINAL_EN = """You review an answer from Coral, Diving Planet's assistant (diving and snorkeling in the Rosario Islands), BEFORE it is sent. You get a closed list of NOTICES (what a good advisor tells the customer even if they don't ask, each with when it applies; they are written in Spanish), the CONVERSATION, the customer's LAST MESSAGE and the ANSWER.

Decide whether the ANSWER is missing ONE of those notices. It is missing only if all three hold:
1. It APPLIES to this customer: its condition is met by what the CUSTOMER has said (not what the bot says, nor what could happen). You must be able to quote their words. Where they depart from, their nationality, their level or their dates only count if the customer SAYS them: never infer them from the language they write in or from what is likely.
2. It is about their LAST MESSAGE (what they ask or tell now): without the notice, the answer to THAT message leaves them with a wrong idea or misses something they need. A notice that is only related to the conversation in general is not missing.
3. Neither the ANSWER nor the bot's earlier messages already say it, even in other words.
If a notice has several conditions, ALL of them must hold. If the customer's words can mean something else (a "closure" that may be the port's or the booking system's), it is not missing. If in doubt, it is not missing. Usually none is missing. At most ONE: the one the customer needs most.

If one is missing, write the sentence that will be added to the answer: ONE sentence in the LANGUAGE given, in Coral's tone, stating the notice with its exact facts (without changing days, times or figures) and nothing else: no greetings, no questions, no asking them for data (not the hotel, the level or dates: if the notice mentions it, state it as information), no prices and no offering other plans. Do not state anything about the customer they did not say as such (if they said "I'm not Colombian", do not say they are not a resident either): whatever depends on it, state it as a rule or with an "if".

Return only JSON: {"aviso": "<notice id>" or null, "cita_del_cliente": "the customer's exact words that meet the condition" or null, "cita_del_ultimo_mensaje": "the exact words of their LAST MESSAGE the notice is about" or null, "frase": "<the sentence>" or null}"""

_IDIOMAS = {"es": ("español", "Spanish"), "en": ("inglés", "English"), "pt": ("portugués", "Portuguese"),
            "fr": ("francés", "French"), "de": ("alemán", "German"), "it": ("italiano", "Italian")}


def _normalizado(texto: str) -> str:
    return " ".join("".join(c.lower() if c.isalnum() else " " for c in texto).split())


def _lo_dijo_el_cliente(cita: str, history: list[dict] | None, query: str) -> bool:
    """Que la cita sea de verdad del cliente (sus mensajes o el último), sin contar mayúsculas ni signos: si el
    revisor no puede citarle, la condición no sale de lo que dijo."""
    cita_n = _normalizado(cita)
    if len(cita_n) < 3:
        return False
    dicho = " | ".join(_normalizado(m.get("content") or "") for m in (history or []) if m.get("role") == "user")
    return cita_n in dicho or cita_n in _normalizado(query)


async def aviso_al_final(history: list[dict] | None, query: str, answer: str, lang: str,
                         dados: list[str] | None = None) -> tuple[str, str] | None:
    """CAL-A6: (id del aviso, frase que añadir) si a la respuesta le falta uno de la lista cerrada; None si no falta
    ninguno, si el modelo nombra uno que no está en la lista o ya dado, si no cita palabras reales del cliente, o si
    la llamada falla (nunca rompe el turno)."""
    from src.flows import avisos as avisos_mod  # lazy
    from src.privacy import redact_pii  # lazy

    lista = avisos_mod.lista_para_el_revisor(dados)
    if not lista or not answer.strip():
        return None
    es = lang == "es"
    idioma = _IDIOMAS.get(lang, (lang, lang))[0 if es else 1]
    conversacion = redact_pii(_ultimas_lineas(history))
    contenido = (f"AVISOS:\n{lista}\n\nCONVERSACIÓN:\n{conversacion}\n\nÚLTIMO MENSAJE DEL CLIENTE:\n{query}\n\n"
                 f"RESPUESTA:\n{answer}\n\nIDIOMA DE LA FRASE: {idioma}" if es else
                 f"NOTICES:\n{lista}\n\nCONVERSATION:\n{conversacion}\n\nCUSTOMER'S LAST MESSAGE:\n{query}\n\n"
                 f"ANSWER:\n{answer}\n\nLANGUAGE OF THE SENTENCE: {idioma}")
    try:
        resp = await _cliente().chat.completions.create(
            model=settings.avisos_al_final_model or settings.rag_plan_model, temperature=0, max_tokens=250,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": _AVISO_FINAL_ES if es else _AVISO_FINAL_EN},
                      {"role": "user", "content": contenido}])
        datos = json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001 — nunca romper el turno
        logger.warning(f"[RAG][AVISO_FINAL] falló, no se añade nada: {exc}")
        return None
    aviso_id = str(datos.get("aviso") or "").strip()
    frase = str(datos.get("frase") or "").strip()
    cita = str(datos.get("cita_del_cliente") or "").strip()
    cita_ultimo = str(datos.get("cita_del_ultimo_mensaje") or "").strip()
    aviso = avisos_mod.por_id(aviso_id) if aviso_id else None
    if not aviso or not frase:
        if aviso_id:
            logger.info(f"[RAG][AVISO_FINAL] descartado: {aviso_id!r} no está en la lista o viene sin frase")
        return None
    if aviso.get("una_vez") and aviso_id in set(dados or []):
        return None
    if not _lo_dijo_el_cliente(cita, history, query):
        logger.info(f"[RAG][AVISO_FINAL] descartado {aviso_id}: la cita no es del cliente ({cita[:80]!r})")
        return None
    if not _lo_dijo_el_cliente(cita_ultimo, [], query):
        logger.info(f"[RAG][AVISO_FINAL] descartado {aviso_id}: no sale de su último mensaje ({cita_ultimo[:80]!r})")
        return None
    logger.info(f"[RAG][AVISO_FINAL] {aviso_id} (cita: {cita[:80]!r}): {frase[:160]}")
    return aviso_id, frase


def insertar_frase(answer: str, frase: str) -> str:
    """La frase del aviso en su propio párrafo, sin tocar nada más: antes del último párrafo si este pregunta algo al
    cliente (la pregunta sigue siendo lo último que lee), y si no, al final."""
    frase = frase.strip()
    texto = answer.rstrip()
    if not frase:
        return answer
    parrafos = texto.split("\n\n")
    if len(parrafos) > 1 and parrafos[-1].rstrip().endswith("?"):
        return "\n\n".join([*parrafos[:-1], frase, parrafos[-1]])
    return f"{texto}\n\n{frase}"
