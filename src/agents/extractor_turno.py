"""ex-4 (fase EX, 12-oct): el extractor "LLM primero" — entender el mensaje del cliente con UNA llamada.

Hoy el regex lee primero y manda, y las redes LLM solo rellenan huecos leyendo el historial entero como turnos de chat:
en el banco ex-0 eso inventa datos en el 22,8 % de los casos ("gracias" → buceo certificado; "Muchas gracias!" →
colombiano). Aquí, en cambio:

1. El modelo ve SOLO el mensaje del cliente, la última pregunta del bot (para entender respuestas cortas) y lo que ya
   sabemos; nunca el historial como turnos de chat.
2. Cada dato trae su CITA del mensaje del cliente, y el código comprueba que la cita está de verdad en el mensaje: sin
   cita verificable no hay dato (lo que el modelo saque del historial o del texto del bot no puede pasar).
3. Las pistas seguras (la lista cerrada de hoteles e islas del Rosario) van en el prompt; el regex no decide.

Si la llamada falla, devuelve {} y el turno sigue con lo de hoy (degradación). Medida: `scripts.run_extraction_eval
--banco ex0 --modo llm-primero`. Plan: docs/robustness/regex/plan-ex-entender-con-ia.md.
"""
from __future__ import annotations

import json
import logging
import re
import time

from openai import AsyncOpenAI

from src.config import settings
from src.llm_client import trace_openai
from src.utils.text import strip_accents

logger = logging.getLogger("uvicorn.error")

CAMPOS = ("activity", "is_certified", "group_size", "group_allocation", "location", "is_colombian",
          "last_dive_over_2_years")
ACTIVIDADES = ("certified_diving", "minicourse", "snorkel", "padi_open_water", "padi_open_water_referral",
               "padi_advanced", "padi_rescue", "padi_divemaster", "padi_specialty")
# Respuestas cortas a la pregunta del bot ("no", "1", "sí"): la cita es el mensaje entero.
_CITA_MIN_PALABRAS_SOLAS = 1


def _dato(tipo: dict, descripcion: str) -> dict:
    return {
        "type": ["object", "null"],
        "description": descripcion + " null si el cliente no lo AFIRMA en su mensaje.",
        "properties": {"valor": tipo, "cita": {"type": "string",
                                                "description": "Las palabras EXACTAS del mensaje del cliente que lo dicen."}},
        "required": ["valor", "cita"],
        "additionalProperties": False,
    }


ESQUEMA = {
    "type": "object",
    "properties": {
        "activity": _dato({"type": "string", "enum": list(ACTIVIDADES)}, "La actividad que el cliente ELIGE para sí."),
        "is_certified": _dato({"type": "boolean"}, "Si quien escribe (o su grupo) YA es buzo certificado."),
        "group_size": _dato({"type": "integer"}, "Cuántas personas van en total en el plan."),
        "group_allocation": _dato({"type": "object", "properties": {a: {"type": ["integer", "null"]} for a in ACTIVIDADES},
                                   "required": list(ACTIVIDADES), "additionalProperties": False},
                                  "Cuántas personas hacen cada actividad, solo si el grupo se reparte entre VARIAS."),
        "location": _dato({"type": "string", "enum": ["cartagena", "island"]},
                          "Desde dónde SALE el cliente: 'cartagena' si sale de Cartagena; 'island' si ya está alojado "
                          "en las Islas del Rosario."),
        "is_colombian": _dato({"type": "boolean"}, "Si quien escribe es colombiano o residente en Colombia."),
        "last_dive_over_2_years": _dato({"type": "boolean"}, "Si su última inmersión fue hace MÁS de 2 años."),
    },
    "required": list(CAMPOS),
    "additionalProperties": False,
}


def _pistas_islas() -> str:
    from src.agents.rag_agent import (
        AMBIGUOUS_LOCATION_NAMES,  # lazy: lista cerrada de hoteles e islas del Rosario
    )

    return ", ".join(AMBIGUOUS_LOCATION_NAMES)


