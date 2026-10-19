"""Banco del paso 6 de ex-9b: los campos nuevos del extractor del turno, con la IA de verdad (config de PRE), frente al
regex de hoy. Frases propias (ninguna del golden ni del examen; las del reparto son las dos que describe la tarea).

Por bloque, cada caso con SOLO el flag de su campo encendido (la llamada que se promocionaría):
- duracion (`duracion_por_extractor`): días de buceo / de estancia -> single_day / multi_day (con el paquete de varios
  días del catálogo si no dice días), frente a `_detect_duration`;
- edades (`edades_por_extractor`): las edades validadas en su cita, frente a `_detect_ages`;
- plan (`plan_elegido_por_extractor`): con el bot proponiendo UN paquete, si el mensaje lo acepta, frente a
  `_CONFIRMS_DESCRIBED_PACKAGE_RE`;
- reparto (`reparto_al_sumarse_alguien`): con 2 buzos certificados sabidos (sin reparto guardado, lo normal), cuántos van
  y el reparto tras `_aplicar_extractor` + `_apply_detected_intent`, con el flag y sin él (dos llamadas por caso);
- notas (`notas_rag_desde_estado`): otra persona sin certificar / certificada e inactiva, frente a los regex de
  `rutas/contexto_rag` sobre el mensaje.

Con red. Desde la raíz del repo:
    ENV_FILE=<repo>/.env.dev python docs/robustness/regex/estudio-ex9/scripts/banco_paso6_extractor.py
Sin red (`--sin-red`): vuelve a decidir con el código de ahora y las lecturas de la IA ya guardadas en el JSON.
`--solo <bloque>`: vuelve a leer con la IA solo ese bloque (con su flag; la lectura sin flag del reparto se reutiliza) y
el resto sale del JSON (para medir un cambio del prompt de un campo sin gastar las demás llamadas).
"""
import asyncio
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
os.chdir(REPO)
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")
SIN_RED = "--sin-red" in sys.argv
if SIN_RED:
    os.environ["ENV_FILE"] = str(REPO / ".env.ci")
from scripts.check_deploy import expected_from_compose  # noqa: E402
from src.config import settings  # noqa: E402

for _k, _v in expected_from_compose().items():
    if hasattr(settings, _k):
        setattr(settings, _k, _v)
FLAGS6 = ("duracion_por_extractor", "edades_por_extractor", "plan_elegido_por_extractor", "reparto_al_sumarse_alguien",
          "notas_rag_desde_estado")
print("config de PRE · extractor =", settings.extractor_turno_model, "· flags del paso 6 en el compose:",
      {f: getattr(settings, f) for f in FLAGS6})

from src.agents import supervisor  # noqa: E402
from src.agents.extractor_turno import extraer_turno  # noqa: E402
from src.agents.intent_detector import DetectedIntent, IntentDetector  # noqa: E402
from src.agents.nucleo import extractor as core_extractor  # noqa: E402
from src.agents.nucleo.routing import _CONFIRMS_DESCRIBED_PACKAGE_RE  # noqa: E402
from src.agents.rutas.contexto_rag import (  # noqa: E402
    _UNCERTIFIED_COMPANION_NOTE_RE,
    _mentions_inactive_but_certified_companion,
)
from src.flows.state import ConversationState  # noqa: E402

DATOS = Path(__file__).resolve().parents[1] / "banco-paso6-extractor.json"
DET = IntentDetector()
NADA = None

PROPUESTA_ES = ("Para lo que buscas te propongo el *paquete de 5 inmersiones en 2 días*: sales desde Cartagena, duermes "
                "una noche en la isla y vuelves al día siguiente. ¿Te encaja?")
PROPUESTA_EN = ("For what you're looking for I'd suggest the *5-dive package over 2 days*: you leave from Cartagena, "
                "spend a night on the island and come back the next day. Does that work for you?")
PREGUNTA_EDADES = "¡Perfecto! ¿Qué edades tienen los niños? Así te digo qué puede hacer cada uno. 😊"

