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
- cantidad: cuántas personas son en esa entrada; null si el mensaje no lo dice («unos amigos», «mis primos»: no se sabe cuántos son).
- certificado: true si el mensaje dice que tiene certificación de buceo (Open Water, Advanced, «buzo certificado»); false si dice que no la tiene, que no bucea o que nunca ha buceado; null si no lo dice. Llevar tiempo sin bucear («hace 3 años que no bucea») no dice que no esté certificado: null, o true si dice que lo está.
- actividad: la que ELIGE, de esta lista (el id); null si no la elige. Si varios eligen juntos («mi hija y yo queremos el minicurso»), es la de todos ellos. Tener una certificación («soy Advanced», «tiene el Open Water», «es buzo certificado») es certificado true, NO una actividad ni un curso. Decir que no bucea, que nunca ha buceado o que quiere «probar algo» tampoco es elegir. companion solo si dice que NO se mete al agua y solo acompaña («no se mete al agua», «solo viene en la lancha»). No bucear no es acompañar: «mi amiga no bucea» = certificado false y actividad null (puede hacer snorkel).
{actividades}
- edades: las que dice de esa entrada; [] si no las dice.
- cita: el trozo del mensaje, copiado tal cual, que habla de esa entrada.

total_dicho: el número de personas si el mensaje lo dice con una cifra o palabra («somos 5», «familia de 5»); si no, null.
Si el mensaje no habla de nadie más que de quien escribe, personas tiene solo su entrada (o [] si tampoco dice nada de sí mismo).

