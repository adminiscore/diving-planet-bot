"""Reproducir dentro de PRE una conversación del golden con el bot REAL y ver qué juzga el juez de grounding (1-oct).

Para los rechazos que dependen de la conversación (historial, estado, contexto adicional), que `rag_piezas` y
`sonda_rag_turnos_pre` no ven: manda los turnos del diálogo, uno tras otro, a `supervisor.route_message` dentro del
contenedor `dp-pre-bot` (mismo código, base, modelos e interruptores que PRE; no pasa por Chatwoot ni guarda estado) y
espía `rag_agent.is_grounded`: por cada juicio guarda la respuesta, el veredicto, el motivo y el CONTEXTO ENTERO que vio
el juez. Repite el diálogo N veces. **Nunca usa el examen oculto.**

    python -m scripts.reproducir_juez_pre paquete-5-buceos-cop-refresh-y-hoteles --reps 5 --out <fichero.jsonl>
    python -m scripts.reproducir_juez_pre <dialogo> --dry          # solo enseña los turnos
    python -m scripts.reproducir_juez_pre <dialogo> --flag juez_privacidad_por_linea   # flag SOLO en ese proceso
    python -m scripts.reproducir_juez_pre <dialogo> --codigo-local --flag x          # con el código local, sin desplegar
    python -m scripts.reproducir_juez_pre <dialogo> --codigo-local --env RAG_ANSWER_MODEL=gpt-6-luna   # otro modelo

Coste: el de N conversaciones del bot (céntimos por conversación). La cuenta de OpenAI es la misma que la de PRE.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "docs/robustness/golden-set/golden-dialogues.json"

_REMOTO = r'''
import asyncio, json, time
from src.agents import rag_agent, supervisor
from src.config import settings
from src.flows.state import ConversationState
TURNOS, REPS = json.loads(TURNOS_JSON), N_REPS
for _f in FLAGS:
    setattr(settings, _f, True)
juicios = []
_orig = rag_agent.is_grounded
async def _spy(answer, context, lang="es"):
    ok, why = await _orig(answer, context, lang=lang)
    juicios.append({"ok": ok, "why": why[:800], "answer": answer, "context": context})
    return ok, why
rag_agent.is_grounded = _spy

async def main():
    for rep in range(REPS):
        st = ConversationState(conversation_id=f"repro-juez-{rep}")
        for i, msg in enumerate(TURNOS, 1):
            juicios.clear()
            t0 = time.perf_counter()
            try:
                reply = await supervisor.route_message(st, msg)
            except Exception as exc:  # noqa: BLE001
                reply = f"ERROR {type(exc).__name__}: {exc}"
            print(json.dumps({"rep": rep, "turn": i, "msg": msg, "reply": reply, "juicios": list(juicios),
                              "segundos": round(time.perf_counter() - t0, 2)},
                             ensure_ascii=False), flush=True)

asyncio.run(main())
'''


def turnos(dialogo: str) -> list[str]:
    dialogos = json.loads(GOLDEN.read_text(encoding="utf-8"))["dialogues"]
    d = next((x for x in dialogos if x["id"] == dialogo), None)
    if d is None:
        raise SystemExit(f"no existe el diálogo {dialogo}")
    if d.get("suite") == "oculto":
        raise SystemExit("ese diálogo es del EXAMEN OCULTO: no se mira para arreglar nada")
    if d.get("turns"):
        return d["turns"]
    # Los diálogos sin `turns` propios citan un caso de un lote (como en `run_synthetic_pre.golden_cases`).
    from scripts.run_synthetic_pre import load_batches

    por_tag = {tag: ts for casos in load_batches().values() for tag, ts in casos}
    return por_tag[d["source"]["tag"]]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dialogo", help="id del diálogo del golden (no del examen oculto)")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", help="JSONL de salida (una línea por turno y repetición)")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--flag", action="append", default=[], help="interruptor a encender SOLO en ese proceso (repetible)")
    ap.add_argument("--env", action="append", default=[], metavar="CLAVE=VALOR",
                    help="variable de entorno SOLO en ese proceso (repetible), p. ej. RAG_ANSWER_MODEL=gpt-6-luna")
    ap.add_argument("--codigo-local", action="store_true",
                    help="corre con el código LOCAL (sin desplegar) copiado dentro de dp-pre-bot; PRE no cambia")
    args = ap.parse_args()

    ts = turnos(args.dialogo)
    print(f"{args.dialogo}: {len(ts)} turnos × {args.reps} repeticiones")
    for i, t in enumerate(ts, 1):
        print(f"  {i}. {t}")
    if args.dry:
        return

    from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

    script = f"TURNOS_JSON = {json.dumps(ts, ensure_ascii=False)!r}\nN_REPS = {args.reps}\nFLAGS = {args.flag!r}\n{_REMOTO}"
    codigo = subir_codigo_local() if args.codigo_local else None
    entorno = dict(e.split("=", 1) for e in args.env)
    r = pre_ssh(docker_python(entorno, codigo_local=codigo), input_text=script, timeout=max(600, 240 * args.reps))
    filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
    out = Path(args.out) if args.out else ROOT / f"repro-{args.dialogo}.jsonl"
    out.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8")
    print(f"resultados: {len(filas)} turnos → {out}")
    for f in filas:
        rech = [j for j in f["juicios"] if not j["ok"]]
        marca = f"RECHAZOS {len(rech)}" if rech else "ok"
        print(f"  rep {f['rep']} turno {f['turn']}: juicios {len(f['juicios'])} · {marca}"
              + (f" · {rech[0]['why'][:140]}" if rech else ""))
    if len(filas) < len(ts) * args.reps:
        print("⚠️ faltan turnos; stderr de PRE:\n" + (r.stderr or "")[-2000:])


if __name__ == "__main__":
    main()