# (bloque, mensaje, lo correcto, extra). duracion: single_day / multi_day / None. edades: lista. plan: True (lo elige) o
# False. reparto: el total que queda. notas: (otro_sin_certificar, otro_certificado_inactivo).
CASOS = [
    ("duracion", "estaré del 5 al 9 en cartagena, pero solo quiero bucear un día", "single_day", {}),
    ("duracion", "vamos a estar una semana en las islas", "multi_day", {}),
    ("duracion", "queremos bucear dos días seguidos", "multi_day", {}),
    ("duracion", "solo tenemos el sábado libre para bucear", "single_day", {}),
    ("duracion", "llegamos el jueves y nos vamos el domingo", "multi_day", {}),
    ("duracion", "I'm in town for three days but only want to dive on one of them", "single_day", {}),
    ("duracion", "we'd like to dive the whole weekend", "multi_day", {}),
    ("duracion", "me interesa el paquete de 7 inmersiones", "multi_day", {"nota": "sin días dichos: el catálogo"}),
    ("duracion", "tengo 5 meses de embarazo, ¿es seguro hacer snorkel?", NADA, {}),
    ("duracion", "hace 2 semanas que escribí y nadie me contesta", NADA, {}),
    ("duracion", "a lo mejor vamos dentro de unos meses", NADA, {}),
    ("duracion", "me operaron de la rodilla hace 3 meses, ¿puedo bucear?", NADA, {}),
    ("duracion", "¿cuántos días dura el curso open water?", NADA, {}),
    ("duracion", "I've been waiting 3 days for an answer about my booking", NADA, {}),
    ("duracion", "no buceo desde hace 3 años", NADA, {}),
    ("duracion", "somos 4 y queremos hacer el minicurso", NADA, {}),
    ("edades", "voy con mis dos hijos, de 8 y 11 años", [8, 11], {}),
    ("edades", "mi hija tiene nueve", [9], {}),
    ("edades", "somos mi esposo (45), yo (41) y nuestro hijo de 13", [13, 41, 45], {}),
    ("edades", "my son is 12 and my daughter 15", [12, 15], {}),
    ("edades", "el pequeño tiene 6 y el grande 10", [6, 10], {}),
    ("edades", "¿mi sobrino de 7 puede hacer snorkel?", [7], {}),
    ("edades", "6 y 9", [6, 9], {"bot": PREGUNTA_EDADES}),
    ("edades", "el mayor 12 y la menor 8", [8, 12], {"bot": PREGUNTA_EDADES}),
    ("edades", "¿desde qué edad pueden bucear los niños?", [], {}),
    ("edades", "no buceo hace 4 años", [], {}),
    ("edades", "somos 3 adultos y 2 niños", [], {}),
    ("edades", "llevamos 10 años casados y queremos celebrarlo buceando", [], {}),
    ("edades", "soy residente en Colombia hace 3 años, ¿tengo el precio local?", [], {}),
    ("plan", "perfecto, ese me sirve", True, {"bot": PROPUESTA_ES}),
    ("plan", "vale, vamos con ese", True, {"bot": PROPUESTA_ES}),
    ("plan", "sí, quiero ese paquete", True, {"bot": PROPUESTA_ES}),
    ("plan", "me encanta, resérvamelo", True, {"bot": PROPUESTA_ES}),
    ("plan", "great, let's do that one", True, {"bot": PROPUESTA_EN, "lang": "en"}),
    ("plan", "¿y cuánto cuesta?", False, {"bot": PROPUESTA_ES}),
    ("plan", "¿qué incluye?", False, {"bot": PROPUESTA_ES}),
    ("plan", "mmm prefiero algo de un solo día", False, {"bot": PROPUESTA_ES}),
    ("plan", "no gracias, con 2 inmersiones me basta", False, {"bot": PROPUESTA_ES}),
    ("plan", "lo pienso y te digo", False, {"bot": PROPUESTA_ES}),
    ("plan", "¿y el de 7 inmersiones cuánto sale?", False, {"bot": PROPUESTA_ES}),
    ("reparto", "mi hermano también viene, él quiere hacer snorkel", 3, {}),
    ("reparto", "al final viene mi primo, que hace snorkel", 3, {}),
    ("reparto", "se apunta mi cuñada, ella prefiere el minicurso", 3, {}),
    ("reparto", "one more friend is joining us, she'll snorkel", 3, {"lang": "en"}),
    ("reparto", "también viene mi hermano a bucear, es certificado", 3, {}),
    ("reparto", "mi pareja prefiere hacer snorkel", 2, {}),
    ("reparto", "los dos tenemos el Advanced", 2, {}),
    ("reparto", "mi amigo, el que ya te dije que viene, quiere snorkel", 2, {}),
    ("notas", "yo soy Open Water pero mi novia nunca ha buceado", (True, False), {}),
    ("notas", "mi amigo no tiene certificación", (True, False), {}),
    ("notas", "my wife isn't certified, I am", (True, False), {"lang": "en"}),
    ("notas", "mi hermano se certificó hace años pero no ha vuelto a bucear", (False, True), {}),
    ("notas", "my dad has his Advanced but hasn't dived since 2015", (False, True), {"lang": "en"}),
    ("notas", "yo no estoy certificado", (False, False), {}),
    ("notas", "no buceo desde hace 4 años, pero soy certificado", (False, False), {}),
    ("notas", "mi amigo es divemaster", (False, False), {}),
    ("notas", "somos 2 buzos certificados", (False, False), {}),
    ("notas", "¿mi hijo necesita estar certificado para el minicurso?", (False, False), {}),
]
FLAG_DEL_BLOQUE = {"duracion": "duracion_por_extractor", "edades": "edades_por_extractor",
                   "plan": "plan_elegido_por_extractor", "reparto": "reparto_al_sumarse_alguien",
                   "notas": "notas_rag_desde_estado"}
