"""Reproducir dentro de PRE una conversación del golden con el bot REAL y ver qué juzga el juez de grounding (1-oct).

Para los rechazos que dependen de la conversación (historial, estado, contexto adicional), que `rag_piezas` y
`sonda_rag_turnos_pre` no ven: manda los turnos del diálogo, uno tras otro, a `supervisor.route_message` dentro del
contenedor `dp-pre-bot` (mismo código, base, modelos e interruptores que PRE; no pasa por Chatwoot ni guarda estado) y
espía `rag_agent.is_grounded`: por cada juicio guarda la respuesta, el veredicto, el motivo y el CONTEXTO ENTERO que vio
el juez. Repite el diálogo N veces. **Nunca usa el examen oculto.**

    python -m scripts.reproducir_juez_pre paquete-5-buceos-cop-refresh-y-hoteles --reps 5 --out <fichero.jsonl>
    python -m scripts.reproducir_juez_pre <dialogo> --dry          # solo enseña los turnos
    python -m scripts.reproducir_juez_pre <dialogo> --flag <flag>   # flag SOLO en ese proceso
    python -m scripts.reproducir_juez_pre <dialogo> --codigo-local --flag x          # con el código local, sin desplegar
    python -m scripts.reproducir_juez_pre <dialogo> --hasta 2 --reps 8               # solo los 2 primeros turnos
    python -m scripts.reproducir_juez_pre <dialogo> --codigo-local --env RAG_ANSWER_MODEL=gpt-6-luna   # otro modelo
    python -m scripts.reproducir_juez_pre --banco docs/robustness/gen/dialogos-gen1.json --reps 1   # banco propio entero

gen-1 (20-oct): `--banco` corre diálogos PROPIOS (un JSON {"dialogos": [{"id", "turnos"}]}) en una sola sesión, y cada
turno guarda también lo que contestó el RAG (`rag`: consulta y respuesta de cada `supervisor.rag_answer`). Así se ve si
un dato que falta en la respuesta al cliente lo dio el RAG y se perdió después, o si el RAG ni se llamó.

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
DIALOGOS, REPS = json.loads(DIALOGOS_JSON), N_REPS
for _f in FLAGS:  # "no:X" APAGA X solo en este proceso (17-oct: medir con PRE en la rama de otro)
    setattr(settings, _f.removeprefix("no:"), not _f.startswith("no:"))
juicios = []
_orig = rag_agent.is_grounded
async def _spy(answer, context, lang="es"):
    ok, why = await _orig(answer, context, lang=lang)
    juicios.append({"ok": ok, "why": why[:800], "answer": answer, "context": context})
    return ok, why
rag_agent.is_grounded = _spy
# gen-1 (20-oct): lo que contestó el RAG en el turno, para compararlo con lo que llegó al cliente.
rags = []
_orig_rag = supervisor.rag_answer
async def _spy_rag(query, *a, **kw):
    answer = await _orig_rag(query, *a, **kw)
    rags.append({"query": query, "answer": answer})
    return answer
supervisor.rag_answer = _spy_rag
# 9-oct (s4-28): el estado de la reserva y las líneas del flujo de cada turno, para ver QUÉ camino puso un dato
# (p. ej. el extractor rellenando `location` con la pregunta del origen pendiente).
import logging
_TRAZA = []
_METRICAS = []  # 28-oct (CALN-2, gasto del lector del grupo): el [TURN_METRICS] entero del turno (llamadas, tokens, usd)
class _Traza(logging.Handler):
    def emit(self, rec):
        m = rec.getMessage()
        if "[TURN_METRICS] " in m:
            try:
                _METRICAS.append(json.loads(m.split("[TURN_METRICS] ", 1)[1]))
            except ValueError:
                pass
        if any(t in m for t in ("[EXTRACT]", "[LLM_EXTRACTOR]", "[CORE]", "[INTENT]", "[ROUTER]", "[AVISOS]", "[HECHOS]", "[INFO]",
                                    "[RAG][GROUNDING]", "[RAG][LAT5]")):  # lat-5: el revisor del RAG
            _TRAZA.append(m[:400])
logging.getLogger().addHandler(_Traza())
logging.getLogger().setLevel(logging.INFO)
_CAMPOS = ("location", "detected_location", "core_pending_slot", "pregunta_precio_pendiente", "detected_activity",
           "selected_service", "detected_group_size", "detected_group_allocation", "is_certified", "is_colombian",
           "quiere_bucear", "suggested_activity",
           # lat-11 T6c (26-oct): la isla y el hotel, para medir los falsos «está en las islas».
           "island", "detected_island", "hotel", "detected_hotel",
           # DEUDA-EXT (26-oct): el repaso y el acompañante que se suma.
           "refresher_interested", "last_dive_over_2_years", "pending_companion_activity", "needs_companion_activity",
           # gen-3b (21-oct): si el turno pasó el caso a una persona (y por qué), para medir "pasa directo" frente a
           # "ofrece el pase".
           "pending_escalation_reason",
           # CALN-2 (27-oct): el grupo entero, para el banco de grupos (scripts/puntua_banco_grupo.py).
           "detected_ages", "pending_undecided_qty", "acompanante_sin_certificar", "acompanante_certificado_inactivo",
           "pending_companion_in_group")

async def main():
    for dialogo, turnos, rep in [(d, ts, r) for d, ts in DIALOGOS for r in range(REPS)]:
        st = ConversationState(conversation_id=f"repro-juez-{dialogo}-{rep}")
        for i, msg in enumerate(turnos, 1):
            juicios.clear()
            rags.clear()
            _TRAZA.clear()
            _METRICAS.clear()
            t0 = time.perf_counter()
            try:
                reply = await supervisor.route_message(st, msg)
            except Exception as exc:  # noqa: BLE001
                reply = f"ERROR {type(exc).__name__}: {exc}"
            estado = {c: getattr(st, c, None) for c in _CAMPOS if getattr(st, c, None) not in (None, "", [], {})}
            print(json.dumps({"dialogo": dialogo, "rep": rep, "turn": i, "msg": msg, "reply": reply,
                              "rag": list(rags), "juicios": list(juicios),
                              "segundos": round(time.perf_counter() - t0, 2), "estado": estado,
                              "traza": list(_TRAZA), "metricas": list(_METRICAS)},
                             ensure_ascii=False, default=str), flush=True)

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
    ap.add_argument("dialogo", nargs="?", help="id del diálogo del golden (no del examen oculto) o del --banco")
    ap.add_argument("--banco", help="JSON propio {'dialogos': [{'id', 'turnos'}]}; sin `dialogo`, corre todos")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", help="JSONL de salida (una línea por turno y repetición)")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--flag", action="append", default=[], help="interruptor a encender SOLO en ese proceso (repetible)")
    ap.add_argument("--env", action="append", default=[], metavar="CLAVE=VALOR",
                    help="variable de entorno SOLO en ese proceso (repetible), p. ej. RAG_ANSWER_MODEL=gpt-6-luna")
    ap.add_argument("--hasta", type=int, help="solo los N primeros turnos (para repetir mucho un turno concreto)")
    ap.add_argument("--codigo-local", action="store_true",
                    help="corre con el código LOCAL (sin desplegar) copiado dentro de dp-pre-bot; PRE no cambia")
    args = ap.parse_args()

    if args.banco:
        banco = json.loads(Path(args.banco).read_text(encoding="utf-8"))["dialogos"]
        dialogos = [(d["id"], d["turnos"]) for d in banco if args.dialogo in (None, d["id"])]
        if not dialogos:
            raise SystemExit(f"no existe el diálogo {args.dialogo} en {args.banco}")
    elif args.dialogo:
        dialogos = [(args.dialogo, turnos(args.dialogo))]
    else:
        raise SystemExit("falta el diálogo o --banco")
    dialogos = [(d, ts[: args.hasta or None]) for d, ts in dialogos]
    total = sum(len(ts) for _, ts in dialogos) * args.reps
    for d, ts in dialogos:
        print(f"{d}: {len(ts)} turnos × {args.reps} repeticiones")
        for i, t in enumerate(ts, 1):
            print(f"  {i}. {t}")
    if args.dry:
        return

    from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

    script = (f"DIALOGOS_JSON = {json.dumps(dialogos, ensure_ascii=False)!r}\nN_REPS = {args.reps}\n"
              f"FLAGS = {args.flag!r}\n{_REMOTO}")
    codigo = subir_codigo_local() if args.codigo_local else None
    entorno = dict(e.split("=", 1) for e in args.env)
    r = pre_ssh(docker_python(entorno, codigo_local=codigo), input_text=script, timeout=max(600, 60 * total))
    filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
    nombre = args.dialogo or Path(args.banco).stem
    out = Path(args.out) if args.out else ROOT / f"repro-{nombre}.jsonl"
    out.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8")
    print(f"resultados: {len(filas)} turnos → {out}")
    for f in filas:
        rech = [j for j in f["juicios"] if not j["ok"]]
        marca = f"RECHAZOS {len(rech)}" if rech else "ok"
        print(f"  {f['dialogo']} rep {f['rep']} turno {f['turn']}: rag {len(f['rag'])} · juicios {len(f['juicios'])}"
              f" · {marca}" + (f" · {rech[0]['why'][:140]}" if rech else ""))
    if len(filas) < total:
        print("⚠️ faltan turnos; stderr de PRE:\n" + (r.stderr or "")[-2000:])


if __name__ == "__main__":
    main()
