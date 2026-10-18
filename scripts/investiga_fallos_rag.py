"""Investigación (15-oct, Gadea): ¿POR QUÉ falla el RAG en los turnos que el juez marca? Búsqueda, redacción o azar.

Tras el examen ex-10, 56 de los 73 fallos están en turnos que escribió el RAG (`scripts.fallos_por_turno`). Aquí se
repite cada uno de esos turnos DENTRO de PRE (`rag_answer` con el historial real de su conversación, N veces) y se
guarda el CONTEXTO exacto que vio el modelo (el que recibe el revisor de grounding). Después un verificador (gpt-4.1,
temperatura 0) contesta, fallo a fallo:
  1. ¿El contexto contiene la información que el criterio exige?           → no: BUSQUEDA
  2. ¿Cumplen el criterio las respuestas repetidas?                         → ninguna: REDACCION · alguna: AZAR
  3. ¿El criterio depende de algo que el RAG no puede saber solo (el estado de la reserva, una regla de negocio que
     no está en la base)?                                                    → FUERA (no es del RAG)

Límite: la repetición no lleva el resumen del estado de la reserva (`extra_context`) que llevaba el turno real; lo
que dependa de él sale como FUERA o AZAR, no como fallo del RAG.

El examen oculto de ex-10 ya está GASTADO (15-oct): aquí sí se incluyen sus turnos, para entender por qué fallan.
Nunca usar esto con un examen oculto nuevo.

    ENV_FILE=.env.dev python -m scripts.investiga_fallos_rag --ronda 2026-10-15-ex10-completa --reps 2
    ENV_FILE=.env.dev python -m scripts.investiga_fallos_rag --solo-verificar   # vuelve a juzgar sin repetir en PRE
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "docs/robustness/synthetic-runs"
DIR = ROOT / "docs/robustness/investigacion"
GOLDEN = ROOT / "docs/robustness/golden-set/golden-dialogues.json"

_REMOTO = r'''
import asyncio, json
from src.agents import rag_agent
CASOS, REPS = json.loads(CASOS_JSON), N_REPS
vistos = []
_orig = rag_agent.is_grounded
async def _spy(answer, context, lang="es"):
    ok, why = await _orig(answer, context, lang=lang)
    vistos.append({"ok": ok, "why": why[:300], "context": context})
    return ok, why
rag_agent.is_grounded = _spy
async def main():
    for c in CASOS:
        for rep in range(REPS):
            vistos.clear()
            try:
                ans = await rag_agent.rag_answer(c["msg"], lang=c["lang"], history=c["history"])
            except Exception as exc:
                ans = f"ERROR {type(exc).__name__}: {exc}"
            ctx = vistos[-1]["context"] if vistos else ""
            print(json.dumps({"id": c["id"], "rep": rep, "ans": ans, "context": ctx,
                              "rechazos": [v["why"] for v in vistos if not v["ok"]]}, ensure_ascii=False), flush=True)
asyncio.run(main())
'''

_VERIFICA = (
    "Eres auditor de un chatbot de un centro de buceo. Te doy un CRITERIO que la respuesta del bot debía cumplir, el "
    "motivo por el que un juez dijo que no lo cumplió, el CONTEXTO que tenía el bot (su base de conocimiento para ese "
    "turno) y varias RESPUESTAS del bot al mismo mensaje. Contesta SOLO JSON:\n"
    '{"info_en_contexto": "si|parcial|no", "que_falta": "<si no o parcial: qué dato del criterio no está, máx 15 '
    'palabras>", "respuestas_cumplen": [true/false por respuesta], "depende_de_estado_o_negocio": true/false, '
    '"mecanismo": "<por qué crees que el bot falla, máx 20 palabras>"}\n'
    "info_en_contexto: ¿el contexto contiene la información necesaria para cumplir el criterio? "
    "depende_de_estado_o_negocio: true si el criterio exige algo que el RAG no puede deducir del contexto ni del "
    "mensaje (un dato de la reserva en curso, una regla de negocio que no está en el contexto)."
)


def _fallos_rag(ronda: str) -> list[dict]:
    f = json.loads((DIR / "fallos-por-turno-ex10.json").read_text(encoding="utf-8"))
    causas = {(x["dialogo"], x["criterio"]): x for x in json.loads(
        (ROOT / "docs/robustness/ex10/fallos-ex10-por-causa.json").read_text(encoding="utf-8"))}
    golden = {d["id"]: d for d in json.loads(GOLDEN.read_text(encoding="utf-8"))["dialogues"]}
    out = []
    for x in f:
        if x.get("tipo") != "rag" or not x.get("turno"):
            continue
        c = causas.get((x["dialogo"], x["criterio"]), {})
        check = next((k.get("check") for k in golden.get(x["dialogo"], {}).get("criteria", []) if k.get("id") == x["criterio"]), "")
        out.append({**x, "causa_ex10": c.get("causa"), "check": check})
    return out


def _casos(ronda: str, fallos: list[dict]) -> list[dict]:
    rows = [json.loads(ln) for ln in (RUNS / f"{ronda}.jsonl").open(encoding="utf-8") if ln.strip()]
    casos, vistos = [], set()
    for x in fallos:
        clave = f"{x['dialogo']}#{x['turno']}"
        if clave in vistos:
            continue
        vistos.add(clave)
        r = next((y for y in rows if y["tag"] == x["dialogo"] and y["turn"] == int(x["turno"])), None)
        if r is None:
            continue
        hist = []
        for p in sorted((y for y in rows if y["conv"] == r["conv"] and y["turn"] < r["turn"]), key=lambda y: y["turn"]):
            hist += [{"role": "user", "content": p["msg"]}, {"role": "assistant", "content": p["reply"]}]
        from scripts.sonda_rag_turnos_pre import _EN
        lang = "en" if len(_EN.findall(r["msg"])) >= 2 else "es"
        casos.append({"id": clave, "msg": r["msg"], "lang": lang, "history": hist})
    return casos


async def _verificar(fallos: list[dict], repes: dict) -> list[dict]:
    from openai import AsyncOpenAI

    from src.config import settings

    cli = AsyncOpenAI(api_key=settings.openai_api_key)
    sem = asyncio.Semaphore(8)

    async def uno(x):
        filas = repes.get(f"{x['dialogo']}#{x['turno']}", [])
        if not filas:
            return {**x, "veredicto_inv": "sin_repeticion"}
        ctx = filas[0]["context"][:60000]
        resp = "\n\n".join(f"[R{i + 1}] {f['ans']}" for i, f in enumerate(filas))
        async with sem:
            r = await cli.chat.completions.create(
                model="gpt-6-luna", temperature=0, response_format={"type": "json_object"},  # mod-8: antes gpt-4.1
                messages=[{"role": "system", "content": _VERIFICA},
                          {"role": "user", "content": f"CRITERIO: {x['check']}\nMOTIVO DEL JUEZ: {x['motivo']}\n\n"
                                                      f"MENSAJE DEL CLIENTE: {x.get('mensaje_cliente', '')}\n\n"
                                                      f"CONTEXTO:\n{ctx}\n\nRESPUESTAS:\n{resp}"}])
        v = json.loads(r.choices[0].message.content or "{}")
        cumplen = v.get("respuestas_cumplen") or []
        if v.get("depende_de_estado_o_negocio"):
            ver = "fuera"
        elif v.get("info_en_contexto") == "no":
            ver = "busqueda"
        elif any(cumplen):
            ver = "azar"
        else:
            ver = "redaccion"
        return {**x, **v, "veredicto_inv": ver, "rechazos_revisor": sum(len(f["rechazos"]) for f in filas),
                "respuestas_repetidas": [f["ans"] for f in filas]}

    return await asyncio.gather(*[uno(x) for x in fallos])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ronda", default="2026-10-15-ex10-completa")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--solo-verificar", action="store_true")
    a = ap.parse_args()
    fallos = _fallos_rag(a.ronda)
    crudo = DIR / f"repeticiones-{a.ronda}.jsonl"
    if not a.solo_verificar:
        casos = _casos(a.ronda, fallos)
        print(f"{len(fallos)} fallos del RAG en {len(casos)} turnos × {a.reps} repeticiones (~{len(casos) * a.reps * 0.03:.1f} $)")
        from scripts.pre_access import pre_ssh

        script = f"CASOS_JSON = {json.dumps(casos, ensure_ascii=False)!r}\nN_REPS = {a.reps}\n{_REMOTO}"
        r = pre_ssh("docker exec -i dp-pre-bot python -", input_text=script, timeout=max(900, 40 * len(casos) * a.reps))
        lineas = [ln for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
        crudo.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        print(f"repeticiones: {len(lineas)} → {crudo}")
        if len(lineas) < len(casos) * a.reps:
            print("⚠️ faltan repeticiones; stderr de PRE:\n" + (r.stderr or "")[-1500:])
    repes: dict = {}
    for ln in crudo.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            f = json.loads(ln)
            repes.setdefault(f["id"], []).append(f)
    res = asyncio.run(_verificar(fallos, repes))
    salida = DIR / f"por-que-falla-el-rag-{a.ronda}.json"
    salida.write_text(json.dumps([{k: v for k, v in x.items() if k != "respuestas_repetidas"} | {
        "respuestas_repetidas": [r[:700] for r in x.get("respuestas_repetidas", [])]} for x in res],
        ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(Counter(x["veredicto_inv"] for x in res))
    print(f"→ {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
