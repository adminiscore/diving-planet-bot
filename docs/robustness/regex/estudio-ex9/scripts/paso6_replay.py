"""ex-9b paso 6: el replay offline del paso 4 (`paso4_replay.py`: 95 diálogos VISIBLES del golden por
`supervisor.route_message`, SIN RED, con el contexto del RAG) con el oráculo ampliado a los campos nuevos del extractor:
`datos/etiquetas-paso6.json` (días de buceo y de estancia, edades, acepta la propuesta, otra persona sin certificar o
certificada e inactiva). El oráculo solo devuelve un campo nuevo si la llamada de verdad lo llevaría
(`extractor_turno.campos_paso6`: su flag encendido y, `acepta_propuesta`, que el bot acabe de proponer un plan).

- `--flags a,b`: enciende esos interruptores antes de la pasada (los del paso 6 están apagados por defecto).

Modos (--modo): `oraculo` (el extractor devuelve las etiquetas del banco ex0 y las del paso 6 de ese turno) y `caido`
(el extractor falla). Jev no tiene clave en los dos: calla siempre. El RAG adelantado (rag-5) no se lanza.

Uso (cwd = raíz del repo): python docs/robustness/regex/estudio-ex9/scripts/paso6_replay.py --modo oraculo
    [--flags duracion_por_extractor] --salida base
Salida: <ESTUDIO_OUT>/paso4-<modo>-<salida>.json (mismo formato que el paso 4). Se compara con `paso4_diff.py`.
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comun  # noqa: E402

comun.bloquear_red()

ap = argparse.ArgumentParser()
ap.add_argument("--modo", choices=["oraculo", "caido"], default="oraculo")
ap.add_argument("--flags", default="", help="interruptores a encender, separados por comas")
ap.add_argument("--salida", required=True)
a = ap.parse_args()

import httpx  # noqa: E402
import openai  # noqa: E402
from openai.resources import embeddings as _emb  # noqa: E402
from openai.resources.chat import completions as _cc  # noqa: E402


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
from src.agents import escalation, extractor_turno, supervisor  # noqa: E402
from src.agents.nucleo import slotfill_close as core_close  # noqa: E402
from src.config import settings  # noqa: E402
from src.flows.state import ConversationState  # noqa: E402

settings.aviso_si_openai_falla = False  # sin esto, sin OpenAI cada turno sería "problema técnico"
for flag in [f.strip() for f in a.flags.split(",") if f.strip()]:
    assert hasattr(settings, flag), f"no existe el interruptor {flag!r}"
    setattr(settings, flag, True)

ETIQ = json.loads((comun.REPO / "docs/robustness/regex/banco-ex0/etiquetas.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((comun.REPO / "docs/robustness/golden-set/golden-dialogues.json").read_text(encoding="utf-8"))
IDIOMA = {d["id"]: (d.get("cobertura") or {}).get("idioma") for d in GOLDEN["dialogues"] if d.get("suite") != "oculto"}
ACTUAL = {"dialogo": None, "turno": None}
LLAMADAS = {"extractor": 0}
RAG: list[str] = []
_HORA = re.compile(r"^(Fecha y hora actual|Current date and time): [^(]*\([^)]*\)\.\s*")


ETIQ6 = json.loads((comun.REPO / "docs/robustness/regex/estudio-ex9/datos/etiquetas-paso6.json").read_text(
    encoding="utf-8"))["etiquetas"]
LLAMADAS["con_acepta_propuesta"] = 0


async def _extractor_oraculo(mensaje, *, history=None, sabido=None, lang="es", modelo=None, client=None):
    LLAMADAS["extractor"] += 1
    if a.modo == "caido":
        return None
    clave = f"ex0-{ACTUAL['dialogo']}-t{ACTUAL['turno']}"
    e = ETIQ.get(clave) or {}
    datos = {} if e.get("slot") == "DUDOSO" else dict(e.get("expected") or {})
    datos = {k: v for k, v in datos.items() if v != (sabido or {}).get(k)}
    # Los campos nuevos solo si la llamada de verdad los llevaría (flag y, para acepta_propuesta, la propuesta del bot).
    campos6 = extractor_turno.campos_paso6(history)
    LLAMADAS["con_acepta_propuesta"] += "acepta_propuesta" in campos6
    datos.update({k: v for k, v in (ETIQ6.get(clave) or {}).items() if k in campos6})
    idioma = IDIOMA.get(ACTUAL["dialogo"])
    if idioma in ("es", "en"):
        datos["idioma"] = idioma
    return datos


extractor_turno.extraer_turno = _extractor_oraculo


async def _rag(message, **k):
    RAG.append(_HORA.sub("", k.get("extra_context") or ""))
    return "«RAG»"


async def _noop(*_a, **_k):
    return True


supervisor.rag_answer = _rag
core.lanzar_rag_adelantado = lambda *a_, **k: None
core_close.compose_acknowledgement = lambda *a_, **k: asyncio.sleep(0, result="")
core.extract_notes = lambda *a_, **k: asyncio.sleep(0, result=[])
escalation.escalate_to_human = _noop
supervisor.escalate_to_human = _noop

CAMPOS_ESTADO = ("language", "client_name", "detected_activity", "suggested_activity", "is_certified", "location",
                 "detected_location", "island", "hotel", "detected_group_size", "detected_group_allocation",
                 "is_colombian", "last_dive_over_2_years", "refresher_interested", "detected_duration",
                 "detected_cert_dives", "detected_cert_days", "detected_ages", "solo_traveler_confirmed",
                 "needs_cert_or_course", "quiere_bucear", "core_pending_slot", "pending_escalation_reason",
                 "duracion_de_buceo", "acompanante_sin_certificar", "acompanante_certificado_inactivo")


async def main():
    from scripts.replay_golden_local import dialogues  # ya salta el oculto

    ocultos = comun.ids_ocultos()
    filas = []
    for did, turns in dialogues():
        assert did not in ocultos
        st = ConversationState(conversation_id=f"paso4-{did}")
        for i, msg in enumerate(turns, 1):
            ACTUAL.update(dialogo=did, turno=i)
            RAG.clear()
            try:
                reply = await supervisor.route_message(st, msg)
            except Exception as exc:  # noqa: BLE001
                reply = f"ERROR {type(exc).__name__}: {exc}"
            snap = {f: getattr(st, f, None) for f in CAMPOS_ESTADO}
            snap["carrito"] = sorted((x.get("type"), x.get("qty")) for x in (st.mixed_cart or []))
            filas.append({"id": did, "turno": i, "msg": msg, "reply": reply if isinstance(reply, str) else str(reply),
                          "estado": json.loads(json.dumps(snap, default=str)), "rag": list(RAG)})
    return filas


filas = asyncio.run(main())
salida = {"modo": a.modo, "flags": a.flags, "turnos": len(filas),
          "errores": sum(1 for f in filas if f["reply"].startswith("ERROR")),
          "llamadas_extractor": LLAMADAS["extractor"], "con_acepta_propuesta": LLAMADAS["con_acepta_propuesta"],
          "filas": filas}
destino = comun.OUT / f"paso4-{a.modo}-{a.salida}.json"
destino.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
print(a.modo, a.flags or "(sin flags)", "turnos", len(filas), "errores", salida["errores"], "llamadas al extractor",
      LLAMADAS["extractor"], "con acepta_propuesta", LLAMADAS["con_acepta_propuesta"], "->", destino.name)
