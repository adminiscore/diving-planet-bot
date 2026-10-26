"""Fase 0 eval-set runner (docs/robustness/plan.md §4-5).

Runs the REALISTIC end-to-end pipeline (lat-11 T6d, 26-oct: the turn's `_understand`; the regex IntentDetector
and the LLM gap-filler are gone) against
docs/robustness/eval-set.json, and reports per-field agreement with the
hand-labeled `expected` values. This is the tool used to decide, per domain,
whether the Fase 1+ cutover criteria (plan.md §4) are met.

Cases may carry an optional `history` field (list of {"role", "content"}
turns) that is passed straight through to `fill_gaps`. This is what makes the
"extractor contesta de más" misfill family (fill_gaps re-deriving an answer
from a pending bot question in the history instead of abstaining — see
docs/multi-agent-refactor-plan.md §6.bis) measurable here: without history,
every case looks like a cold-start turn and that failure mode can't occur.

Needs a real OpenAI API key (uses settings.openai_api_key) — run against an
environment that has one, e.g.:

    ENV_FILE=.env.dev python -m scripts.run_extraction_eval
    ssh ... "docker exec -i dp-pre-bot python3 -m scripts.run_extraction_eval"

Banco ex-0 (fase EX, 12-oct): `--banco ex0 --modo regex|actual|llm-primero --grupo diseño|ciego|todos` (ver el bloque
"Banco ex-0" abajo y docs/robustness/regex/banco-ex0/README.md).

Usage: no arguments (`--core` is still accepted: it is the only mode since lat-11 T6d) runs each case through the
real turn (`conversational_core._understand`, production config, guards included) and
score what the turn changed in the state. Cases may carry an optional `state`
(e.g. the pending slot a `history` implies). Prints a per-case and a per-field
summary to stdout.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

from src.agents.llm_extractor import (
    compare_with_ground_truth,
)
from src.flows.state import ConversationState

EVAL_SET_PATH = Path(__file__).resolve().parent.parent / "docs" / "robustness" / "eval-set.json"


# ── Deteccion de tandas contaminadas ────────────────────────────────────────
#
# `fill_gaps`/`verify_fields` degradan en silencio ante cualquier fallo
# (devuelven {} y siguen) -- ese contrato es CORRECTO en produccion: mas vale
# responder con el regex que romper la conversacion. Pero en una medicion es
# veneno: un 429 produce exactamente el mismo resultado que "el LLM coincidio
# con el regex", asi que los fallos de red se cuelan en las estadisticas
# disfrazados de aciertos/desaciertos reales.
#
# INCIDENTE REAL (2026-09-11): una tanda con 3 errores 429 dio `activity`
# 92% frente al 95% de la tanda anterior, y los 3 casos "nuevos" que fallaban
# devolvian precisamente el valor del regex -- justo lo que produce un 429.
# Estuvo a punto de concluirse que un rediseño degradaba la precision cuando
# lo que fallaba era la cuota. De ahi esta guarda: el arnes no debe publicar
# numeros que no pueda garantizar.
class _DegradationWatcher(logging.Handler):
    def __init__(self):
        super().__init__()
        self.degraded = 0
        self.rate_limited = 0

    def emit(self, record):
        # Solo cuenta como degradacion el marcador EXPLICITO [DEGRADED] que
        # pone `llm_extractor` cuando la LLAMADA fallo (red, 429, timeout,
        # respuesta malformada) y por tanto NO hubo opinion del modelo.
        #
        # Deliberadamente NO cuenta el descarte por enum
        # ("valor fuera de enum descartado"): ahi la llamada funciono y el
        # modelo respondio -- mal, pero respondio. Eso es conducta real y
        # reproducible suya y debe PUNTUAR como fallo en la medicion, no
        # excluirse. Confundir ambas cosas (version del 2026-09-11, que
        # filtraba por nivel de log) hacia desaparecer del computo casos
        # legitimos: `conv913-first-level-activity` quedaba excluido por un
        # problema del modelo, no de la infraestructura.
        if record.levelno < logging.WARNING:
            return
        try:
            msg = record.getMessage()
        except Exception:
            return
        if "[LLM_EXTRACTOR][DEGRADED]" not in msg:
            return
        self.degraded += 1
        if "429" in msg or "rate_limit" in msg.lower():
            self.rate_limited += 1


def _install_watcher() -> _DegradationWatcher:
    w = _DegradationWatcher()
    lg = logging.getLogger("uvicorn.error")   # el logger que usa llm_extractor
    lg.addHandler(w)
    lg.setLevel(logging.WARNING)
    return w


# ── Modo --core (2026-09-15) ─────────────────────────────────────────────────
#
# El modo por defecto mide regex + `fill_gaps`, sin las guardas del nucleo,
# y los casos con historial salian mal por un artefacto: el LLM veia la pregunta
# del bot pero no el estado que esa conversacion tendria (slot pendiente, reparto ya
# sabido). Con --core cada caso pasa por `conversational_core._understand`, el turno
# real de produccion con su config (guardas incluidas), sobre un estado
# sembrado con `history` y el `state` opcional del caso. Se puntua lo que el TURNO
# cambio en el estado: un campo que ya estaba y no se toca cuenta como abstencion.

def _state_values(state: ConversationState) -> dict:
    """Valor de cada campo extraible en el estado, con la misma lectura que el
    nucleo (`_state_known_fields`): el valor confirmado antes que el detectado. Las
    personas sin actividad elegida salen del reparto a `pending_undecided_qty`
    (`_take_undecided_members`); se devuelven como `undecided`, igual que las etiqueta
    el eval-set."""
    from src.agents.conversational_core import _known_field_values  # lazy: solo en --core

    values = _known_field_values(state)
    allocation = dict(values["group_allocation"] or {})
    if state.pending_undecided_qty:
        allocation["undecided"] = state.pending_undecided_qty
    return {
        **values,
        "group_allocation": allocation or None,
        "duration": state.detected_duration,
        "cert_dives": state.detected_cert_dives,
        "cert_days": state.detected_cert_days,
    }


async def _core_turn(case: dict) -> tuple[dict, dict]:
    from src.agents import conversational_core  # lazy: solo en --core

    state = ConversationState(conversation_id=f"eval-core-{case['id']}")
    state.language = case.get("lang", "es")
    state.history = list(case.get("history") or [])
    for key, value in (case.get("state") or {}).items():
        setattr(state, key, value)
    before = _state_values(state)
    await conversational_core._understand(state, case["message"])
    after = _state_values(state)
    produced = {f: v for f, v in after.items() if v != before[f] and v not in (None, [], {})}
    return produced, {"estado_inicial": {f: v for f, v in before.items() if v not in (None, [], {})}}


async def run() -> None:
    """lat-11 T6d (26-oct): sin el modo «script» (solo el regex de IntentDetector, que se quitó): cada caso por el turno."""
    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        cases = json.load(f)["cases"]

    field_stats: dict[str, dict[str, int]] = {}
    total_agree = total_disagree = total_missed = 0
    watcher = _install_watcher()
    contaminados: list[str] = []
    print("Modo: nucleo (_understand, config de produccion)")

    for case in cases:
        antes_degradado = watcher.degraded
        combined, context = await _core_turn(case)

        # Si la cuota se agoto, PARAR: seguir solo quema peticiones para
        # producir numeros invalidos (y ademas impide re-correr la medicion
        # bien despues). Mejor abortar fuerte que publicar basura.
        if watcher.rate_limited:
            print(
                f"\n!! ABORTADO en el caso {case['id']!r}: la API devolvio rate-limit "
                f"({watcher.rate_limited} veces). Las llamadas degradan en silencio al "
                f"valor del regex, asi que cualquier estadistica de aqui en adelante "
                f"seria indistinguible de 'el LLM coincidio'. Repetir la tanda con cuota.",
                file=sys.stderr,
            )
            sys.exit(2)

        # Degradacion no-429 (timeout, respuesta malformada...): el caso se
        # marca y se EXCLUYE de las estadisticas en vez de contarlo como si
        # el LLM hubiera opinado.
        if watcher.degraded > antes_degradado:
            contaminados.append(case["id"])
            print(f"[SKIP] {case['id']}: llamada LLM degradada, excluido del computo")
            continue

        result = compare_with_ground_truth(combined, case["expected"])
        total_agree += len(result["agree"])
        total_disagree += len(result["disagree"])
        total_missed += len(result["missed"])

        for f in result["agree"]:
            field_stats.setdefault(f, {"agree": 0, "disagree": 0, "missed": 0})["agree"] += 1
        for f in result["disagree"]:
            field_stats.setdefault(f, {"agree": 0, "disagree": 0, "missed": 0})["disagree"] += 1
        for f in result["missed"]:
            field_stats.setdefault(f, {"agree": 0, "disagree": 0, "missed": 0})["missed"] += 1

        status = "OK" if not result["disagree"] and not result["missed"] else "GAP"
        print(f"[{status}] {case['id']}: {case['message'][:60]!r}")
        if result["disagree"]:
            print(f"       disagree={result['disagree']}")
        if result["missed"]:
            print(f"       missed={result['missed']} ({context})")

    print("\n--- Per-field summary ---")
    for f, stats in sorted(field_stats.items()):
        total = stats["agree"] + stats["disagree"] + stats["missed"]
        rate = stats["agree"] / total if total else 0.0
        print(f"{f:28s} agree={stats['agree']:3d} disagree={stats['disagree']:3d} missed={stats['missed']:3d}  ({rate:.0%})")

    total = total_agree + total_disagree + total_missed
    overall = total_agree / total if total else 0.0
    print(f"\nOverall: {total_agree}/{total} agree ({overall:.1%}), {total_disagree} disagree, {total_missed} missed")
    evaluados = len(cases) - len(contaminados)
    print(f"Cases: {evaluados}/{len(cases)} evaluados")

    # Resumen tambien en JSON, a fichero. El resumen de texto viaja por
    # stdout mezclado con el ruido de otras librerias (LangSmith escribe a
    # media linea), y filtrar ese ruido puede llevarse por delante lineas
    # buenas: el 2026-09-12 un `grep -v` borro justo la fila de `activity`,
    # el campo que se estaba midiendo. Un fichero aparte no se puede
    # corromper asi.
    out = EVAL_SET_PATH.parent / "eval-last-run-core.json"
    out.write_text(json.dumps({
        "modo": "core",
        "per_field": field_stats,
        "overall": {"agree": total_agree, "disagree": total_disagree, "missed": total_missed},
        "cases_evaluados": evaluados,
        "cases_totales": len(cases),
        "excluidos": contaminados,
        "comparable": not contaminados,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"(resumen JSON en {out})")

    # Veredicto explicito de comparabilidad: quien lea esto no deberia tener
    # que deducir si los numeros valen para comparar contra otra tanda.
    if contaminados:
        print(
            f"\n*** TANDA NO COMPARABLE: {len(contaminados)} caso(s) excluidos por "
            f"llamadas LLM degradadas -> {contaminados}\n"
            f"    Las cifras de arriba cubren solo los {evaluados} casos sanos y NO "
            f"deben compararse contra tandas completas."
        )
    else:
        print("\nTanda limpia: 0 llamadas LLM degradadas, cifras comparables.")


# ── Banco ex-0 (fase EX, 12-oct) ─────────────────────────────────────────────
#
# 342 turnos de cliente de la ronda visible con Luna (`2026-10-08-luna-visible`, sin el examen oculto), con la
# conversación previa y la pregunta que el bot acababa de hacer (`slot`), etiquetados a mano: SOLO lo que el cliente
# AFIRMA en ese mensaje (docs/robustness/regex/banco-ex0/). Cada caso es COMPLETO: un campo de `CAMPOS_EX0` que la
# etiqueta no trae es "no lo dice", así que si el extractor pone un valor es un INVENTO. Grupos diseño/ciego por
# diálogo (sha1 % 2, fijado antes de medir): ajustar SOLO mirando el de diseño.
#
#   --modo regex   lo determinista: lector de respuestas cortas a la pregunta pendiente (sin LLM ni Jev; lat-11 T6d:
#                  sin el detector IntentDetector, que se quitó)
#   --modo actual  el turno de producción hasta entender el mensaje: señales del router (Jev, en cascada), lector de
#                  respuestas cortas y `_understand` (regex + sus redes LLM), con la config de producción
BANCO_EX0 = Path(__file__).resolve().parent.parent / "docs" / "robustness" / "regex" / "banco-ex0"
CAMPOS_EX0 = ("activity", "is_certified", "group_size", "group_allocation", "location", "is_colombian",
              "last_dive_over_2_years")


def casos_ex0(grupo: str = "todos") -> list[dict]:
    candidatos = json.loads((BANCO_EX0 / "candidatos.json").read_text(encoding="utf-8"))
    etiquetas = json.loads((BANCO_EX0 / "etiquetas.json").read_text(encoding="utf-8"))
    casos, sabido_por_dialogo = [], {}
    for c in sorted(candidatos, key=lambda x: (x["dialogo"], x["turno"])):
        e = etiquetas.get(c["id"])
        sabido = dict(sabido_por_dialogo.get(c["dialogo"], {}))
        if e:
            sabido_por_dialogo[c["dialogo"]] = {**sabido, **e["expected"]}
        if not e or e["slot"] == "DUDOSO" or (grupo != "todos" and c["grupo"] != grupo):
            continue
        lang = "en" if any(w in f" {c['message'].lower()} " for w in (" the ", " i ", " we ", " you ", " is ")) else "es"
        # `sabido`: lo que el cliente ya habia dicho en los turnos anteriores del dialogo (sus etiquetas): el estado
        # con el que llega el turno. Sin esto, "no, buceé hace poco" (a la pregunta de seguridad) "inventaba" la
        # actividad que en la conversacion real ya se sabia.
        casos.append({**c, "slot": e["slot"], "expected": e["expected"], "lang": lang, "sabido": sabido})
    return casos


def _estado_ex0(caso: dict) -> ConversationState:
    state = ConversationState(conversation_id=f"ex0-{caso['id']}")
    state.language = caso["lang"]
    state.history = list(caso.get("history") or [])
    if caso.get("slot"):
        state.core_pending_slot = caso["slot"]
    sabido = caso.get("sabido") or {}
    for campo, attr in (("activity", "detected_activity"), ("is_certified", "is_certified"),
                        ("group_size", "detected_group_size"), ("group_allocation", "detected_group_allocation"),
                        ("location", "location"), ("is_colombian", "is_colombian"),
                        ("last_dive_over_2_years", "last_dive_over_2_years")):
        if campo in sabido:
            setattr(state, attr, sabido[campo])
    return state


def _cambios(antes: dict, despues: dict) -> dict:
    return {f: despues[f] for f in CAMPOS_EX0 if despues.get(f) != antes.get(f) and despues.get(f) not in (None, [], {})}


TIEMPOS_EX0: list[float] = []


async def _turno_ex0(caso: dict, modo: str, modelo: str | None = None) -> dict:
    from src.agents import conversational_core  # lazy

    if modo == "llm-primero":
        from src.agents.extractor_turno import extraer_turno  # lazy

        sabido = caso.get("sabido") or {}
        datos = await extraer_turno(caso["message"], history=caso.get("history"), sabido=sabido, lang=caso["lang"],
                                    modelo=modelo)
        TIEMPOS_EX0.append(extraer_turno.ultimo_segundos)
        return {f: v for f, v in (datos or {}).items() if v != sabido.get(f)}
    state = _estado_ex0(caso)
    antes = _state_values(state)
    msg = caso["message"]
    resuelto = False
    if modo == "actual":
        from src.agents.escalation import detect_routing_signals  # lazy

        senales = {} if msg.strip().isdigit() else await detect_routing_signals(
            msg, lang=state.language, pending_slot=state.core_pending_slot)
        conversational_core.sembrar_senales_del_turno(state, senales)
    if state.core_pending_slot and "?" not in msg:
        resuelto = conversational_core._apply_short_answer(state, msg)
    if modo == "actual":
        if not (resuelto and len(msg.strip()) <= 12):
            await conversational_core._understand(state, msg, answered_pending=resuelto)
        return _cambios(antes, _state_values(state))
    return _cambios(antes, _state_values(state))


def _tolerado(campo: str, valor, esperado: dict, sabido: dict | None = None) -> bool:
    """Lo que no cuenta como invento aunque la etiqueta no lo traiga, por ser coherente con lo que el cliente SÍ dijo:
    la actividad 'principal' de un grupo mixto (una del reparto), el reparto de una sola actividad que repite la
    actividad y el número, la certificación de un grupo mixto, y "no certificado" deducido del minicurso o del curso
    Open Water."""
    contexto = {**(sabido or {}), **esperado}
    reparto = contexto.get("group_allocation") or {}
    if campo == "is_certified" and valor is False and contexto.get("activity") in ("minicourse", "padi_open_water"):
        return True
    if campo == "activity" and valor in reparto:
        return True
    if campo == "is_certified" and reparto:
        return True
    if campo == "group_allocation" and isinstance(valor, dict) and len(valor) == 1:
        (act, n), = valor.items()
        return act == contexto.get("activity") or n == contexto.get("group_size")
    return False


def puntuar_ex0(producido: dict, esperado: dict, sabido: dict | None = None) -> dict:
    r = {"acierto": [], "equivocado": [], "perdido": [], "inventado": []}
    for f in CAMPOS_EX0:
        got = producido.get(f)
        if f in esperado:
            # Si el cliente repite algo que ya se sabia, no tocarlo es acertar (los modos solo devuelven CAMBIOS).
            ya_sabido = got is None and esperado[f] == (sabido or {}).get(f)
            r["acierto" if got == esperado[f] or ya_sabido else "perdido" if got is None else "equivocado"].append(f)
        elif got is not None and got != (sabido or {}).get(f) and not _tolerado(f, got, esperado, sabido):
            r["inventado"].append(f)
    return r


async def run_ex0(modo: str, grupo: str, modelo: str | None = None) -> None:
    casos = casos_ex0(grupo)
    watcher = _install_watcher()
    por_campo: dict[str, dict[str, int]] = {f: {"acierto": 0, "equivocado": 0, "perdido": 0, "inventado": 0}
                                            for f in CAMPOS_EX0}
    filas, contaminados = [], []
    print(f"Banco ex0 · modo {modo}{f' ({modelo})' if modelo else ''} · grupo {grupo} · {len(casos)} casos")
    for caso in casos:
        antes_degradado = watcher.degraded
        producido = await _turno_ex0(caso, modo, modelo)
        if watcher.rate_limited:
            print(f"\n!! ABORTADO en {caso['id']!r}: rate-limit de la API (ver el modo de siempre).", file=sys.stderr)
            sys.exit(2)
        if watcher.degraded > antes_degradado:
            contaminados.append(caso["id"])
            continue
        r = puntuar_ex0(producido, caso["expected"], caso.get("sabido"))
        for tipo, campos in r.items():
            for f in campos:
                por_campo[f][tipo] += 1
        filas.append({"id": caso["id"], "grupo": caso["grupo"], "message": caso["message"], "slot": caso["slot"],
                      "esperado": caso["expected"], "producido": producido, **r})
        if r["equivocado"] or r["perdido"] or r["inventado"]:
            print(f"[MAL] {caso['id']}: {caso['message'][:70]!r} esperado={caso['expected']} producido={producido}")
    tot = {t: sum(v[t] for v in por_campo.values()) for t in ("acierto", "equivocado", "perdido", "inventado")}
    esperados = tot["acierto"] + tot["equivocado"] + tot["perdido"]
    con_invento = sum(1 for x in filas if x["inventado"])
    print("\n--- Por campo (acierto / equivocado / perdido / inventado) ---")
    for f, v in por_campo.items():
        n = v["acierto"] + v["equivocado"] + v["perdido"]
        print(f"{f:24s} {v['acierto']:3d}/{n:<3d} ({(v['acierto'] / n if n else 0):4.0%})  equiv {v['equivocado']:2d}  "
              f"perdido {v['perdido']:2d}  inventado {v['inventado']:2d}")
    print(f"\nDatos acertados: {tot['acierto']}/{esperados} ({tot['acierto'] / esperados:.1%}) · equivocados "
          f"{tot['equivocado']} · perdidos {tot['perdido']} · inventados {tot['inventado']} "
          f"(en {con_invento} de {len(filas)} casos, {con_invento / len(filas):.1%})")
    if TIEMPOS_EX0:
        ts = sorted(TIEMPOS_EX0)
        print(f"Tiempo por llamada: p50 {ts[len(ts) // 2]:.2f}s · p90 {ts[int(0.9 * len(ts))]:.2f}s · máx {ts[-1]:.2f}s")
    from src.config import settings

    flags = [f for f in ("extraccion_llm_ubicacion", "extraccion_llm_actividad", "extraccion_llm_certificacion",
                       "extraccion_llm_grupo")
             if getattr(settings, f, False)]
    sufijo = (f"-{modelo.replace('/', '_')}" if modelo else "") + "".join(f"-{f}" for f in flags)
    salida = BANCO_EX0 / f"resultado-{modo}{sufijo}-{grupo}.json"
    salida.write_text(json.dumps({"modo": modo, "grupo": grupo, "casos": len(filas), "por_campo": por_campo,
                                  "total": tot, "casos_con_invento": con_invento, "excluidos": contaminados,
                                  "comparable": not contaminados, "filas": filas}, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print(f"(detalle en {salida}){'' if not contaminados else f'  *** NO COMPARABLE: {len(contaminados)} degradados'}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--banco" in args and args[args.index("--banco") + 1] == "ex0":
        modo = args[args.index("--modo") + 1] if "--modo" in args else "actual"
        grupo = args[args.index("--grupo") + 1] if "--grupo" in args else "todos"
        modelo = args[args.index("--modelo") + 1] if "--modelo" in args else None
        from src.config import settings

        for i, a in enumerate(args):  # --flag X: enciende un interruptor de settings solo en este proceso (repetible)
            if a == "--flag":
                setattr(settings, args[i + 1], True)
        asyncio.run(run_ex0(modo, grupo, modelo))
    else:
        asyncio.run(run())
