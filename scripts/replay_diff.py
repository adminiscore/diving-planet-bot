"""Compara dos pasadas de `scripts/replay_golden_local.py` (off/on): preguntas contestadas y
datos que SOLO guarda la versión "on"; un juez (gpt-5-mini) dice si cada dato de más lo
afirma el cliente. OJO: separa luego el ruido (mensajes sin pregunta o con estado previo ya
distinto entre pasadas) antes de concluir; el juez es estricto con los mapeos de producto
("paquete de 5 buceos" -> buceo certificado es correcto). Etiquetas de pregunta:
docs/robustness/u3-4/preguntas-etiquetadas.json.

    python -m scripts.replay_diff --dir u3-4
"""
import asyncio
import json
import sys
from pathlib import Path

from dotenv import dotenv_values
from openai import AsyncOpenAI

D = Path("docs/robustness") / (sys.argv[sys.argv.index("--dir") + 1] if "--dir" in sys.argv else "u3-4")
K = dotenv_values(".env.dev")["OPENAI_API_KEY"].strip()
MARK = "«RAG»"
DATA = ("detected_activity", "is_certified", "location", "detected_location", "hotel", "detected_group_size",
        "detected_group_allocation", "is_colombian", "last_dive_over_2_years", "refresher_interested")


def load(name):
    rows = [json.loads(line) for line in open(D / f"replay-{name}.jsonl", encoding="utf-8")]
    return {(r["id"], r["turn"]): r for r in rows}


off, on = load("off"), load("on")
label = {o["msg"]: o["label"] for o in json.load(open(Path("docs/robustness/u3-4/preguntas-etiquetadas.json"), encoding="utf-8"))}


def changes(run, key):
    did, t = key
    prev = run.get((did, t - 1), {"state": {}})["state"]
    cur = run[key]["state"]
    return {f: cur.get(f) for f in DATA if cur.get(f) != prev.get(f) and cur.get(f) not in (None, "{}", {}, "None")}


JUEZ = ("Te doy lo que un cliente ha escrito a un chatbot de reservas de buceo (sus mensajes, en orden) y DATOS que "
        "el sistema guardó al leer el ÚLTIMO mensaje. Para cada dato di si el cliente lo AFIRMA en sus mensajes "
        "(aunque sea con otras palabras) o si es INVENTADO/SUPUESTO (hipotético, sale de una pregunta, deducción "
        "sin base). Responde SOLO JSON: {\"inventados\": [\"campo\", ...], \"por_que\": \"...\"}")


async def main():
    keys = sorted(set(off) & set(on))
    q = [k for k in keys if label.get(on[k]["msg"])]
    print(f"turnos {len(keys)} | con pregunta (etiqueta) {len(q)}")
    ans_off = sum(off[k]["rag"] for k in q)
    ans_on = sum(on[k]["rag"] for k in q)
    both_on = sum(1 for k in q if on[k]["rag"] and len(on[k]["reply"].replace(MARK, "").strip()) > 20)
    print(f"preguntas contestadas por el RAG: off {ans_off} -> on {ans_on} | on con respuesta Y reserva: {both_on}")
    nq_rag = [k for k in keys if not label.get(on[k]["msg"]) and on[k]["rag"] and not off[k]["rag"]]
    print(f"turnos SIN pregunta (etiqueta) que ahora pasan por el RAG: {len(nq_rag)}")
    for k in nq_rag[:15]:
        print("   ", k, "|", on[k]["msg"][:90].replace("\n", " "))
    # datos que guarda on y no off en el mismo turno
    diffs = []
    for k in keys:
        c_on, c_off = changes(on, k), changes(off, k)
        extra = {f: v for f, v in c_on.items() if c_off.get(f) != v}
        if extra:
            diffs.append((k, extra))
    print(f"turnos en los que on guarda un dato que off no guarda: {len(diffs)}")
    oa = AsyncOpenAI(api_key=K)
    sem = asyncio.Semaphore(6)

    async def judge(k, extra):
        async with sem:
            msgs = [on[(k[0], t)]["msg"] for t in range(1, k[1] + 1)]
            u = "\n".join(f"{i}. {m}" for i, m in enumerate(msgs, 1)) + f"\n\nDATOS: {json.dumps(extra, ensure_ascii=False)}"
            r = await oa.chat.completions.create(model="gpt-5-mini", reasoning_effort="low",
                                                 response_format={"type": "json_object"},
                                                 messages=[{"role": "system", "content": JUEZ}, {"role": "user", "content": u}])
            return json.loads(r.choices[0].message.content)

    verdicts = await asyncio.gather(*(judge(k, e) for k, e in diffs))
    bad = []
    for (k, extra), v in zip(diffs, verdicts):
        tag = "INVENTADO" if v.get("inventados") else "ok"
        print(f"- [{tag}] {k[0]}#{k[1]} | {on[k]['msg'][:80]!r} | {extra}" + (f" | {v.get('inventados')} {v.get('por_que', '')[:160]}" if v.get("inventados") else ""))
        if v.get("inventados"):
            bad.append({"key": k, "msg": on[k]["msg"], "extra": extra, **v})
    json.dump({"diffs": [{"key": k, "extra": e, "verdict": v} for (k, e), v in zip(diffs, verdicts)]},
              open(D / "diff.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(f"\nRESUMEN: datos de más en {len(diffs)} turnos; el juez ve inventados en {len(bad)}")

asyncio.run(main())
