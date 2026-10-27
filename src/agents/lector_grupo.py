"""CALN-2 (27-oct): el lector del grupo. Diseño: `docs/robustness/caln/diseno-caln2-lector-grupo.md`.

Una lectura aparte del extractor, con su propio esquema: la lista de las personas del grupo (quién, cuántas iguales, si
está certificada, qué actividad ELIGE, sus edades), cada entrada con su cita comprobada en el mensaje. El extractor no
cambia (diseño del grupo, paso 3b: un campo más en su esquema le hacía dejar el reparto).

Paso 1 (aprobado por Gadea, #2231): NO está enchufado. Se mide solo con `scripts/medir_lector_grupo.py`.
"""
from __future__ import annotations

import json
import logging
import time

from openai import AsyncOpenAI

from src.agents.extractor_turno import (
    _actividades,
    _json_de_la_respuesta,
    cita_verificable,
    edades_citadas,
    ultima_pregunta_del_bot,
)
from src.config import settings
from src.domain import activities as dom
from src.llm_client import trace_openai
from src.observability import pieza_llm

logger = logging.getLogger("uvicorn.error")

SISTEMA_ES = """Lees UN mensaje de un cliente de un centro de buceo y devuelves las personas del grupo que van, contando a quien escribe. Solo lo que el mensaje dice: no adivines nada.

Cada entrada es una persona o varias iguales («4 tenemos certificación» = una entrada con cantidad 4; «los niños, de 7 y 4» = una entrada con cantidad 2):
- quien: "cliente" para quien escribe, junto con quienes nombra con él en la misma frase («mi hermana y yo» = una entrada "cliente" con cantidad 2; «4 tenemos certificación» = cantidad 4); para los demás, cómo los nombra ("esposo", "niños", "amiga", "los otros dos"). Nadie va en dos entradas.
- cantidad: cuántas personas son en esa entrada.
- certificado: true si el mensaje dice que tiene certificación de buceo (Open Water, Advanced, «buzo certificado»); false si dice que no la tiene, que no bucea o que nunca ha buceado; null si no lo dice.
- actividad: la que ELIGE, de esta lista (el id); null si no la elige. Si varios eligen juntos («mi hija y yo queremos el minicurso»), es la de todos ellos. Tener una certificación («soy Advanced», «tiene el Open Water», «es buzo certificado») es certificado true, NO una actividad ni un curso. Decir que no bucea, que nunca ha buceado o que quiere «probar algo» tampoco es elegir. companion solo si dice que NO se mete al agua y solo acompaña («no se mete al agua», «solo viene en la lancha»). No bucear no es acompañar: «mi amiga no bucea» = certificado false y actividad null (puede hacer snorkel).
{actividades}
- edades: las que dice de esa entrada; [] si no las dice.
- cita: el trozo del mensaje, copiado tal cual, que habla de esa entrada.

total_dicho: el número de personas si el mensaje lo dice con una cifra o palabra («somos 5», «familia de 5»); si no, null.
Si el mensaje no habla de nadie más que de quien escribe, personas tiene solo su entrada (o [] si tampoco dice nada de sí mismo).

Responde SOLO con un objeto JSON (sin texto antes ni después, sin ```):
{"total_dicho": int|null, "personas": [{"quien": str, "cantidad": int, "certificado": bool|null, "actividad": str|null, "edades": [int], "cita": str}]}"""

SISTEMA_EN = """You read ONE message from a customer of a dive center and return the people in the group who are going, counting the writer. Only what the message says: do not guess anything.

Each entry is one person or several alike ("4 of us are certified" = one entry with quantity 4; "the kids, 7 and 4" = one entry with quantity 2):
- quien: "cliente" for the writer, together with those they name with them in the same sentence ("my sister and I" = one "cliente" entry with quantity 2; "4 of us are certified" = quantity 4); for the others, how they name them ("husband", "kids", "friend", "the other two"). Nobody goes in two entries.
- cantidad: how many people are in that entry.
- certificado: true if the message says they have a diving certification (Open Water, Advanced, "certified diver"); false if it says they do not have one, do not dive or have never dived; null if it does not say.
- actividad: the one they CHOOSE, from this list (the id); null if they do not choose. If several choose together ("my daughter and I want the mini course"), it is everyone's. Having a certification ("I'm Advanced", "she has her Open Water", "he's a certified diver") is certificado true, NOT an activity or a course. Saying they do not dive, that they have never dived or that they want to "try something" is not choosing either. companion only if it says they will NOT get in the water and only come along ("doesn't get in the water", "just comes on the boat"). Not diving is not coming along: "my friend doesn't dive" = certificado false and actividad null (they could snorkel).
{actividades}
- edades: the ages it gives for that entry; [] if none.
- cita: the piece of the message, copied verbatim, that talks about that entry.

total_dicho: the number of people if the message gives it with a number or word ("we are 5", "family of 5"); otherwise null.
If the message talks about nobody but the writer, personas has only their entry (or [] if it says nothing about them either).

Answer ONLY with a JSON object (no text before or after, no ```):
{"total_dicho": int|null, "personas": [{"quien": str, "cantidad": int, "certificado": bool|null, "actividad": str|null, "edades": [int], "cita": str}]}"""


