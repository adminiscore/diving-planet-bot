"""MOD-4 (18-oct): la reescritura de la consulta (condense_query, hoy gpt-4o-mini) con otros modelos. Turnos REALES de
seguimiento de la ronda CAL-F (solo diálogos VISIBLES; los del examen oculto se saltan), los mismos que hoy se
reescriben (_should_condense). Para cada candidato: la consulta que escribe, la latencia, y si cambia respecto a la de
gpt-4o-mini. Local, sin PRE."""
import asyncio
import json
import statistics
import sys
import time

sys.path.insert(0, r"C:\Users\Usuario\Documents\WorkSpace\diving-planet-bot")
from src.agents import query_rewriter as qr  # noqa: E402
from src.config import settings  # noqa: E402
from src.flows.catalog import _detect_language_from_text  # noqa: E402

RONDA = "docs/robustness/synthetic-runs/2026-10-17-calf-completa.jsonl"
GOLDEN = "docs/robustness/golden-set/golden-dialogues.json"
CANDIDATOS = ["gpt-4o-mini", "deepseek/deepseek-v4.1-flash", "gpt-5.4-mini", "gpt-6-luna"]


def turnos():
    ocultos = {d["id"] for d in json.load(open(GOLDEN, encoding="utf-8"))["dialogues"] if d.get("suite") == "oculto"}
    por_conv = {}
    for ln in open(RONDA, encoding="utf-8"):
        r = json.loads(ln)
        if r["tag"] in ocultos:
            continue
        por_conv.setdefault((r["tag"], r["conv"]), []).append(r)
    casos = []
    for (tag, _), rs in por_conv.items():
        rs.sort(key=lambda r: r["turn"])
        hist = []
        for r in rs:
            lang = _detect_language_from_text(r["reply"] or "") or "es"
            if hist and qr._should_condense(r["msg"], hist, lang):
                casos.append({"tag": tag, "turn": r["turn"], "msg": r["msg"], "lang": lang, "hist": list(hist)})
            hist += [{"role": "user", "content": r["msg"]}, {"role": "assistant", "content": (r["reply"] or "")[:600]}]
    return casos


async def main():
    casos = turnos()
    print(len(casos), "turnos que hoy se reescriben", flush=True)
    res = {}
    for modelo in CANDIDATOS:
        settings.openai_model = modelo
        ts, outs = [], []
        for c in casos:
            t0 = time.perf_counter()
            try:
                out = await qr.condense_query(c["msg"], history=c["hist"], lang=c["lang"])
            except Exception as exc:  # noqa: BLE001
                out = f"ERROR {exc}"
            ts.append(time.perf_counter() - t0)
            outs.append(out)
        res[modelo] = {"p50": round(statistics.median(ts), 2), "p90": round(sorted(ts)[int(len(ts) * 0.9) - 1], 2),
                       "salidas": outs, "sin_cambio": sum(o == c["msg"] for o, c in zip(outs, casos))}
        print(f"{modelo:30} p50 {res[modelo]['p50']}s p90 {res[modelo]['p90']}s  devueltas tal cual "
              f"{res[modelo]['sin_cambio']}/{len(casos)}", flush=True)
    json.dump({"casos": [{k: c[k] for k in ("tag", "turn", "msg", "lang")} for c in casos], "res": res},
              open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)


asyncio.run(main())
