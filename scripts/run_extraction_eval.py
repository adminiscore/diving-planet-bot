"""Fase 0 eval-set runner (docs/robustness/plan.md §4-5).

Runs the REALISTIC end-to-end pipeline — regex IntentDetector first, then the
LLM gap-filler on whatever it left missing — against
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

Usage: no arguments, or `--core` to run each case through the real turn
(`conversational_core._understand`, production config, guards included) and
score what the turn changed in the state. Cases may carry an optional `state`
(e.g. the pending slot a `history` implies). Prints a per-case and a per-field
summary to stdout.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

from src.agents.intent_detector import IntentDetector
from src.agents.llm_extractor import (
    EXTRACTABLE_FIELDS,
    compare_with_ground_truth,
    fill_gaps,
    verify_fields,
)
from src.agents.supervisor import _VETO_FIELD_SPECS, valid_veto_corrections
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

# Reusa DIRECTAMENTE `supervisor._VETO_FIELD_SPECS` (mismo trigger `should_
# verify` por campo, p. ej. la ambiguedad real que `activity` exige) en vez
# de reimplementar la condicion de disparo aqui -- hallazgo en vivo,
# 2026-09-10: una primera version de este script SI la reimplemento
# ("resuelto este turno" a secas, sin el `should_verify` de `activity`), y
# ese drift exacto (logica duplicada, no sincronizada) hizo que este script
# midiera un trigger que ya no era el que corria en produccion, ocultando
# que el fix real (revertir el trigger de activity a ambiguedad) SI
# funcionaba. No repetir ese error aqui otra vez.


def _regex_resolved(intent) -> dict:
    return {
        f: getattr(intent, f)
        for f in EXTRACTABLE_FIELDS
        if getattr(intent, f, None) not in (None, [])
    }


# ── Modo --core (2026-09-15) ─────────────────────────────────────────────────
#
# El modo por defecto mide regex + `fill_gaps` + veto, sin las guardas del nucleo,
# y los casos con historial salian mal por un artefacto: el LLM veia la pregunta
# del bot pero no el estado que esa conversacion tendria (slot pendiente, reparto ya
# sabido). Con --core cada caso pasa por `conversational_core._understand`, el turno
# real de produccion con su config (vetos y guardas incluidos), sobre un estado
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


async def _script_turn(case: dict, detector: IntentDetector) -> tuple[dict, dict]:
    state = ConversationState(conversation_id=f"eval-{case['id']}")
    regex_intent = detector.detect(case["message"], state)
    resolved = _regex_resolved(regex_intent)
    patch = await fill_gaps(
        case["message"], regex_intent, history=case.get("history"), lang=case.get("lang", "es"),
    )
    combined = {**resolved, **patch}

    # Veto de campos ya resueltos (docs/multi-agent-refactor-plan.md,
    # generalizacion "A bien montado" 2026-09-10, agrupado en UNA
    # peticion el mismo dia): se verifica cada campo resuelto por el
    # regex ESTE turno que ademas pase el `should_verify` de su spec
    # (para `activity`, ambiguedad real -- ver supervisor.py). Se aplica
    # siempre aqui (no gateado por settings) para medir el efecto REAL
    # del mecanismo sobre el eval-set completo, independientemente de
    # que flags esten on/off en el entorno donde se corre este script.
    veto_fields = [
        f for f, spec in _VETO_FIELD_SPECS.items()
        if f in resolved and f in regex_intent.detected_fields
        and (spec.should_verify is None
             or spec.should_verify(case["message"], regex_intent, state))
    ]
    if veto_fields:
        disagreements = await verify_fields(
            veto_fields, case["message"], {f: resolved[f] for f in veto_fields},
            history=case.get("history"), lang=case.get("lang", "es"),
        )
        # El mismo filtro que aplica el producto (supervisor.apply_veto_disagreements).
        combined.update(valid_veto_corrections(disagreements, resolved, case["message"]))
    return combined, {"regex_had": resolved, "llm_patch": patch}


async def run(core: bool = False) -> None:
    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        cases = json.load(f)["cases"]

    detector = IntentDetector()
    field_stats: dict[str, dict[str, int]] = {}
    total_agree = total_disagree = total_missed = 0
    watcher = _install_watcher()
    contaminados: list[str] = []
    print(f"Modo: {'nucleo (_understand, config de produccion)' if core else 'script (regex + fill_gaps + veto)'}")

    for case in cases:
        antes_degradado = watcher.degraded
        combined, context = await (_core_turn(case) if core else _script_turn(case, detector))

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
    out = EVAL_SET_PATH.parent / ("eval-last-run-core.json" if core else "eval-last-run.json")
    out.write_text(json.dumps({
        "modo": "core" if core else "script",
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


if __name__ == "__main__":
    asyncio.run(run(core="--core" in sys.argv[1:]))