SISTEMA_ES = """Eres el lector de mensajes de Coral, la asistente de reservas de Diving Planet (buceo y snorkel en las Islas del Rosario, saliendo desde Cartagena o desde las propias islas). Lees UN mensaje del cliente y devuelves SOLO los datos de la reserva que el cliente AFIRMA en ese mensaje, cada uno con la cita exacta de sus palabras.

Reglas:
- Solo lo que el cliente afirma de sí mismo o de su grupo en ESTE mensaje. Una pregunta ("¿puedo bucear embarazada?", "¿cuánto cuesta el buceo certificado?"), una hipótesis ("si decidiera hacer el curso…") o algo que nombra sin elegirlo no es un dato.
- Lo que el cliente dice de OTRA persona ("él no es certificado") no cambia los datos de quien escribe; sí puede servir para el reparto del grupo.
- Lo que el cliente dice de OTRA persona que hace algo distinto ("él quiere hacer snorkel") va en group_allocation junto con lo que ya sabemos de quien escribe.
- Usa la pregunta que el bot acaba de hacer solo para entender una respuesta corta ("no" o "no, hace poco buceé" a "¿han pasado más de 2 años?" = last_dive_over_2_years false; "1" a "¿cuántas personas?" = group_size 1). Nunca saques datos del texto del bot.
- No repitas lo que ya sabemos salvo que el cliente lo cambie en este mensaje.
- activity: certified_diving = salidas o paquetes de buceo para buzos certificados (fun dive); minicourse = probar el buceo por primera vez, bautismo, principiante sin certificación; snorkel; padi_open_water = sacarse la certificación, curso básico (o Open Water); padi_open_water_referral = terminar aquí un Open Water empezado en otro centro (referido); padi_advanced = HACER el curso avanzado (si dice que YA es Advanced, eso es is_certified true, no este curso). "Quiero bucear" a secas no elige actividad. Si dice que ya es buzo certificado (u Open Water, Advanced…) y quiere bucear o pide salidas o paquetes de buceo, activity = certified_diving e is_certified = true.
- location: desde dónde sale. Si dice que está, estará, va o viene a Cartagena ("estoy en Cartagena", "vamos a Cartagena", "bucear en Cartagena", "estaremos visitando Cartagena") y no dice que se aloja en las islas → cartagena. Alojado en las islas, en un hotel de las islas o "sin ir de Cartagena" → island (nombrar las islas como el sitio donde se bucea no basta). Llegar mañana sin decir dónde, o preguntar por un hotel, por el punto de encuentro ("¿dónde es el punto de encuentro en Cartagena?") o por de dónde sale la lancha NO es su ubicación. La cita de location tiene que nombrar el lugar (Cartagena, las islas, un hotel).
- is_colombian: colombiano o residente en Colombia (también si pide para sí el precio "para colombianos"). Un grupo con nacionalidades mezcladas → null.
- group_size: solo si dice CUÁNTAS personas van ("voy solo", "solo yo" = 1; "somos 3" = 3; "mi pareja y yo" = 2). Hablar en primera persona ("yo", "quiero") no dice el tamaño del grupo.
- last_dive_over_2_years: true solo si su última inmersión fue hace MÁS de 2 años; "1,5 años", "el año pasado" o "hace poco" = false.
- Si los datos están en partes distintas del mensaje, la cita puede ser varios trozos literales separados por " … ".
- La cita debe ser texto copiado literalmente del mensaje del cliente.

Hoteles e islas del Rosario (si el cliente está alojado en uno, location = island): {islas}"""

