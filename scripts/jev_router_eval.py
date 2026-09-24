"""l2-4 (paso 2): Jev frente al router actual en la bateria de las 9 senales (2026-09-24).

SOLO en local: no toca el bot. Traduce el tool de `detect_routing_signals` a preguntas
de Jev (TypeSafe, via el Decisions API de OpenRouter) con las MISMAS descripciones que
lee hoy el LLM, y pasa los casos de `battery_router_signals` por los dos:

- booleanos -> `noul` (probabilidad de que sea cierto; se marca si >= umbral);
- `sensitive_topic` / `booking_change_topic` -> `choice` con la opcion "none";
- `comparing_options` -> un `noul` "esta comparando" + un `noul` por actividad
  (Jev no tiene eleccion multiple).

Mide acierto por caso (igual que la bateria: todas las repeticiones correctas),
separado por idioma y en las senales de seguridad, latencia p50/p95 y coste.

Uso (necesita OPENROUTER_API_KEY y OPENAI_API_KEY en el .env):

    ENV_FILE=.env.dev python -m scripts.jev_router_eval [repeticiones] [umbral] [--v2]

`--v2`: los dos arreglos generales de `_questions` (ver el comentario de `_NONE_SENSITIVE`).
`--bias`: umbral bajo para las senales "ante la duda" (ver `BIAS_SIGNALS`).
"""

import asyncio
import json
import statistics
import sys
import time
from collections import Counter

import httpx

from scripts import battery_activity_choice as bac
from scripts import battery_router_signals as brs
from src.agents import escalation
from src.config import settings
from src.prompts.router import ROUTING_TOOL

JEV_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "typesafe/jev-1.13"  # version fija: el resultado tiene que ser repetible
SAFETY = ("wants_human", "sensitive_topic", "adaptive_diving_topic")  # no se pueden fallar

_PROPS = ROUTING_TOOL["function"]["parameters"]["properties"]
_CONTEXT = (
    "Message from a customer to the booking chatbot of a scuba diving center "
    "(Diving Planet, Cartagena, Colombia). The message may be in Spanish or English."
)


# v2: dos arreglos GENERALES a los fallos de la v1 (nada por frase de la bateria).
# 1) En Jev cada pregunta se contesta sin ver las demas, asi que el "nunca las dos a
#    la vez" que el LLM respeta al ver el tool entero se pierde. Se mete DENTRO de la
#    eleccion: la opcion "none" nombra las senales especificas que tienen su propio
#    campo (lo especifico gana a lo general, como en el orden del router).
# 2) Las actividades se describen tambien con el vocabulario del cliente en espanol.
_NONE_SENSITIVE = (
    "None of the above. This includes messages that belong to a MORE SPECIFIC signal "
    "with its own field: asking to talk to a person without a complaint (that is "
    "wants_human), reporting that a link/page/button we sent is broken (that is "
    "broken_link_complaint), or a disability/accessibility topic (that is "
    "adaptive_diving_topic). Also general policy or catalog questions."
)
_ACTIVITY_ES = {
    "certified_diving": "scuba diving as a certified diver (Spanish: 'buceo', 'bucear', 'inmersiones')",
    "minicourse": "the first-time discover-scuba mini course (Spanish: 'minicurso', 'bautizo', 'primera vez')",
    "snorkel": "snorkeling (Spanish: 'snorkel', 'esnórquel')",
    "padi_course": "a full PADI certification course (Spanish: 'curso', 'Open Water', 'Advanced', 'certificarse')",
}


def _questions(v2: bool = False) -> dict:
    """El tool del router como preguntas de Jev, con las mismas descripciones."""
    q = {}
    for name in ("wants_human", "wants_menu_or_restart", "adaptive_diving_topic",
                 "availability_question", "broken_link_complaint", "asks_for_contact_number"):
        q[name] = {"type": "noul", "instructions": _PROPS[name]["description"]}
    for name in ("sensitive_topic", "booking_change_topic"):
        spec = _PROPS[name]
        criteria = {v: f"The message is '{v}' as described." for v in spec["enum"]}
        criteria["none"] = (
            _NONE_SENSITIVE if v2 and name == "sensitive_topic" else "None of the above applies to this message."
        )
        q[name] = {"type": "choice", "instructions": spec["description"], "criteria": criteria}
    comp = _PROPS["comparing_options"]["properties"]
    q["comparing"] = {"type": "noul", "instructions": comp["comparing"]["description"]}
    for opt in comp["options"]["items"]["enum"]:
        label = _ACTIVITY_ES[opt] if v2 else f"'{opt}'"
        q[f"opt_{opt}"] = {
            "type": "noul",
            "instructions": f"The customer is weighing {label} as one of the options. "
            + comp["options"]["description"],
        }
    return q


QUESTIONS = _questions(v2="--v2" in sys.argv)


# Senales que el esquema del router pide marcar "ante la duda" (description del tool:
# "when genuinely unsure ... still set it"). Con `--bias` se marcan desde un umbral mas
# bajo, fijado ANTES de medir: 0,3 = "salvo que Jev este bastante seguro de que no".
BIAS_SIGNALS = ("sensitive_topic", "adaptive_diving_topic", "broken_link_complaint", "availability_question")
BIAS_THRESHOLD = 0.3


