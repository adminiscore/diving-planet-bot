"""Banco del paso 4 de ex-9b: respuestas cortas a la pregunta pendiente (origen, hotel, cuántos) leídas por la IA de
verdad (Jev `pending_answer` y el extractor del turno, config de PRE) frente al regex de hoy; más el nombre, las notas
del RAG y un día cerrado. Frases propias (ninguna del golden ni del examen). 49 llamadas (Jev solo para el origen, que es
la única de estas preguntas que Jev contesta; el extractor una vez por frase). Las respuestas al origen que Jev deja en
duda las resuelve en el mismo turno la red anti-bucle con el resolutor LLM: eso lo mide `banco_paso4_resolutor.py`
(5 llamadas más), que añade sus resultados al JSON.

Con red. Desde la raíz del repo:
    ENV_FILE=<repo>/.env.dev python docs/robustness/regex/estudio-ex9/scripts/banco_paso4_respuestas_cortas.py
Sin red (`--sin-red`): vuelve a decidir con el código de ahora y las lecturas de la IA ya guardadas en el JSON.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

REPO = Path(__file__).resolve().parents[5]
os.chdir(REPO)
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")
SIN_RED = "--sin-red" in sys.argv
if SIN_RED:
    os.environ["ENV_FILE"] = str(REPO / ".env.ci")
from scripts.check_deploy import expected_from_compose  # noqa: E402
from src.config import settings  # noqa: E402

# La configuración de PRE (Jev encendido, sus preguntas, modelos), como en el compose.
for _k, _v in expected_from_compose().items():
    if hasattr(settings, _k):
        setattr(settings, _k, _v)
print("config de PRE; jev_router_enabled =", settings.jev_router_enabled, "· extractor =", settings.extractor_turno_model)

from src.agents.conversational_core import (  # noqa: E402
    SLOT_HOTEL,
    SLOT_LOCATION,
    SLOT_QTY,
    ask_slot,
)
from src.agents.extractor_turno import extraer_turno  # noqa: E402
from src.agents.jev_router import PENDING_ANSWER_MIN, detect_routing_signals_jev_full  # noqa: E402
from src.agents.nucleo import extractor as core_extractor  # noqa: E402
from src.agents.nucleo import routing as core_routing  # noqa: E402
from src.agents.nucleo.setup import _NAME_TRIGGER_SIN_SOY_RE  # noqa: E402
from src.flows.state import ConversationState  # noqa: E402

DATOS = Path(__file__).resolve().parents[1] / "banco-paso4-respuestas-cortas.json"
NO = "(no se resuelve)"
# (pregunta pendiente, mensaje, lo correcto). Origen: "cartagena"/"island"/NO. Hotel: lo que se guarda (en minúsculas;
# el id si es del catálogo de las islas) o "por confirmar". Cuántos: la cifra o NO.
CASOS = [
    (SLOT_LOCATION, "da igual", "cartagena"),
    (SLOT_LOCATION, "tú decides", "cartagena"),
    (SLOT_LOCATION, "me da lo mismo, lo que sea más fácil", "cartagena"),
    (SLOT_LOCATION, "lo que me recomiendes", "cartagena"),
    (SLOT_LOCATION, "cartagena", "cartagena"),
    (SLOT_LOCATION, "desde la ciudad amurallada", "cartagena"),
    (SLOT_LOCATION, "en el hilton de bocagrande", "cartagena"),
    (SLOT_LOCATION, "ya estamos en isla grande", "island"),
    (SLOT_LOCATION, "que solo nos acompañe en la lancha, no se mete al agua", NO),
    (SLOT_LOCATION, "no sé si hacer el minicurso o el snorkel", NO),
    (SLOT_LOCATION, "mejor pensándolo bien quiero el minicurso", NO),
    (SLOT_LOCATION, "somos 3", NO),
    (SLOT_LOCATION, "nos quedamos en barú", NO),
    (SLOT_HOTEL, "no tengo idea, el Hilton creo", "hilton"),
    (SLOT_HOTEL, "no sé todavía", "por confirmar"),
    (SLOT_HOTEL, "aún no hemos reservado hotel", "por confirmar"),
    (SLOT_HOTEL, "en el Ubuntu", "ubuntu"),
    (SLOT_HOTEL, "Casa Lola", "casa lola"),
    (SLOT_HOTEL, "nos vamos a quedar en el san pedro de majagua", "san_pedro_majagua"),
    (SLOT_HOTEL, "en un airbnb en isla grande, no me acuerdo el nombre", "por confirmar"),
    (SLOT_HOTEL, "cual me recomiendas", "por confirmar"),
    (SLOT_HOTEL, "ok perfecto", "por confirmar"),
    (SLOT_QTY, "solo yo", 1),
    (SLOT_QTY, "just me", 1),
    (SLOT_QTY, "mi pareja y yo", 2),
    (SLOT_QTY, "somos 4 adultos", 4),
    (SLOT_QTY, "voy con mis dos hijos", 3),
    (SLOT_QTY, "nosotros 3 y mi suegra que no bucea", 4),
    (SLOT_QTY, "hace 3 años que no buceo", NO),
    (SLOT_QTY, "mi hijo tiene 9 años", NO),
    (SLOT_QTY, "llegamos el 12", NO),
]
SABIDO = {SLOT_LOCATION: {"activity": "certified_diving", "is_certified": True},
          SLOT_HOTEL: {"activity": "certified_diving", "is_certified": True, "location": "island"},
          SLOT_QTY: {"activity": "certified_diving", "is_certified": True, "location": "cartagena"}}


def _estado(slot: str) -> tuple[ConversationState, list[dict]]:
    st = ConversationState(conversation_id="banco-paso4", language="es")
    st.detected_activity, st.is_certified = "certified_diving", True
    if slot == SLOT_HOTEL:
        st.location = st.detected_location = "island"
    if slot == SLOT_QTY:
        st.location = st.detected_location = "cartagena"
    pregunta = ask_slot(st, slot)
    st.core_pending_slot = slot
    return st, [{"role": "user", "content": "hola, quiero bucear"}, {"role": "assistant", "content": pregunta}]


def _valor(st: ConversationState, slot: str, resuelto: bool):
    if not resuelto:
        return NO
    return {SLOT_LOCATION: st.location, SLOT_HOTEL: (st.hotel or "").lower(), SLOT_QTY: st.detected_group_size}[slot]


def _bien(valor, esperado) -> bool:
    return valor == esperado


def _fin_hoy(slot: str, hoy, datos: dict | None, jev_extras: dict, resolutor: dict | None):
    """Lo que queda al final del turno de HOY cuando el regex no resuelve la respuesta corta: `_understand` aplica lo
    que lee el extractor (origen, total) y la red anti-bucle pregunta a Jev (si está seguro) o al resolutor LLM (origen).
    El hotel no tiene red: lo que guarda la respuesta corta se queda."""
    if hoy != NO:
        return hoy
    campo = {SLOT_LOCATION: "location", SLOT_QTY: "group_size"}.get(slot)
    if campo and (datos or {}).get(campo):
        return datos[campo]
    pa = jev_extras.get("pending_answer") or {}
    if slot == SLOT_LOCATION and pa and pa.get("confidence", 0.0) >= PENDING_ANSWER_MIN:
        return pa.get("value") or NO
    if resolutor is not None:
        return resolutor["resolutor"]
    return NO


def _jev_guardado(texto: str | None, slot: str) -> dict:
    if not texto:
        return {}
    valor, conf = texto.split("@")
    return {"pending_answer": {"slot": slot, "value": None if valor == "None" else valor, "confidence": float(conf)}}


async def _caso(slot: str, msg: str, esperado, guardado: dict | None = None, resolutor: dict | None = None) -> dict:
    if guardado is not None:  # --sin-red: las lecturas de la IA de la pasada con red
        jev_extras, datos = _jev_guardado(guardado["jev"], slot), guardado["extractor"]
    else:
        jev_extras: dict = {}
        if slot == SLOT_LOCATION:  # Jev solo contesta la pregunta pendiente del origen (las otras no son de sí/no ni lista)
            _, hist = _estado(slot)
            senales, extras = await detect_routing_signals_jev_full(msg, lang="es", pending_slot=slot, history=hist)
            jev_extras = {**(senales if isinstance(senales, dict) else {}), **(extras or {})}
        _, hist = _estado(slot)
        datos = await extraer_turno(msg, history=hist, sabido=SABIDO[slot], lang="es")
    # Hoy (antes del flag `respuesta_corta_por_ia`, ya quitado): el regex, sin la lectura de la IA.
    st_hoy, _ = _estado(slot)
    hoy = _valor(st_hoy, slot, core_routing._apply_short_answer(st_hoy, msg))
    # Con el flag (hoy, sin flag): la IA (la lectura del extractor ya hecha, sin otra llamada).
    core_extractor.lectura_del_extractor = AsyncMock(return_value=datos)
    st_ia, _ = _estado(slot)
    ia = await core_routing._lectura_de_la_ia(st_ia, msg, jev_extras, slot)
    con = _valor(st_ia, slot, core_routing._apply_short_answer(st_ia, msg, ia=ia))
    despues = con
    if con == NO and slot == SLOT_LOCATION and (datos or {}).get("location"):
        despues = datos["location"]  # lo aplica `_understand` en el mismo turno
    elif con == NO and resolutor is not None:
        despues = resolutor["resolutor"]  # la red anti-bucle del mismo turno (Jev dudó o no contestó)
    pa = jev_extras.get("pending_answer") or {}
    fin_hoy = _fin_hoy(slot, hoy, datos, jev_extras, resolutor)
    return {"slot": slot, "msg": msg, "esperado": esperado, "hoy": hoy, "hoy_fin_del_turno": fin_hoy, "con_flag": con,
            "fin_del_turno": despues,
            "jev": (f"{pa.get('value')}@{pa.get('confidence', 0):.2f}" if pa else None),
            "extractor": {k: v for k, v in (datos or {}).items() if k in ("location", "hotel", "group_size")}
            if datos is not None else None,
            "bien_hoy": _bien(hoy, esperado), "bien_hoy_fin": _bien(fin_hoy, esperado),
            "bien_con_flag": _bien(despues, esperado)}


async def _extra() -> dict:
    """Nombre (la regex frente al extractor), notas del RAG (¿el estado tiene lo que hace falta?) y un día cerrado."""
    salida = {}
    for msg in ("hola, me llamo Ana y queremos bucear", "me llamo mucho la atención el precio del minicurso"):
        datos = await extraer_turno(msg, history=[], sabido={}, lang="es")
        m = _NAME_TRIGGER_SIN_SOY_RE.search(msg)
        salida[msg] = {"regex": m.group(1) if m else None, "extractor": (datos or {}).get("nombre")}
    for msg in ("mi amigo se certificó hace 8 años y no ha vuelto a bucear, yo soy open water",
                "somos 2, yo soy buzo certificado y mi novia no lo es"):
        datos = await extraer_turno(msg, history=[], sabido={}, lang="es")
        salida[msg] = {k: v for k, v in (datos or {}).items()
                       if k in ("is_certified", "last_dive_over_2_years", "group_size", "group_allocation")}
    msg = "quiero bucear el 25 de diciembre, somos 2"
    _, extras = await detect_routing_signals_jev_full(msg, lang="es", pending_slot=None, history=[])
    salida[msg] = {"asks_question (Jev)": (extras or {}).get("asks_question")}
    return salida


async def main():
    previo = json.loads(DATOS.read_text(encoding="utf-8")) if SIN_RED else {}
    guardados = {c["msg"]: c for c in previo.get("casos", [])}
    resolutor = {r["msg"]: r for r in previo.get("resolutor", [])}
    filas = [await _caso(s, m, e, guardados.get(m) if SIN_RED else None, resolutor.get(m)) for s, m, e in CASOS]
    for f in filas:
        marca = "" if f["bien_con_flag"] else "   <-- MAL con el flag"
        print(f"{f['slot']:9} {f['msg'][:52]!r:56} quiero={f['esperado']!s:14} hoy={f['hoy']!s:.30} "
              f"(fin del turno {f['hoy_fin_del_turno']!s:.20}) "
              f"flag={f['fin_del_turno']!s:16} jev={f['jev']} ext={f['extractor']}{marca}")
    for slot in (SLOT_LOCATION, SLOT_HOTEL, SLOT_QTY):
        fs = [f for f in filas if f["slot"] == slot]
        print(f"{slot}: bien hoy {sum(f['bien_hoy'] for f in fs)}/{len(fs)} (al final del turno "
              f"{sum(f['bien_hoy_fin'] for f in fs)}) · con el flag "
              f"{sum(f['bien_con_flag'] for f in fs)}/{len(fs)}")
    print(f"TOTAL: bien hoy {sum(f['bien_hoy'] for f in filas)}/{len(filas)} (al final del turno "
          f"{sum(f['bien_hoy_fin'] for f in filas)}) · con el flag "
          f"{sum(f['bien_con_flag'] for f in filas)}/{len(filas)} (umbral de Jev {PENDING_ANSWER_MIN})")
    extra = previo.get("extra") if SIN_RED else await _extra()
    for k, v in extra.items():
        print(f"{k!r}: {v}")
    salida = {"casos": filas, "extra": extra}
    if previo.get("resolutor"):
        salida["resolutor"] = previo["resolutor"]
    DATOS.write_text(json.dumps(salida, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("->", DATOS.relative_to(REPO))


asyncio.run(main())