SISTEMA_EN = """You read messages for Coral, the booking assistant of Diving Planet (diving and snorkeling in the Rosario Islands, departing from Cartagena or from the islands). You read ONE customer message and return ONLY the booking facts the customer STATES in that message, each with the exact quote of their words.

Rules:
- Only what the customer states about themselves or their group in THIS message. A question ("can I dive pregnant?", "how much is certified diving?"), a hypothesis ("in case I decided to do the course…") or something they mention without choosing it is not a fact.
- What the customer says about ANOTHER person ("he isn't certified") does not change the writer's facts; it may count for the group split.
- What the customer says about ANOTHER person doing something different ("he wants to snorkel") goes into group_allocation together with what we already know about the writer.
- Use the bot's last question only to understand a short answer ("no" or "no, I dove recently" to "has it been more than 2 years?" = last_dive_over_2_years false; "1" to "how many people?" = group_size 1). Never take facts from the bot's text.
- Do not repeat what we already know unless the customer changes it in this message.
- activity: certified_diving = dive trips or packages for certified divers (fun dives); minicourse = trying diving for the first time, discover scuba, beginner without certification; snorkel; padi_open_water = getting certified, basic course (Open Water); padi_open_water_referral = finishing here an Open Water started at another center (referral); padi_advanced = TAKING the advanced course (if they say they ARE Advanced, that is is_certified true, not this course). "I want to dive" alone does not choose an activity. If they say they are already a certified diver (or Open Water, Advanced…) and want to dive or ask for dive trips or packages, activity = certified_diving and is_certified = true.
- location: where they depart from. If they say they are, will be, are going to or are visiting Cartagena ("I'm in Cartagena", "we'll be in Cartagena", "diving in Cartagena") and do not say they stay on the islands → cartagena. Staying on the islands or at an island hotel → island (naming the islands as the place where you dive is not enough). Arriving tomorrow without saying where, or asking about a hotel, the meeting point ("where is the meeting point in Cartagena?") or where the boat leaves from is NOT their location. The location quote must name the place (Cartagena, the islands, a hotel).
- is_colombian: Colombian or resident of Colombia (also if they ask for themselves the price "for Colombians"). A group of mixed nationalities → null.
- group_size: only if they say HOW MANY people go ("just me" = 1; "we are 3" = 3; "my partner and I" = 2). Speaking in first person ("I", "I want") does not give the group size.
- last_dive_over_2_years: true only if their last dive was MORE than 2 years ago; "1.5 years", "last year" or "recently" = false.
- If the facts are in different parts of the message, the quote may be several literal pieces separated by " … ".
- The quote must be text copied literally from the customer's message.

Rosario hotels and islands (if the customer is staying at one, location = island): {islas}"""


def _norm(texto: str) -> list[str]:
    return re.findall(r"\w+", strip_accents(texto or "").lower())


def _trozo_en(c: list[str], m: list[str]) -> bool:
    return any(m[i:i + len(c)] == c for i in range(len(m) - len(c) + 1))


def cita_verificable(cita: str, mensaje: str) -> bool:
    """La cita está de verdad en el mensaje del cliente: sus palabras, en orden y seguidas (ignorando mayúsculas,
    tildes y puntuación); puede venir en varios trozos separados por "…" o "...", y cada trozo tiene que estar. Una
    cita vacía o que no aparece = el dato no sale del mensaje."""
    m = _norm(mensaje)
    trozos = [_norm(t) for t in re.split(r"…|\.\.\.", cita or "")]
    trozos = [t for t in trozos if t]
    return bool(trozos) and all(len(t) >= _CITA_MIN_PALABRAS_SOLAS and _trozo_en(t, m) for t in trozos)


def _lugares() -> set[str]:
    """Palabras de lugar (lista cerrada): Cartagena, islas/hotel y los nombres de hoteles e islas del Rosario."""
    from src.agents.rag_agent import AMBIGUOUS_LOCATION_NAMES  # lazy

    palabras = {"cartagena", "isla", "islas", "island", "islands", "rosario", "hotel", "hostel", "hostal"}
    for nombre in AMBIGUOUS_LOCATION_NAMES:
        palabras.update(w for w in _norm(nombre) if len(w) > 3)
    return palabras


def nombra_un_lugar(cita: str) -> bool:
    """La cita de la ubicación nombra un lugar (como `ORIGEN_DEL_CLIENTE` de s4-28): "im getting in tmrw" no."""
    return bool(set(_norm(cita)) & _lugares())


