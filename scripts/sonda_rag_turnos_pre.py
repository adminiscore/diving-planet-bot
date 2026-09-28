"""Escalón 0 del RAG DENTRO de PRE: repetir turnos reales de una ronda con el historial real, con un flag
apagado y encendido, y ver por qué rechaza el juez de grounding (28-sep; con esto se midieron `RAG_CONCISE`
y `RAG_REGEN_FEEDBACK`, HISTORY 0.29.67-0.29.68).

Corre `rag_answer` dentro del contenedor `dp-pre-bot` (base de conocimiento, catálogo y modelos de PRE) por
SSH; el flag solo se cambia en ese proceso, así que PRE no cambia para nadie. Espía al juez: guarda cada
respuesta rechazada con su motivo, para saber si un "no lo tengo" viene del juez o de la búsqueda.
**Nunca usa el examen oculto** (`suite == "oculto"` del golden): esos diálogos se saltan siempre.

    # turnos concretos de una ronda (etiqueta#turno), flag apagado y encendido, 2 veces
    python -m scripts.sonda_rag_turnos_pre --run docs/robustness/synthetic-runs/2026-09-27-paso8.jsonl \\
        --turns "paquete-5-buceos-cop-refresh-y-hoteles#2,principiante-hora-lugar-y-precio#3" --flag rag_regen_feedback --reps 2
    # todos los turnos que contestó el RAG en una ronda (lee las líneas `[RAG] Query` de sus logs de PRE)
    python -m scripts.sonda_rag_turnos_pre --run docs/robustness/synthetic-runs/2026-09-28-cache-B2.jsonl \\
        --from-log docs/robustness/logs-pre-2026-09-28-cache-B2.txt --flag rag_concise
    # solo ver qué casos saldrían, sin gastar nada
    python -m scripts.sonda_rag_turnos_pre --run ... --turns ... --dry

Coste: cada respuesta son 2-4 llamadas con ~8.000 tokens de contexto (~0,02-0,03 $). 34 turnos × 2 lados
≈ 1,5 $. La cuenta de OpenAI es la MISMA que usa PRE: si se queda sin crédito, PRE deja de contestar.
Salida: JSONL (una línea por respuesta) y un resumen por lado (caracteres, segundos, "no lo tengo", rechazos).
"""
import argparse
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "docs/robustness/golden-set/golden-dialogues.json"
_EN = re.compile(r"\b(the|is|are|we|you|what|how|can|do|does|i'm|would|hi|hello|thanks|my|me|i)\b", re.I)

_REMOTO = r'''
import asyncio, json, time
from src.config import settings
from src.observability import _TURN_FACTS
from src.agents import rag_agent
from src.agents.rag_agent import FALLBACK_ES, FALLBACK_EN
CASOS, FLAG, REPS = json.loads(CASOS_JSON), FLAG_NAME, N_REPS
juicios = []
_orig = rag_agent.is_grounded
async def _spy(answer, context, lang="es"):
    ok, why = await _orig(answer, context, lang=lang)
    juicios.append({"ok": ok, "why": why[:400], "answer": answer[:600]})
    return ok, why
rag_agent.is_grounded = _spy

async def una(c, lado):
    if FLAG:
        setattr(settings, FLAG, lado)
    juicios.clear()
    tok = _TURN_FACTS.set({})
    t0 = time.perf_counter()
    try:
        ans = await rag_agent.rag_answer(c["msg"], lang=c["lang"], history=c["history"])
    except Exception as exc:  # noqa: BLE001
        ans = f"ERROR {type(exc).__name__}: {exc}"
    s = time.perf_counter() - t0
    llamadas = len((_TURN_FACTS.get() or {}).get("_llm", []))
    _TURN_FACTS.reset(tok)
    return {"id": c["id"], "flag": lado if FLAG else None, "s": round(s, 2), "chars": len(ans or ""),
            "n_llm": llamadas, "fallback": (ans or "").strip() in (FALLBACK_ES, FALLBACK_EN),
            "error": (ans or "").startswith("ERROR "), "ans": ans, "juicios": list(juicios)}

async def main():
    for i, c in enumerate(CASOS):
        for rep in range(REPS):
            # se alterna el orden para que ninguno de los dos lados vaya siempre primero
            lados = ([False, True] if (i + rep) % 2 == 0 else [True, False]) if FLAG else [None]
            for lado in lados:
                print(json.dumps(await una(c, lado), ensure_ascii=False), flush=True)

asyncio.run(main())
'''


def _oculto() -> set[str]:
    dialogos = json.loads(GOLDEN.read_text(encoding="utf-8"))["dialogues"]
    return {d["id"] for d in dialogos if d.get("suite") == "oculto"}