def _to_signals(answers: dict, threshold: float, bias: float | None = None) -> dict:
    """Respuestas de Jev -> el mismo dict que devuelve `detect_routing_signals`."""
    out = {}
    for name, a in answers.items():
        cut = bias if bias is not None and name in BIAS_SIGNALS else threshold
        if a["type"] == "noul" and not name.startswith("opt_") and name != "comparing":
            if a["noul"] >= cut:
                out[name] = True
        elif a["type"] == "choice":
            if a["choice"] != "none":
                out[name] = a["choice"]
            elif cut < threshold:
                # "ante la duda": la mejor opcion que no sea "none", si llega al umbral bajo
                probs = {k: v for k, v in (a.get("probabilities") or {}).items() if k != "none"}
                if probs and max(probs.values()) >= cut:
                    out[name] = max(probs, key=probs.get)
    if answers["comparing"]["noul"] >= threshold:
        opts = [n[4:] for n, a in answers.items() if n.startswith("opt_") and a["noul"] >= threshold]
        out["comparing_options"] = {"comparing": True, "options": opts}
    return out


async def _jev(client: httpx.AsyncClient, key: str, msg: str) -> tuple[dict, float, float]:
    t = time.perf_counter()
    r = await client.post(
        JEV_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={"model": JEV_MODEL, "state": f"{_CONTEXT}\n\nCustomer message: {msg}", "questions": QUESTIONS},
        timeout=30,
    )
    ms = (time.perf_counter() - t) * 1000
    r.raise_for_status()
    body = r.json()
    return body["answers"], ms, float(body.get("usage", {}).get("cost") or 0.0)


async def _router(msg: str, lang: str) -> tuple[dict, float]:
    t = time.perf_counter()
    got = await escalation.detect_routing_signals(msg, lang=lang)
    return got, (time.perf_counter() - t) * 1000


def _pct(v: list[float], p: float) -> float:
    v = sorted(v)
    return v[min(len(v) - 1, int(round(p * (len(v) - 1))))]


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    reps = int(args[0]) if args else 8
    threshold = float(args[1]) if len(args) > 1 else 0.5
    key = (settings.model_extra or {}).get("openrouter_api_key") or ""
    if not key:
        import os

        from dotenv import dotenv_values
        key = (dotenv_values(os.environ.get("ENV_FILE", ".env")).get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        sys.exit("Falta OPENROUTER_API_KEY en el .env")

    bac._restore()  # variante `base` del router: la de PRE
    cases = brs._cases()
    res = {"jev": {}, "router": {}}
    lat = {"jev": [], "router": []}
    cost_jev = 0.0
    raw_probs = {}
    async with httpx.AsyncClient() as client:
        for cid, lang, msg, expected in cases:
            outs = {"jev": [], "router": []}
            for _ in range(reps):
                answers, ms, cost = await _jev(client, key, msg)
                lat["jev"].append(ms)
                cost_jev += cost
                outs["jev"].append(brs._signals(_to_signals(answers, threshold, BIAS_THRESHOLD if "--bias" in sys.argv else None)))
                raw_probs.setdefault(cid, []).append(
                    {n: (a.get("noul") if a["type"] == "noul" else a.get("choice")) for n, a in answers.items()}
                )
                got, ms = await _router(msg, lang)
                lat["router"].append(ms)
                outs["router"].append(brs._signals(got))
            for who in ("jev", "router"):
                oks = sum(brs._ok(o, expected) for o in outs[who])
                res[who][cid] = (oks, Counter(brs._show(o) for o in outs[who]))

    def resumen(who):
        total = sum(1 for c in cases if res[who][c[0]][0] == reps)
        por_idioma = {
            lg: f"{sum(1 for c in cases if c[1] == lg and res[who][c[0]][0] == reps)}/{sum(1 for c in cases if c[1] == lg)}"
            for lg in ("es", "en")
        }
        seg = [c for c in cases if set(c[3]) & set(SAFETY)]
        seg_ok = sum(1 for c in seg if res[who][c[0]][0] == reps)
        return total, por_idioma, f"{seg_ok}/{len(seg)}"

    print(f"Jev {JEV_MODEL} vs router ({settings.extraction_model}) · {reps} repeticiones · umbral {threshold}\n")
    for cid, _lang, msg, expected in cases:
        j, r = res["jev"][cid][0], res["router"][cid][0]
        marca = "  " if j == r else ("▲ " if j > r else "▼ ")
        print(f"{marca}{cid:30} jev {j}/{reps}  router {r}/{reps}  esperado={brs._show(expected)}  «{msg[:55]}»")
        if j < reps:
            print(f"      jev vio: {dict(res['jev'][cid][1])}")
    print()
    for who in ("jev", "router"):
        total, idioma, seg = resumen(who)
        print(f"{who:6} casos perfectos {total}/{len(cases)} · ES {idioma['es']} · EN {idioma['en']} · "
              f"senales de seguridad {seg} · latencia p50 {statistics.median(lat[who]):.0f} ms / "
              f"p95 {_pct(lat[who], 0.95):.0f} ms")
    print(f"coste Jev: {cost_jev:.5f} $ en {len(lat['jev'])} llamadas")
    out = {
        "modelo": JEV_MODEL, "router": settings.extraction_model, "repeticiones": reps, "umbral": threshold,
        "resumen": {w: dict(zip(("perfectos", "por_idioma", "seguridad"), resumen(w))) for w in ("jev", "router")},
        "latencia_ms": {w: {"p50": statistics.median(lat[w]), "p95": _pct(lat[w], 0.95)} for w in lat},
        "coste_jev_usd": cost_jev,
        "casos": {c[0]: {"jev": res["jev"][c[0]][0], "router": res["router"][c[0]][0]} for c in cases},
        "probabilidades_jev": raw_probs,
    }
    print("JSON " + json.dumps(out, ensure_ascii=False, default=str))


if __name__ == "__main__":
    asyncio.run(main())