def _contexto(mensaje: str, pregunta_bot: str | None, sabido: dict, lang: str) -> str:
    sabido_txt = json.dumps({k: v for k, v in (sabido or {}).items() if v not in (None, [], {})}, ensure_ascii=False)
    if lang == "es":
        return (f"Última pregunta del bot (solo para entender una respuesta corta): {pregunta_bot or '(ninguna)'}\n"
                f"Lo que ya sabemos: {sabido_txt}\n\nMENSAJE DEL CLIENTE:\n{mensaje}")
    return (f"Bot's last question (only to understand a short answer): {pregunta_bot or '(none)'}\n"
            f"What we already know: {sabido_txt}\n\nCUSTOMER MESSAGE:\n{mensaje}")


def ultima_pregunta_del_bot(history: list[dict] | None, max_chars: int = 300) -> str | None:
    """El final del último mensaje del bot (donde va su pregunta), para entender respuestas cortas."""
    for turno in reversed(history or []):
        if turno.get("role") == "assistant" and turno.get("content"):
            texto = re.sub(r"\s+", " ", turno["content"]).strip()
            return texto[-max_chars:]
    return None


async def extraer_turno(mensaje: str, *, history: list[dict] | None = None, sabido: dict | None = None,
                        lang: str = "es", modelo: str | None = None, client: AsyncOpenAI | None = None) -> dict | None:
    """{campo: valor} con SOLO los datos que el cliente afirma en `mensaje` y cuya cita se verifica en él; None si la
    llamada falló (el turno sigue con lo de hoy). Los atributos `ultimo_*` de la función son solo para la medida y
    el log (globales: no usarlos para decidir, hay turnos a la vez)."""
    extraer_turno.ultimo_motivo = {}
    if not mensaje or not mensaje.strip():
        return {}
    sistema = (SISTEMA_ES if lang == "es" else SISTEMA_EN).replace("{islas}", _pistas_islas())
    modelo = modelo or settings.extractor_turno_model
    t0 = time.perf_counter()
    try:
        client = client or trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        resp = await client.chat.completions.create(
            model=modelo,
            messages=[{"role": "system", "content": sistema},
                      {"role": "user", "content": _contexto(mensaje, ultima_pregunta_del_bot(history), sabido or {}, lang)}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "datos_del_turno", "strict": True, "schema": ESQUEMA}},
            temperature=0.0,
            max_tokens=400,
        )
        datos = json.loads(resp.choices[0].message.content or "{}")
        uso = getattr(resp, "usage", None)
        detalle = getattr(uso, "prompt_tokens_details", None)
        extraer_turno.ultimo_uso = {"entrada": getattr(uso, "prompt_tokens", 0) or 0,
                                    "cache": getattr(detalle, "cached_tokens", 0) or 0,
                                    "salida": getattr(uso, "completion_tokens", 0) or 0}
    except Exception as exc:  # noqa: BLE001 — nunca romper el turno: se sigue con lo de hoy
        logger.warning(f"[LLM_EXTRACTOR][DEGRADED] extractor_turno: {exc}")
        return None
    extraer_turno.ultimo_segundos = time.perf_counter() - t0
    salida, descartes = {}, {}
    for campo in CAMPOS:
        d = datos.get(campo)
        if not isinstance(d, dict) or d.get("valor") in (None, "", [], {}):
            continue
        valor, cita = d["valor"], d.get("cita") or ""
        if campo == "group_allocation":
            valor = {k: v for k, v in valor.items() if v}
            if len(valor) < 2:  # un reparto de una sola actividad no es un reparto
                continue
        if not cita_verificable(cita, mensaje):
            descartes[campo] = f"cita no está en el mensaje: {cita!r}"
            continue
        if campo == "location" and not nombra_un_lugar(cita):
            descartes[campo] = f"la cita no nombra un lugar: {cita!r}"
            continue
        salida[campo] = valor
    # Regla del catálogo: el buceo certificado exige certificación.
    if salida.get("activity") == "certified_diving" and "is_certified" not in salida:
        salida["is_certified"] = True
    extraer_turno.ultimo_motivo = descartes
    if descartes:
        logger.info(f"[EXTRACT][EX4] descartado sin cita verificable: {descartes}")
    return salida


extraer_turno.ultimo_motivo = {}
extraer_turno.ultimo_segundos = 0.0
extraer_turno.ultimo_uso = {}
