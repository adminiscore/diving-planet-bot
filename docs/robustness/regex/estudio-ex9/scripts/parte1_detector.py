"""Parte 1: el detector (intent_detector) sobre los 342 mensajes visibles distintos, sin red.

- Qué campos pone cada sub-detector (`_detect_*`) y cuántas veces.
- Qué patrones se evalúan y casan (trazador), por función llamadora.
- Funciones públicas que usan otros módulos.
Salida: out/parte1.json
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comun  # noqa: E402

comun.bloquear_red()

import trazador  # noqa: E402
from src.agents import intent_detector as idet  # noqa: E402
from src.flows.state import ConversationState  # noqa: E402

trazador.instala(idet)

CAMPOS = ("language", "activity", "service_id", "is_certified", "group_size", "group_allocation",
          "last_dive_over_2_years", "duration", "location", "island", "hotel", "ages", "cert_dives", "cert_days",
          "is_colombian", "solo_confirmed")

# Atribuir a cada sub-detector los campos que pone.
POR_SUBDETECTOR: dict = defaultdict(lambda: defaultdict(list))  # sub -> campo -> [i]
_SUBS = ("_detect_language", "_detect_activity", "_detect_certification", "_detect_group_info", "_detect_ages",
         "_detect_last_dive", "_detect_duration", "_detect_location", "_detect_nationality",
         "_split_out_uncertifiable_kids")


def _vale(c, v):
    if c == "solo_confirmed":
        return v is True
    return v is not None and v != [] and v != {}


def _snap(intent):
    return {c: getattr(intent, c) for c in CAMPOS}


def _envuelve(nombre):
    original = getattr(idet.IntentDetector, nombre)

    def w(self, *a, **k):
        intent = next(x for x in a if isinstance(x, idet.DetectedIntent))
        antes = _snap(intent)
        r = original(self, *a, **k)
        despues = _snap(intent)
        for c in CAMPOS:
            if despues[c] != antes[c] and _vale(c, despues[c]):
                POR_SUBDETECTOR[nombre][c].append(trazador.CTX["i"])
        return r

    setattr(idet.IntentDetector, nombre, w)


for s in _SUBS:
    _envuelve(s)

# La regla del final de detect() (actividad inferida de la certificación / del reparto) va aparte.

filas = comun.corpus()
pesos = comun.pesos_rondas()
msgs = list(dict.fromkeys(f["msg"] for f in filas))
detector = idet.IntentDetector()
salida_por_msg = []
for i, m in enumerate(msgs):
    trazador.CTX["i"] = i
    trazador.CTX["ctx"] = "detect"
    intent = detector.detect(m, ConversationState(conversation_id="estudio"))
    res = {c: v for c, v in _snap(intent).items() if _vale(c, v)}
    pub = {}
    trazador.CTX["ctx"] = "publicas"
    low = m.lower()
    pub["certification_claim"] = idet.certification_claim(m)
    pub["certification_claim_otros"] = idet.certification_claim(m, about_writer=False)
    pub["certification_status"] = idet.certification_status(m)
    pub["certification_is_ambiguous"] = idet.certification_is_ambiguous(m)
    pub["nationality_is_ambiguous"] = idet.nationality_is_ambiguous(m)
    pub["course_level_is_ambiguous"] = idet.course_level_is_ambiguous(m)
    pub["matched_activity_categories"] = sorted(idet.matched_activity_categories(m))
    pub["courses_mentioned"] = idet.courses_mentioned(m)
    for nombre in ("mentions_other_person_subject", "mentions_writer_and_others"):  # ex-9b: borradas, sin llamador
        if hasattr(idet, nombre):
            pub[nombre] = getattr(idet, nombre)(m)
    pub["dive_counts_in"] = idet.dive_counts_in(m)
    pub = {k: v for k, v in pub.items() if v is not None and v != [] and not (v is False and k not in ("certification_claim", "certification_claim_otros", "certification_status"))}
    salida_por_msg.append({"i": i, "msg": m, "peso_rondas": pesos.get(m, 0), "detect": res, "publicas": pub})

rec = []
for (mod, nombre, func), r in trazador.REC.items():
    rec.append({"modulo": mod, "patron": nombre, "funcion": func, "evals": r["evals"], "hits": r["hits"],
                "msgs_eval": len(r["msgs_eval"]), "msgs_casa": len(r["msgs"]),
                "msgs_casa_detect": len(r["ctx"].get("detect", ())), "msgs_casa_publicas": len(r["ctx"].get("publicas", ())),
                "ejemplos": [msgs[j][:140] for j in sorted(r["msgs"])[:4]]})
rec.sort(key=lambda x: (-x["msgs_casa"], x["patron"]))

campos_detect = Counter()
for s in salida_por_msg:
    for c in s["detect"]:
        campos_detect[c] += 1
por_sub = {s: {c: len(set(v)) for c, v in d.items()} for s, d in POR_SUBDETECTOR.items()}
ejemplos_sub = {s: {c: [msgs[j][:140] for j in sorted(set(v))[:3]] for c, v in d.items()} for s, d in POR_SUBDETECTOR.items()}
out = {"mensajes": len(msgs), "turnos": len(filas), "campos_detect": dict(campos_detect), "por_subdetector": por_sub,
       "ejemplos_subdetector": ejemplos_sub, "patrones": rec, "por_mensaje": salida_por_msg}
(comun.OUT / "parte1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("mensajes", len(msgs), "turnos", len(filas))
print("campos que pone detect():", dict(campos_detect.most_common()))
print("por sub-detector:", json.dumps(por_sub, ensure_ascii=False))
print("patrones trazados:", len(rec), "que casan alguna vez:", sum(1 for r in rec if r["msgs_casa"]))
