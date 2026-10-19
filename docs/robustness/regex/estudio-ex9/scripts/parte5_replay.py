"""Parte 5: los 95 diálogos VISIBLES del golden por el turno de verdad (`supervisor.route_message`, grafo incluido), en
local y SIN RED: OpenAI falla al momento, Jev sin clave (cae al router LLM, que también falla), RAG/acuse/notas con
respuesta fija (como scripts/replay_golden_local.py).

Modos (--modo):
  oraculo      el extractor del turno devuelve las ETIQUETAS del banco ex0 de ese diálogo y turno (lo que el cliente
               afirma) e idioma del golden: aproxima "el extractor funciona" sin llamar a ningún modelo.
  caido        el extractor falla (None): manda el regex con su puerta (degradación).
Variantes (--variante), siempre sobre el detector (`IntentDetector.detect`, para TODOS sus llamadores):
  base         el código de hoy.
  sin_dominios el detector no devuelve los campos que decide el extractor (actividad, certificación, grupo, origen,
               nacionalidad, última inmersión); sí hotel/isla (lista cerrada).
  sin_todo     además sin duración, nº de inmersiones/días, edades, idioma y "voy solo" (lo que hoy solo lee el regex).
Con --cobertura mide las líneas ejecutadas (coverage.py) de los módulos del estudio.
Salida: <ESTUDIO_OUT>/replay-<modo>-<variante>.json
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comun  # noqa: E402

comun.bloquear_red()

ap = argparse.ArgumentParser()
ap.add_argument("--modo", choices=["oraculo", "caido"], default="oraculo")
ap.add_argument("--variante", choices=["base", "sin_dominios", "sin_todo"], default="base")
ap.add_argument("--cobertura", action="store_true")
ap.add_argument("--trazar", action="store_true")
a = ap.parse_args()

cov = None
if a.cobertura:
    import coverage

    cov = coverage.Coverage(data_file=None, include=[str(comun.REPO / "src" / "*")], branch=False)
    cov.start()

import httpx  # noqa: E402
import openai  # noqa: E402
from openai.resources.chat import completions as _cc  # noqa: E402
from openai.resources import embeddings as _emb  # noqa: E402


async def _falla(*_a, **_k):
    raise openai.APIConnectionError(request=httpx.Request("POST", "http://sin-red.invalid"))


_cc.AsyncCompletions.create = _falla
_emb.AsyncEmbeddings.create = _falla
try:
    from openai.resources import responses as _resp  # noqa: E402

    _resp.AsyncResponses.create = _falla
except Exception:  # noqa: BLE001
    pass

from src.agents import conversational_core as core  # noqa: E402
from src.agents import escalation, supervisor  # noqa: E402
from src.agents import extractor_turno  # noqa: E402
from src.agents import intent_detector as idet  # noqa: E402
from src.agents.nucleo import slotfill_close as core_close  # noqa: E402
from src.config import settings  # noqa: E402
from src.flows.state import ConversationState  # noqa: E402

settings.aviso_si_openai_falla = False  # sin esto, sin OpenAI cada turno sería "problema técnico"

if a.trazar:
    import importlib

    import trazador

    for nombre in ("src.agents.intent_detector", "src.agents.nucleo.extraction", "src.agents.nucleo.routing",
                   "src.agents.nucleo.setup", "src.agents.nucleo.extractor", "src.agents.nucleo.slotfill_close",
                   "src.agents.nucleo.availability", "src.agents.conversational_core", "src.agents.supervisor",
                   "src.agents.rutas.booking", "src.agents.rutas.changes", "src.agents.rutas.contexto_rag",
                   "src.agents.rutas.deflection", "src.agents.rutas.info", "src.agents.rutas.router",
                   "src.agents.rutas.safety", "src.orchestration.graph", "src.agents.escalation",
                   "src.agents.llm_extractor", "src.flows.catalog"):
        trazador.instala(importlib.import_module(nombre))

ETIQ = json.loads((comun.REPO / "docs/robustness/regex/banco-ex0/etiquetas.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((comun.REPO / "docs/robustness/golden-set/golden-dialogues.json").read_text(encoding="utf-8"))
IDIOMA = {d["id"]: (d.get("cobertura") or {}).get("idioma") for d in GOLDEN["dialogues"] if d.get("suite") != "oculto"}
ACTUAL = {"dialogo": None, "turno": None}
LLAMADAS = {"extractor": 0}


async def _extractor_oraculo(mensaje, *, history=None, sabido=None, lang="es", modelo=None, client=None):
    LLAMADAS["extractor"] += 1
    if a.modo == "caido":
        return None
    e = ETIQ.get(f"ex0-{ACTUAL['dialogo']}-t{ACTUAL['turno']}") or {}
    datos = {} if e.get("slot") == "DUDOSO" else dict(e.get("expected") or {})
    datos = {k: v for k, v in datos.items() if v != (sabido or {}).get(k)}
    idioma = IDIOMA.get(ACTUAL["dialogo"])
    if idioma in ("es", "en"):
        datos["idioma"] = idioma
    return datos


extractor_turno.extraer_turno = _extractor_oraculo

CAMPOS_DOMINIO = ("activity", "service_id", "is_certified", "group_size", "group_allocation", "location",
                  "is_colombian", "last_dive_over_2_years")
CAMPOS_RESTO = ("duration", "cert_dives", "cert_days", "language")
_detect_original = idet.IntentDetector.detect


def _detect_variante(self, message, state):
    intent = _detect_original(self, message, state)
    quitar = CAMPOS_DOMINIO if a.variante == "sin_dominios" else CAMPOS_DOMINIO + CAMPOS_RESTO if a.variante == "sin_todo" else ()
    for c in quitar:
        setattr(intent, c, None)
    if a.variante == "sin_todo":
        intent.ages = []
        intent.solo_confirmed = False
    intent.detected_fields = [f for f in intent.detected_fields if f not in quitar
                              and not (a.variante == "sin_todo" and f == "ages")]
    return intent


idet.IntentDetector.detect = _detect_variante


async def _rag(message, **_k):
    return "«RAG»"


async def _noop(*_a, **_k):
    return True


supervisor.rag_answer = _rag
core_close.compose_acknowledgement = lambda *a_, **k: asyncio.sleep(0, result="")
core.extract_notes = lambda *a_, **k: asyncio.sleep(0, result=[])
escalation.escalate_to_human = _noop
supervisor.escalate_to_human = _noop

CAMPOS_ESTADO = ("language", "detected_activity", "suggested_activity", "is_certified", "location", "detected_location",
                 "island", "hotel", "detected_group_size", "detected_group_allocation", "is_colombian",
                 "last_dive_over_2_years", "refresher_interested", "detected_duration", "detected_cert_dives",
                 "detected_cert_days", "detected_ages", "solo_traveler_confirmed", "needs_cert_or_course",
                 "quiere_bucear", "core_pending_slot", "pending_escalation_reason")


async def main():
    from scripts.replay_golden_local import dialogues

    filas = []
    for did, turns in dialogues():
        st = ConversationState(conversation_id=f"estudio-{did}")
        for i, msg in enumerate(turns, 1):
            ACTUAL.update(dialogo=did, turno=i)
            if a.trazar:
                trazador.CTX["i"] = (did, i)
                trazador.CTX["ctx"] = "replay"
            try:
                reply = await supervisor.route_message(st, msg)
            except Exception as exc:  # noqa: BLE001
                reply = f"ERROR {type(exc).__name__}: {exc}"
            snap = {f: getattr(st, f, None) for f in CAMPOS_ESTADO}
            snap["carrito"] = sorted((x.get("type"), x.get("qty")) for x in (st.mixed_cart or []))
            filas.append({"id": did, "turno": i, "msg": msg, "reply": reply if isinstance(reply, str) else str(reply),
                          "estado": json.loads(json.dumps(snap, default=str))})
    return filas


filas = asyncio.run(main())
salida = {"modo": a.modo, "variante": a.variante, "turnos": len(filas),
          "errores": sum(1 for f in filas if f["reply"].startswith("ERROR")),
          "llamadas_extractor": LLAMADAS["extractor"], "filas": filas}
if cov is not None:
    cov.stop()
    lineas = {}
    for f in cov.get_data().measured_files():
        rel = Path(f).resolve().relative_to(comun.REPO.resolve()).as_posix() if str(comun.REPO) in f else f
        lineas[rel] = sorted(cov.get_data().lines(f) or [])
    salida["cobertura"] = lineas
if a.trazar:
    rec = []
    for (mod, nombre, func), r in trazador.REC.items():
        rec.append({"modulo": mod, "patron": nombre, "funcion": func, "evals": r["evals"], "hits": r["hits"],
                    "turnos_eval": len(r["msgs_eval"]), "turnos_casa": len(r["msgs"]),
                    "ejemplos": sorted({f"{d}#{t}" for d, t in r["msgs"]})[:5]})
    salida["patrones"] = sorted(rec, key=lambda x: (-x["turnos_casa"], x["modulo"], x["patron"]))
(comun.OUT / f"replay-{a.modo}-{a.variante}.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                                                             encoding="utf-8")
print(a.modo, a.variante, "turnos", len(filas), "errores", salida["errores"], "llamadas al extractor",
      LLAMADAS["extractor"])