Responde SOLO con un objeto JSON (sin texto antes ni después, sin ```):
{"total_dicho": int|null, "personas": [{"quien": str, "cantidad": int|null, "certificado": bool|null, "actividad": str|null, "edades": [int], "cita": str}]}"""

SISTEMA_EN = """You read ONE message from a customer of a dive center and return the people in the group who are going, counting the writer. Only what the message says: do not guess anything.

Each entry is one person or several alike ("4 of us are certified" = one entry with quantity 4; "the kids, 7 and 4" = one entry with quantity 2):
- quien: "cliente" for the writer, together with those they name with them in the same sentence ("my sister and I" = one "cliente" entry with quantity 2; "4 of us are certified" = quantity 4); for the others, how they name them ("husband", "kids", "friend", "the other two"). Nobody goes in two entries.
- cantidad: how many people are in that entry; null if the message does not say ("some friends", "my cousins": we do not know how many).
- certificado: true if the message says they have a diving certification (Open Water, Advanced, "certified diver"); false if it says they do not have one, do not dive or have never dived; null if it does not say. Not having dived for a while ("hasn't been diving in 3 years") does not say they are not certified: null, or true if it says they are.
- actividad: the one they CHOOSE, from this list (the id); null if they do not choose. If several choose together ("my daughter and I want the mini course"), it is everyone's. Having a certification ("I'm Advanced", "she has her Open Water", "he's a certified diver") is certificado true, NOT an activity or a course. Saying they do not dive, that they have never dived or that they want to "try something" is not choosing either. companion only if it says they will NOT get in the water and only come along ("doesn't get in the water", "just comes on the boat"). Not diving is not coming along: "my friend doesn't dive" = certificado false and actividad null (they could snorkel).
{actividades}
- edades: the ages it gives for that entry; [] if none.
- cita: the piece of the message, copied verbatim, that talks about that entry.

total_dicho: the number of people if the message gives it with a number or word ("we are 5", "family of 5"); otherwise null.
If the message talks about nobody but the writer, personas has only their entry (or [] if it says nothing about them either).

Answer ONLY with a JSON object (no text before or after, no ```):
{"total_dicho": int|null, "personas": [{"quien": str, "cantidad": int|null, "certificado": bool|null, "actividad": str|null, "edades": [int], "cita": str}]}"""


def _contexto(mensaje: str, history: list[dict] | None, lang: str) -> str:
    pregunta = ultima_pregunta_del_bot(history)
    if lang == "es":
        return (f"Última pregunta del bot (solo para entender una respuesta corta): {pregunta or '(ninguna)'}\n\n"
                f"MENSAJE DEL CLIENTE:\n{mensaje}")
    return f"Bot's last question (only to understand a short answer): {pregunta or '(none)'}\n\nCUSTOMER MESSAGE:\n{mensaje}"


def validar(datos: dict, mensaje: str) -> dict:
    """Lo que el código acepta de la lectura: entradas con cita comprobada, cantidad entera o None (no dice cuántos:
    «unos amigos»; si las demás ya suman el total dicho, repite el grupo y se quita), actividad del registro, edades
    que están en su cita. Lo descartado va en `descartes` (para contar los inventos)."""
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
        if cantidad is not None and (not isinstance(cantidad, int) or isinstance(cantidad, bool)
                                     or not 1 <= cantidad <= 50):
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
    contadas = [p for p in personas if p["cantidad"] is not None]
    if total and len(contadas) < len(personas) and sum(p["cantidad"] for p in contadas) == total:
        # «somos 6 amigos de Bogotá: 4 tenemos certificación y 2 dudan»: la entrada sin cantidad («somos 6 amigos»)
        # nombra otra vez al grupo entero, que ya cuentan las demás.
        descartes += [{"motivo": "repite el grupo", **p} for p in personas if p["cantidad"] is None]
        personas = contadas
    return {"total_dicho": total, "personas": personas, "descartes": descartes}


def total_de(lectura: dict | None) -> int | None:
    """Cuántos son según la lectura: el total dicho o, si no, la suma de las entradas (None sin nadie, o si de alguna
    no se sabe cuántos son)."""
    if not lectura:
        return None
    if not _contadas(lectura["personas"]):
        return lectura["total_dicho"]
    suma = sum(p["cantidad"] for p in lectura["personas"])
    return lectura["total_dicho"] or suma or None


def _contadas(personas: list[dict]) -> bool:
    return all(isinstance(p["cantidad"], int) for p in personas)


def _suma(reparto: dict | None) -> int:
    return sum(n for n in (reparto or {}).values() if isinstance(n, int) and not isinstance(n, bool))


def por_completar(datos: dict, total_antes: int | None = None, reparto_antes: dict | None = None,
                  jev_otros: bool = False) -> bool:
    """¿Hace falta el lector en este turno? (disparador T2b del paso 1: 601/640 frente a 477/640 sin él.) Si el mensaje
    habla de otras personas y el grupo no queda completo con lo del extractor y lo sabido, o queda alguien sin elegir
    (su certificación decide la recomendación), o es un grupo de 2 o más sin reparto. Es `salta(..., "T2b")` de
    `scripts/medir_lector_grupo.py`, el que se midió, más `jev_otros` (CALN-8, 28-oct): si Jev está seguro de que el
    mensaje mete a otra persona aunque el extractor no diga nada de ella («viene también mi amiga, pero no sabe qué
    quiere hacer»), también: es lo que hacía la red de señales de acompañantes, que se quitó."""
    reparto = datos.get("group_allocation") or reparto_antes
    total = datos.get("group_size") or total_antes
    otros = bool(datos.get("edades") or datos.get("otro_sin_certificar") or datos.get("otro_certificado_inactivo")
                 or (datos.get("group_allocation") and (len(datos["group_allocation"]) > 1
                                                       or {"undecided", "companion"} & set(datos["group_allocation"])))
                 or (isinstance(datos.get("group_size"), int) and datos["group_size"] > 1) or jev_otros)
    if not otros:
        return False
    if not isinstance(total, int):
        return True
    if reparto and _suma(reparto) != total:
        return True
    if not reparto and (datos.get("otro_sin_certificar") or datos.get("edades")):
        return True
    if total < 2:
        return False
    return bool(not reparto or reparto.get("undecided"))


def completar(datos: dict, lectura: dict, total_sabido: int | None = None,
              actividad_sabida: str | None = None) -> tuple[dict, list[str]]:
    """Los datos del extractor con lo que dejó vacío, sacado de la lectura del grupo: el total (si no lo dio), el
    reparto (si no lo dio o no suma el total que dijo, y la lectura cuadra con ese total), la certificación de quien
    escribe (si no la dio) y la de quienes faltan por elegir. Lo que el extractor dio y cuadra no se toca. La
    actividad de quien escribe es la del extractor (con la regla de negocio ya puesta) o, si este turno no la dice, la
    que ya eligió (`actividad_sabida`). Un total ya sabido de la conversación (`total_sabido`) no lo cambia la lectura
    de un mensaje que nombra solo a una parte (g29: «yo el minicurso, la de 14 también y la pequeña Bubble Makers» no
    habla del suegro). Devuelve (datos, qué cambió)."""
    personas = (lectura or {}).get("personas") or []
    if not personas:
        return datos, []
    out, cambios = dict(datos), []
    escritor = out.get("activity") or actividad_sabida
    if (escritor and not any(p["quien"] == "cliente" for p in personas) and not lectura.get("total_dicho")
            and not isinstance(out.get("group_size"), int) and not isinstance(total_sabido, int)):
        # CALN-8 (g19): quien escribe ya eligió («I'd like to do the mini course») y el mensaje habla solo de otro («my
        # husband is certified, he'd like to dive»): quien escribe también va. Con un total dicho o ya sabido no se
        # cuenta: el mensaje puede nombrar solo a una parte del grupo.
        personas = [{"quien": "cliente", "cantidad": 1, "certificado": None, "actividad": None, "edades": [],
                     "cita": ""}, *personas]
        lectura = {**lectura, "personas": personas}
    total_lector = total_de(lectura)
    # Un total de 1 solo porque el mensaje habla de quien escribe no dice que vaya solo: no se pone.
    if (not isinstance(out.get("group_size"), int) and not isinstance(total_sabido, int) and total_lector
            and (lectura.get("total_dicho") or total_lector > 1)):
        out["group_size"] = total_lector
        cambios.append(f"group_size={total_lector}")
    total = out.get("group_size") if isinstance(out.get("group_size"), int) else total_sabido
    reparto = out.get("group_allocation")
    sin_elegir = []
    # El reparto de la lectura, solo si cuenta a todos y suma el total: «somos 6 amigos: 4 tenemos certificación y 2
    # dudan» leído como quien escribe + 4 + 2 suma 7 (b6, 19 de 20 lecturas hasta el 28-oct, que daban {undecided: 7}).
    if (not (reparto and _suma(reparto) == total) and total_lector is not None and total_lector == total
            and _contadas(personas) and sum(p["cantidad"] for p in personas) == total):
        nuevo: dict = {}
        for p in personas:
            n, act = p["cantidad"], p["actividad"]
            if act is None and p["quien"] == "cliente" and escritor:
                nuevo[escritor] = nuevo.get(escritor, 0) + 1
                n -= 1
            if n > 0:
                nuevo[act or "undecided"] = nuevo.get(act or "undecided", 0) + n
                if act is None:
                    sin_elegir.append(p)
        out["group_allocation"] = nuevo
        cambios.append(f"group_allocation={nuevo}")
    else:
        sin_elegir = [p for p in personas if p["actividad"] is None and not (p["quien"] == "cliente" and escritor)]
    if out.get("is_certified") is None and any(p["quien"] == "cliente" and p["certificado"] is True for p in personas):
        out["is_certified"] = True
        cambios.append("is_certified=True")
    certs = {p["certificado"] for p in sin_elegir}
    if sin_elegir and certs in ({True}, {False}):
        out["sin_decidir_certificados"] = certs == {True}
        cambios.append(f"sin_decidir_certificados={certs == {True}}")
    return out, cambios


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
    uso = getattr(resp, "usage", None)
    salida["tokens"] = {"entrada": getattr(uso, "prompt_tokens", 0) or 0, "salida": getattr(uso, "completion_tokens", 0) or 0,
                        "usd": (getattr(uso, "model_extra", None) or {}).get("cost")}  # OpenRouter da el coste
    return salida


def para_el_log(lectura: dict | None) -> str:
    return json.dumps({k: v for k, v in (lectura or {}).items() if k != "descartes"}, ensure_ascii=False)