PREVIO_REPARTO = [{"role": "user", "content": "somos 2 buzos certificados, salimos de cartagena"},
                  {"role": "assistant", "content": "¡Genial! Son 2 buzos certificados saliendo desde Cartagena. "
                                                   "¿Alguno lleva más de 2 años sin bucear?"}]


def _flags(bloque: str | None) -> None:
    for f in FLAGS6:
        setattr(settings, f, False)
    if bloque:
        setattr(settings, FLAG_DEL_BLOQUE[bloque], True)


def _estado_reparto() -> ConversationState:
    st = ConversationState(conversation_id="banco-paso6", language="es")
    st.detected_activity, st.is_certified, st.detected_is_certified = "certified_diving", True, True
    st.detected_group_size, st.location, st.detected_location = 2, "cartagena", "cartagena"
    st.quiere_bucear = True
    st.history = list(PREVIO_REPARTO)
    return st


def _historial(extra: dict) -> list[dict]:
    return [{"role": "assistant", "content": extra["bot"]}] if extra.get("bot") else []


def _regex(bloque: str, msg: str, extra: dict):
    if bloque == "duracion":
        intent = DetectedIntent()
        DET._detect_duration(msg.lower(), intent)
        return intent.duration
    if bloque == "edades":
        intent = DetectedIntent()
        DET._detect_ages(msg.lower(), intent)
        return sorted(intent.ages or [])
    if bloque == "plan":
        return bool(_CONFIRMS_DESCRIBED_PACKAGE_RE.search(msg))
    if bloque == "notas":
        return (bool(_UNCERTIFIED_COMPANION_NOTE_RE.search(msg)), _mentions_inactive_but_certified_companion(msg))
    return None


async def _leer(bloque: str, msg: str, extra: dict, *, flag: bool) -> dict | None:
    _flags(bloque if flag else None)
    if bloque == "reparto":
        st = _estado_reparto()
        sabido = core_extractor._sabido_para_extractor(st)
        return await extraer_turno(msg, history=st.history, sabido=sabido, lang=extra.get("lang", "es"))
    return await extraer_turno(msg, history=_historial(extra), sabido={}, lang=extra.get("lang", "es"))


async def _reparto_decide(msg: str, datos: dict | None, flag: bool) -> dict:
    """Lo que queda en el estado con esa lectura del extractor (`_aplicar_extractor` + `_apply_detected_intent`)."""
    _flags("reparto" if flag else None)
    st = _estado_reparto()
    fut = asyncio.get_running_loop().create_future()
    fut.set_result(datos)
    st._extraccion_adelantada = fut
    intent = DetectedIntent()
    await core_extractor._aplicar_extractor(intent, st, msg, {})
    supervisor._apply_detected_intent(intent, st, msg)
    return {"total": st.detected_group_size, "reparto": st.detected_group_allocation,
            "confirma": dict(st.pending_correction or {})}


