"""ARQ-1d (22-oct, fase ARQ: el modelo interpreta, el código decide, el modelo redacta): el REDACTOR de hechos.

Diseño: `docs/robustness/arq/diseno-intenciones-y-hechos.md` §3. Si Jev dice que el mensaje solo pide intenciones de la
tabla (precio, qué incluye, requisitos, horario, disponibilidad, edad, enlace) y se sabe de qué actividad habla, el
código saca los hechos (`src/flows/hechos.py`) y Luna solo los pone en palabras, con el estilo de Coral y sin el
catálogo, las políticas ni las reglas del RAG (el 21-oct, con todo eso delante, recortaba las listas que tenía). Lo
demás sigue en el RAG de siempre: aquí se devuelve None y contesta él. Con el flag `hechos_por_codigo` apagado no se
llama.
"""
from __future__ import annotations

import copy
import json
import logging

from openai import AsyncOpenAI

from src.agents.grounding_check import (
    contains_phone_number,
    currency_amounts_grounded,
    is_coherent_text,
    urls_grounded,
)
from src.config import settings
from src.domain import activities as dom
from src.flows import hechos as hechos_mod
from src.flows.state import ConversationState
from src.llm_client import trace_openai
from src.privacy import redact_pii

logger = logging.getLogger("uvicorn.error")

# Mensajes anteriores que ve el redactor: para el tono y no volver a saludar, no para sacar datos (los datos son los
# hechos).
_HISTORIAL = 6
_LUGAR_DE_JEV = {"cartagena": "cartagena", "islands": "island"}
# La palabra con la que el redactor dice que los hechos no contestan lo que pregunta (ver REDACTOR_HECHOS_*).
_FALTA = "FALTA"


def _actividad(state: ConversationState, datos: dict) -> str | None:
    """La actividad de la que pregunta ESTE mensaje (extractor) o, si no nombra ninguna, la de la conversación SI es
    una sola. arq-1k (G10 nº 2): hablaban de snorkel para los niños y de buceo para el padre, «¿qué incluye?» y el
    redactor contestaba lo del buceo; con varias en juego no se adivina: contesta el RAG, que ve la conversación."""
    for actividad in (datos.get("actividad_preguntada"), datos.get("activity")):
        if actividad and dom.by_id(actividad) is not None:
            return actividad
    elegida = dom.activity_for_service(state.selected_service) if state.selected_service else None
    reparto = state.detected_group_allocation or {}
    en_juego = {a for a in (state.actividad_preguntada, state.detected_activity, elegida.id if elegida else None,
                            *(a for a, n in reparto.items() if n)) if a and dom.by_id(a) is not None}
    if len(en_juego) == 1:
        return en_juego.pop()
    if not en_juego and state.suggested_activity and dom.by_id(state.suggested_activity) is not None:
        return state.suggested_activity  # la que acaba de proponer el bot («¿y qué incluye?»)
    return None


def _actividades(state: ConversationState, datos: dict) -> list[str]:
    """arq-1j (flag `varias_actividades`): todas las del mensaje si nombra dos o más («¿cuánto pagamos un buzo y un
    acompañante?»); si no, la de siempre."""
    if settings.varias_actividades:
        varias = [a for a in dict.fromkeys(datos.get("actividades_preguntadas") or []) if dom.by_id(a) is not None]
        if len(varias) >= 2:
            return varias
    una = _actividad(state, datos)
    return [una] if una else []


def _origen(state: ConversationState, datos: dict) -> str | None:
    for lugar in (state.location, state.detected_location, datos.get("location")):
        if lugar in hechos_mod.ORIGENES:
            return lugar
    from src.agents.jev_router import CUSTOMER_PLACE_MIN  # lazy

    lugar = getattr(state, "_jev_lugar", None) or {}  # gen-15: «nos alojamos en Mulata» lo dice Jev, no una palabra
    if (lugar.get("confidence") or 0.0) >= CUSTOMER_PLACE_MIN:
        return _LUGAR_DE_JEV.get(lugar.get("choice"))
    return None


def _foto(state: ConversationState, datos: dict, origen: str | None) -> ConversationState:
    """Una copia del estado con lo que dice ESTE mensaje (origen y nacionalidad): la extracción aún no lo ha guardado
    cuando se contesta (como gen-14 en el RAG). El estado de verdad lo sigue escribiendo la extracción."""
    foto = copy.copy(state)
    foto.location = origen
    if foto.is_colombian is None and datos.get("is_colombian") is not None:
        foto.is_colombian = datos["is_colombian"]
    if datos.get("mixed_nationality") is True:
        foto.mixed_nationality_notice = True
    return foto