def _contexto(mensaje: str, history: list[dict] | None, lang: str) -> str:
    pregunta = ultima_pregunta_del_bot(history)
    if lang == "es":
        return (f"Última pregunta del bot (solo para entender una respuesta corta): {pregunta or '(ninguna)'}\n\n"
                f"MENSAJE DEL CLIENTE:\n{mensaje}")
    return f"Bot's last question (only to understand a short answer): {pregunta or '(none)'}\n\nCUSTOMER MESSAGE:\n{mensaje}"


def validar(datos: dict, mensaje: str) -> dict:
    """Lo que el código acepta de la lectura: entradas con cita comprobada, cantidad entera, actividad del registro,
    edades que están en su cita. Lo descartado va en `descartes` (para contar los inventos)."""
    personas, descartes = [], []
    clientes = 0
    for p in datos.get("personas") or []:
        if not isinstance(p, dict):
            continue
        cita = p.get("cita") if isinstance(p.get("cita"), str) else ""
        if not cita_verificable(cita, mensaje):
            descartes.append({"motivo": "cita", **p})
            continue
        cantidad = p.get("cantidad")
        if not isinstance(cantidad, int) or isinstance(cantidad, bool) or not 1 <= cantidad <= 50:
            descartes.append({"motivo": "cantidad", **p})
            continue
        quien = str(p.get("quien") or "").strip().lower() or "?"
        if quien == "cliente":
            clientes += 1
            if clientes > 1:
                descartes.append({"motivo": "dos clientes", **p})
                continue
        actividad = p.get("actividad") if p.get("actividad") in dom.activity_ids() else None
        certificado = p.get("certificado") if isinstance(p.get("certificado"), bool) else None
        if actividad == "padi_open_water" and certificado is True:
            actividad = None  # quien ya está certificado no se saca el Open Water (la regla de DEUDA-EXT2 del extractor)
        personas.append({"quien": quien, "cantidad": cantidad, "certificado": certificado, "actividad": actividad,
                         "edades": edades_citadas(p.get("edades"), cita)[:cantidad], "cita": cita})
    total = datos.get("total_dicho")
    total = total if isinstance(total, int) and not isinstance(total, bool) and 1 <= total <= 50 else None
    return {"total_dicho": total, "personas": personas, "descartes": descartes}


def total_de(lectura: dict | None) -> int | None:
    """Cuántos son según la lectura: el total dicho o, si no, la suma de las entradas (None sin nadie)."""
    if not lectura:
        return None
    suma = sum(p["cantidad"] for p in lectura["personas"])
    return lectura["total_dicho"] or suma or None


async def leer_grupo(mensaje: str, *, history: list[dict] | None = None, lang: str = "es", modelo: str | None = None,
                     client: AsyncOpenAI | None = None) -> dict | None:
    """La lista de personas que dice `mensaje` (ver `validar`), con `segundos`; None si la llamada falló."""
    if not mensaje or not mensaje.strip():
        return {"total_dicho": None, "personas": [], "descartes": [], "segundos": 0.0}
    sistema = (SISTEMA_ES if lang == "es" else SISTEMA_EN).replace("{actividades}", _actividades(lang))
    t0 = time.perf_counter()
    try:
        client = client or trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        with pieza_llm("lector_grupo"):
            resp = await client.chat.completions.create(
                model=modelo or settings.extractor_turno_model,
                messages=[{"role": "system", "content": sistema},
                          {"role": "user", "content": _contexto(mensaje, history, lang)}],
                temperature=0.0,
                max_tokens=500,
            )
        datos = _json_de_la_respuesta(resp.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001 — sin lectura, el turno sigue con lo del extractor
        logger.warning(f"[LECTOR_GRUPO][DEGRADED] {exc}")
        return None
    salida = validar(datos if isinstance(datos, dict) else {}, mensaje)
    salida["segundos"] = time.perf_counter() - t0
    return salida


def para_el_log(lectura: dict | None) -> str:
    return json.dumps({k: v for k, v in (lectura or {}).items() if k != "descartes"}, ensure_ascii=False)
