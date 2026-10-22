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
    """La actividad de la que pregunta ESTE mensaje (extractor) o, si no nombra ninguna, la de la conversación."""
    elegida = dom.activity_for_service(state.selected_service) if state.selected_service else None
    for actividad in (datos.get("actividad_preguntada"), datos.get("activity"), state.actividad_preguntada,
                      state.detected_activity, state.suggested_activity, elegida.id if elegida else None):
        if actividad and dom.by_id(actividad) is not None:
            return actividad
    return None


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


async def responder(state: ConversationState, message: str, history: list[dict]) -> str | None:
    """La respuesta escrita con los hechos del código, o None si este mensaje no es para el redactor (y contesta el
    RAG): Jev no da intenciones o no está seguro de que no traiga otra cosa, no se sabe la actividad, los hechos no
    cubren alguna intención, o la redacción no pasa las guardas deterministas (importes, enlaces, teléfonos)."""
    intenciones = list(getattr(state, "_intenciones", None) or [])
    if not intenciones or getattr(state, "_otra_cosa", None) is not False:
        return None
    ultimo = next((h.get("content") for h in reversed(history or []) if h.get("role") == "user"), None)
    if ultimo != message:
        # La pregunta guardada que se contesta en un turno posterior (el precio tras decir el origen): las intenciones
        # de Jev son las del mensaje de ahora, no las suyas.
        return None
    from src.agents.nucleo.extractor import lectura_del_extractor  # lazy
    from src.observability import note_turn  # lazy

    datos = await lectura_del_extractor(state, message) or {}
    actividad = _actividad(state, datos)
    if actividad is None:
        return None
    origen = _origen(state, datos)
    bloques = hechos_mod.hechos(_foto(state, datos, origen), intenciones, [actividad])
    if not bloques or not all(_cubierta(bloques[0], i) for i in intenciones):
        logger.info(f"[HECHOS] {actividad}: los hechos no cubren {intenciones}; contesta el RAG")
        return None
    lang = "es" if state.language == "es" else "en"
    # `pregunta_pendiente` es del código (la pregunta la pone él, abajo): con ella delante, Luna preguntaba el origen
    # en vez de dar los dos enlaces (banco arq-1d, k2 2 de 3).
    texto_hechos = json.dumps([{k: v for k, v in b.items() if k != "pregunta_pendiente"} for b in bloques],
                              ensure_ascii=False, indent=1)
    from src.agents.rag_agent import generar_con_respaldo  # lazy

    client = trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
    try:
        respuesta = await generar_con_respaldo(client, _mensajes(lang, history, message, texto_hechos),
                                               pieza="redactor_hechos")
    except Exception as exc:  # noqa: BLE001 — sin redacción, contesta el RAG
        logger.warning(f"[HECHOS] el redactor falló: {exc!r}")
        return None
    answer = (respuesta.choices[0].message.content or "").strip()
    if answer.strip(" .*_").upper() == _FALTA:
        # Pregunta algo que los hechos no traen (Jev no marcó esa intención: «what time do we meet» a 0,72 en un mensaje
        # de tres preguntas, banco arq-1d v3). Mejor el RAG, con toda la base, que un «no tengo ese dato».
        logger.info(f"[HECHOS] el redactor dice que falta algo ({intenciones}); contesta el RAG")
        note_turn(hechos_por_codigo="falta")
        return None
    if not (is_coherent_text(answer) and currency_amounts_grounded(answer, f"{texto_hechos}\n{message}")
            and urls_grounded(answer, texto_hechos) and not contains_phone_number(answer)):
        logger.info("[HECHOS] la redacción no pasa las guardas deterministas; contesta el RAG")
        note_turn(hechos_por_codigo="guardas")
        return None
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