def _cubierta(bloque: dict, intencion: str) -> bool:
    """¿Los hechos traen algo para esta intención? Si no (una edad que el registro no tiene, un plan sin horario),
    contesta el RAG."""
    valor = bloque.get(intencion)
    if intencion == "horario" and not valor:
        valor = bloque.get("horario_general")
    if isinstance(valor, dict):
        return any(v for v in valor.values())
    return bool(valor)


def _mensajes(lang: str, history: list[dict], message: str, texto_hechos: str) -> list[dict]:
    from src.agents.rag_agent import _build_tone_section  # lazy
    from src.prompts.info import (  # lazy
        RAG_INTRO_EN,
        RAG_INTRO_ES,
        RAG_SECURITY_EN,
        RAG_SECURITY_ES,
        REDACTOR_HECHOS_EN,
        REDACTOR_HECHOS_ES,
    )

    if lang == "es":
        system = (f"{RAG_INTRO_ES}\n\n{RAG_SECURITY_ES}\nEstilo y tono:\n{_build_tone_section('es')}\n\n"
                  f"{REDACTOR_HECHOS_ES}")
        user = f"Hechos:\n{texto_hechos}\n\nPregunta del cliente: {redact_pii(message)}"
    else:
        system = (f"{RAG_INTRO_EN}\n\n{RAG_SECURITY_EN}\nStyle and tone:\n{_build_tone_section('en')}\n\n"
                  f"{REDACTOR_HECHOS_EN}")
        user = f"Facts:\n{texto_hechos}\n\nCustomer's question: {redact_pii(message)}"
    previos = list(history or [])
    if previos and previos[-1].get("role") == "user" and previos[-1].get("content") == message:
        previos = previos[:-1]  # el mensaje va abajo, con los hechos
    return [{"role": "system", "content": system},
            *({"role": m["role"], "content": redact_pii(m.get("content") or "")} for m in previos[-_HISTORIAL:]),
            {"role": "user", "content": user}]


async def _redactar(client, mensajes: list[dict]) -> str | None:
    from src.agents.rag_agent import generar_con_respaldo  # lazy

    try:
        respuesta = await generar_con_respaldo(client, mensajes, pieza="redactor_hechos")
    except Exception as exc:  # noqa: BLE001 — sin redacción, contesta el RAG
        logger.warning(f"[HECHOS] el redactor falló: {exc!r}")
        return None
    return (respuesta.choices[0].message.content or "").strip()


def _pasa_las_guardas(answer: str, texto_hechos: str, message: str) -> bool:
    """Las guardas deterministas de siempre: ni importes, ni enlaces, ni teléfonos que no estén en los hechos."""
    return (is_coherent_text(answer) and currency_amounts_grounded(answer, f"{texto_hechos}\n{message}")
            and urls_grounded(answer, texto_hechos) and not contains_phone_number(answer))


def _pide_los_que_faltan(perdidos: list[str], lang: str) -> str:
    lista = "\n".join(f"- {p}" for p in perdidos)
    if lang == "es":
        return (f"A tu respuesta le faltan estos hechos:\n{lista}\nEscríbela de nuevo entera, con el mismo estilo, "
                "incluyéndolos todos (y sin quitar nada de lo que ya decía).")
    return (f"Your answer is missing these facts:\n{lista}\nWrite it again in full, in the same style, including all "
            "of them (and without removing anything it already said).")


async def hechos_del_turno(state: ConversationState, message: str, history: list[dict]) -> tuple[list[dict], list[str]] | None:
    """Los hechos de las intenciones de este mensaje que el código sabe dar (bloques, intenciones cubiertas), o None si
    no hay: Jev no da intenciones, la pregunta no es la del mensaje de ahora o no se sabe la actividad. No mira si el
    mensaje trae algo más: eso lo decide quien llama (el redactor, o el RAG en los mensajes mezclados, arq-1g)."""
    intenciones = list(getattr(state, "_intenciones", None) or [])
    if not intenciones:
        return None
    ultimo = next((h.get("content") for h in reversed(history or []) if h.get("role") == "user"), None)
    if ultimo != message:
        # La pregunta guardada que se contesta en un turno posterior (el precio tras decir el origen): las intenciones
        # de Jev son las del mensaje de ahora, no las suyas.
        return None
    from src.agents.nucleo.extractor import lectura_del_extractor  # lazy

    datos = await lectura_del_extractor(state, message) or {}
    actividades = _actividades(state, datos)
    if not actividades:
        return None
    bloques = hechos_mod.hechos(_foto(state, datos, _origen(state, datos)), intenciones, actividades)
    cubiertas = [i for i in intenciones if any(_cubierta(b, i) for b in bloques)]
    return (bloques, cubiertas) if cubiertas else None