def _decide(bloque: str, msg: str, datos: dict | None):
    datos = datos or {}
    if bloque == "duracion":
        st = ConversationState(conversation_id="banco-paso6")
        dur, _ = core_extractor.duracion_del_extractor(datos, st)
        if dur is None and core_extractor._paquete_de_varios_dias_nombrado(msg):
            dur = "multi_day"
        return dur
    if bloque == "edades":
        return sorted(datos.get("edades") or [])
    if bloque == "plan":
        return datos.get("acepta_propuesta") is True
    if bloque == "notas":
        return (datos.get("otro_sin_certificar") is True, datos.get("otro_certificado_inactivo") is True)
    return None


def norm(valor):
    return list(valor) if isinstance(valor, tuple) else valor


async def main() -> None:
    solo = sys.argv[sys.argv.index("--solo") + 1] if "--solo" in sys.argv else None
    guardado = json.loads(DATOS.read_text(encoding="utf-8")) if (SIN_RED or solo) else {}
    previo = {(c["bloque"], c["mensaje"]): c for c in guardado.get("casos", [])}
    filas, llamadas = [], 0
    for bloque, msg, correcto, extra in CASOS:
        fila = {"bloque": bloque, "mensaje": msg, "correcto": correcto, "regex_hoy": _regex(bloque, msg, extra)}
        if SIN_RED or (solo and solo != bloque):
            fila["ia"] = previo[(bloque, msg)]["ia"]
            fila["ia_sin_flag"] = previo[(bloque, msg)].get("ia_sin_flag")
        else:
            fila["ia"] = await _leer(bloque, msg, extra, flag=True)
            llamadas += 1
            if bloque == "reparto" and solo:
                fila["ia_sin_flag"] = previo[(bloque, msg)].get("ia_sin_flag")
                fila["ia_primera_version"] = previo[(bloque, msg)].get("ia_primera_version", previo[(bloque, msg)]["ia"])
            elif bloque == "reparto":
                fila["ia_sin_flag"] = await _leer(bloque, msg, extra, flag=False)
                llamadas += 1
        if bloque == "reparto":
            fila["con_flag"] = await _reparto_decide(msg, fila["ia"], True)
            fila["sin_flag"] = await _reparto_decide(msg, fila["ia_sin_flag"], False)
            # Vale el total correcto o preguntar UNA vez para confirmarlo (regla de negocio del juez).
            fila["ok_con_flag"] = correcto in (fila["con_flag"]["total"], fila["con_flag"]["confirma"].get("group_size"))
            fila["ok_sin_flag"] = correcto in (fila["sin_flag"]["total"], fila["sin_flag"]["confirma"].get("group_size"))
            fila["ok_regex"] = None
        else:
            fila["decide"] = _decide(bloque, msg, fila["ia"])
            fila["ok_con_flag"] = norm(fila["decide"]) == norm(correcto)
            fila["ok_regex"] = norm(fila["regex_hoy"]) == norm(correcto)
        filas.append(fila)
        marca = "ok" if fila["ok_con_flag"] else "FALLA"
        print(f"[{bloque}] {marca:5} {msg[:60]!r}: IA -> {fila.get('decide', fila.get('con_flag'))!r} · hoy "
              f"{fila['regex_hoy'] if bloque != 'reparto' else fila['sin_flag']!r} · correcto {correcto!r}")
    resumen = {}
    for bloque in FLAG_DEL_BLOQUE:
        fb = [f for f in filas if f["bloque"] == bloque]
        hoy = (sum(bool(f["ok_sin_flag"]) for f in fb) if bloque == "reparto" else sum(bool(f["ok_regex"]) for f in fb))
        resumen[bloque] = {"casos": len(fb), "hoy": hoy, "con_el_campo": sum(bool(f["ok_con_flag"]) for f in fb)}
    print("\nresumen (hoy = regex; reparto: el extractor sin el flag):", json.dumps(resumen, ensure_ascii=False))
    if not SIN_RED:
        print("llamadas:", llamadas)
    total = (guardado.get("llamadas") or 0) + (0 if SIN_RED else llamadas) if guardado else llamadas
    # Lo que añaden otros scripts o notas a mano (`jev_suma`, `versiones_reparto`…) se conserva.
    out = {**{k: v for k, v in guardado.items() if k not in ("_nota", "modelo", "llamadas", "resumen", "casos")},
           "_nota": __doc__.split("\n\n")[0], "modelo": settings.extractor_turno_model, "llamadas": total,
           "resumen": resumen, "casos": filas}
    DATOS.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=list), encoding="utf-8")


asyncio.run(main())