def turnos_del_log(log_path: Path, rows: list[dict]) -> list[str]:
    """Los turnos que contestó el RAG en la ronda: casan las líneas `[RAG] Query: <inicio>...` con los mensajes."""
    consultas = re.findall(r"\[RAG\] Query: (.*?)\.\.\. \| Docs", log_path.read_text(encoding="utf-8"))
    usados, out = set(), []
    for q in consultas:
        for i, r in enumerate(rows):
            if i not in usados and r["msg"].startswith(q):
                usados.add(i)
                out.append(f"{r['tag']}#{r['turn']}")
                break
    return out


def construir_casos(rows: list[dict], turnos: list[str], oculto: set[str]) -> tuple[list[dict], list[str]]:
    """Cada turno con el historial real de su conversación (turnos anteriores de la ronda). Salta el oculto."""
    casos, saltados = [], []
    for t in turnos:
        tag, turn = t.rsplit("#", 1)
        if tag in oculto:
            saltados.append(t)
            continue
        r = next((x for x in rows if x["tag"] == tag and x["turn"] == int(turn)), None)
        if r is None:
            raise SystemExit(f"no está en la ronda: {t}")
        hist = []
        for p in sorted((x for x in rows if x["conv"] == r["conv"] and x["turn"] < r["turn"]), key=lambda x: x["turn"]):
            hist += [{"role": "user", "content": p["msg"]}, {"role": "assistant", "content": p["reply"]}]
        lang = "en" if len(_EN.findall(r["msg"])) >= 2 else "es"
        casos.append({"id": t, "msg": r["msg"], "lang": lang, "history": hist})
    return casos, saltados


def resumen(filas: list[dict]) -> str:
    if not filas:
        return "sin filas"
    ch = sorted(f["chars"] for f in filas)
    s = sorted(f["s"] for f in filas)
    rech = sum(1 for f in filas for j in f["juicios"] if not j["ok"])
    return (f"n={len(filas)} · caracteres p50 {statistics.median(ch):.0f} · segundos media {statistics.mean(s):.2f} "
            f"p90 {s[int(len(s) * 0.9)]:.2f} · \"no lo tengo\" {sum(f['fallback'] for f in filas)} · "
            f"rechazos del juez {rech} · errores {sum(f['error'] for f in filas)}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", required=True, help="JSONL de una ronda (scripts.run_synthetic_pre): da mensajes e historial")
    grupo = ap.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--turns", help="etiqueta#turno separados por coma")
    grupo.add_argument("--from-log", help="logs de PRE de esa ronda: usa todos los turnos que contestó el RAG")
    ap.add_argument("--flag", help="setting booleano a comparar apagado/encendido (p. ej. rag_regen_feedback)")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--out", help="JSONL de salida (por defecto, junto a la ronda: <ronda>__sonda.jsonl)")
    ap.add_argument("--dry", action="store_true", help="solo lista los casos, sin llamar a PRE")
    args = ap.parse_args()

    run = Path(args.run)
    rows = [json.loads(line) for line in run.open(encoding="utf-8") if line.strip()]
    turnos = [t.strip() for t in args.turns.split(",") if t.strip()] if args.turns else turnos_del_log(Path(args.from_log), rows)
    casos, saltados = construir_casos(rows, turnos, _oculto())
    lados = 2 if args.flag else 1
    print(f"{len(casos)} casos × {args.reps} rep × {lados} lado(s) = {len(casos) * args.reps * lados} respuestas "
          f"(~{len(casos) * args.reps * lados * 0.025:.2f} $)" + (f" · saltados por examen oculto: {saltados}" if saltados else ""))
    if args.dry:
        for c in casos:
            print(f"  {c['id']} [{c['lang']}] historial {len(c['history']) // 2} turnos | {c['msg'][:90]}")
        return

    from scripts.pre_access import pre_ssh

    script = (f"CASOS_JSON = {json.dumps(casos, ensure_ascii=False)!r}\nFLAG_NAME = {args.flag!r}\n"
              f"N_REPS = {args.reps}\n{_REMOTO}")
    r = pre_ssh("docker exec -i dp-pre-bot python -", input_text=script, timeout=max(600, 60 * len(casos) * args.reps * lados))
    filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
    out = Path(args.out) if args.out else run.with_name(run.stem + "__sonda.jsonl")
    out.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8")
    print(f"resultados: {len(filas)} → {out}")
    if args.flag:
        for lado in (False, True):
            print(f"  {args.flag}={'on ' if lado else 'off'}: {resumen([f for f in filas if f['flag'] is lado])}")
    else:
        print(f"  {resumen(filas)}")
    if len(filas) < len(casos) * args.reps * lados:
        print("⚠️ faltan respuestas; stderr de PRE:\n" + (r.stderr or "")[-2000:])


if __name__ == "__main__":
    main()