def texto_de_los_hechos(bloques: list[dict]) -> str:
    """Los hechos en JSON para el modelo. `pregunta_pendiente` es del código (la pregunta la pone él): con ella delante,
    Luna preguntaba el origen en vez de dar los dos enlaces (banco arq-1d, k2 2 de 3)."""
    return json.dumps([{k: v for k, v in b.items() if k != "pregunta_pendiente"} for b in bloques],
                      ensure_ascii=False, indent=1)


async def responder(state: ConversationState, message: str, history: list[dict]) -> str | None:
    """La respuesta escrita con los hechos del código, o None si este mensaje no es para el redactor (y contesta el
    RAG): Jev no da intenciones o no está seguro de que no traiga otra cosa, no se sabe la actividad, los hechos no
    cubren alguna intención, o la redacción no pasa las guardas deterministas (importes, enlaces, teléfonos)."""
    if getattr(state, "_otra_cosa", None) is not False:
        return None
    turno = await hechos_del_turno(state, message, history)
    if turno is None:
        return None
    from src.observability import note_turn  # lazy

    bloques, cubiertas = turno
    intenciones = list(getattr(state, "_intenciones", None) or [])
    actividad = bloques[0]["actividad"]
    origen = bloques[0].get("origen")
    if cubiertas != intenciones:
        logger.info(f"[HECHOS] {actividad}: los hechos no cubren {intenciones}; contesta el RAG")
        return None
    lang = "es" if state.language == "es" else "en"
    texto_hechos = texto_de_los_hechos(bloques)
    client = trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
    mensajes = _mensajes(lang, history, message, texto_hechos)
    answer = await _redactar(client, mensajes)
    if answer is None:
        return None
    if _FALTA in answer:
        # Pregunta algo que los hechos no traen (Jev no marcó esa intención: «what time do we meet» a 0,72 en un mensaje
        # de tres preguntas, banco arq-1d v3). Mejor el RAG, con toda la base, que un «no tengo ese dato». Se mira en
        # todo el texto, en mayúsculas: la escribió en medio (banco D, v2) y al final de una frase (core B2: «I don't
        # have the price for the refresher. FALTA»), y las dos veces le habría llegado al cliente.
        logger.info(f"[HECHOS] el redactor dice que falta algo ({intenciones}); contesta el RAG")
        note_turn(hechos_por_codigo="falta")
        state._redactor_dijo_falta = True  # arq-1g: el mensaje era mezclado; el RAG recibe los hechos
        return None
    if not _pasa_las_guardas(answer, texto_hechos, message):
        logger.info("[HECHOS] la redacción no pasa las guardas deterministas; contesta el RAG")
        note_turn(hechos_por_codigo="guardas")
        return None
    perdidos = hechos_mod.faltan(answer, bloques, intenciones)
    if perdidos:
        # ARQ-3: el código comprueba que la respuesta lleva los hechos (en el banco G, el referido sin la carta de
        # referido firmada, el Advanced sin las 18 h antes de volar). Se rehace UNA vez diciendo cuáles; vale la que deje
        # menos fuera y pase lo mismo que la primera.
        otra = await _redactar(client, [*mensajes, {"role": "assistant", "content": answer},
                                        {"role": "user", "content": _pide_los_que_faltan(perdidos, lang)}])
        quedan = hechos_mod.faltan(otra, bloques, intenciones) if otra else perdidos
        mejor = (otra is not None and _FALTA not in otra and _pasa_las_guardas(otra, texto_hechos, message)
                 and len(quedan) < len(perdidos))
        logger.info(f"[HECHOS][ARQ3] faltaban {len(perdidos)}, tras rehacer {len(quedan)}"
                    f"{'' if mejor else ' (se queda la primera)'}: {[p[:60] for p in perdidos]}")
        note_turn(hechos_faltaban=len(perdidos), hechos_quedan=len(quedan) if mejor else len(perdidos))
        if mejor:
            answer = otra
    if any(b.get("pregunta_pendiente") == "origen" for b in bloques):
        # La pregunta del origen la pone el código, con el texto que reconoce el flujo (`_es_pregunta_de_origen`): así
        # queda pendiente el origen y, cuando lo diga, se le contesta el plan exacto, como en ord-7.
        from src.agents import conversational_core as core  # lazy

        tras = ((core.ORIGEN_TRAS_LOS_ENLACES_ES, core.ORIGEN_TRAS_LOS_ENLACES_EN) if "enlace" in intenciones
                else (core.ORIGEN_TRAS_LAS_VARIANTES_ES, core.ORIGEN_TRAS_LAS_VARIANTES_EN))
        answer = f"{answer}\n\n{tras[0] if lang == 'es' else tras[1]}"
    logger.info(f"[HECHOS] contesta el redactor: {actividad} {intenciones} origen={origen}")
    note_turn(rag_used=True, hechos_por_codigo="redactor", intenciones=",".join(intenciones))
    return answer
