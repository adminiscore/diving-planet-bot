"""GEN-0 (21-oct, prioridad 1 de Gadea): ronda core SIN DESPLEGAR, para medir en paralelo.

`run_synthetic_pre` manda los diálogos por Chatwoot al bot DESPLEGADO: solo hay uno, así que las rondas iban de una en
una y nadie subía mientras otro medía. Este script corre la misma muestra DENTRO del contenedor `dp-pre-bot` (base,
claves y modelos de PRE) con el código desplegado o con el LOCAL de cada uno (`--codigo-local`, su carpeta
`/tmp/codigo-local-<usuario>`) y sus flags (`--flag`, `--env`), y escribe el MISMO jsonl que `run_synthetic_pre`, que se
juzga con `judge_golden_set --run`. Varias personas, y A y B, pueden correr a la vez.

Fiel al camino del webhook (`channels/chatwoot.handle_message` + `finalize_chatwoot_delivery`):
- estado nuevo como el webhook (`ConversationState(conversation_id, language=settings.default_language)`) y, entre
  turnos, guardado y recargado como en Redis (`serialize_state` / `deserialize_state`: los atributos con "_" se pierden);
- tras cada respuesta, lo que hace la entrega: la nota privada se borra y el motivo del pase se limpia (en PRE el pase
  a Chatwoot sale bien);
- la respuesta se parte por `<<<SPLIT>>>` y se aplica `a_whatsapp` si está `formato_whatsapp`, y se une con "\\n---\\n"
  como hace `run_synthetic_pre` con las burbujas.
No pasa por Chatwoot (ni el canal ni sus tiempos): `client_latency_s` es lo que tarda `route_message`.

    # base A y B a la vez, con el mismo código local y distinto flag
    python -m scripts.ronda_local_pre --name x-A --sample core --codigo-local --flag no:mi_flag
    python -m scripts.ronda_local_pre --name x-B --sample core --codigo-local --flag mi_flag
    python -m scripts.judge_golden_set --run docs/robustness/synthetic-runs/<fecha>-x-B.jsonl
    # el código desplegado en PRE, para comparar con una ronda por Chatwoot
    python -m scripts.ronda_local_pre --name x-local --sample core

Los flags que se leen al importar (p. ej. `dieta_no_es_medica`, el tool del enrutador) van con `--env CLAVE=valor`, no
con `--flag`. Coste: el de una ronda normal (el bot en PRE) más nada; la cuenta de OpenAI es la de PRE.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from scripts import run_synthetic_pre
from scripts.run_synthetic_pre import load_batches, select_cases

RUNS_DIR = Path("docs/robustness/synthetic-runs")

_REMOTO = r'''
import asyncio, json, time
from datetime import UTC, datetime
from src.agents import supervisor
from src.config import settings
from src.flows.state import MESSAGE_SPLIT, ConversationState
from src.state_store import deserialize_state, serialize_state
CASOS, PARALELO, BASE_ID = json.loads(CASOS_JSON), N_PARALELO, CONV_BASE
for _f in FLAGS:  # "no:X" APAGA X solo en este proceso
    setattr(settings, _f.removeprefix("no:"), not _f.startswith("no:"))
if METRICAS:  # MEJ-5: la línea [TURN_METRICS] de cada turno (llamadas, modelos, tokens) sale por stdout con «M »
    import logging

    class _Metricas(logging.Handler):
        def emit(self, rec):
            m = rec.getMessage()
            if m.startswith("[TURN_METRICS] "):
                print("M " + m.split(" ", 1)[1], flush=True)

    _lg = logging.getLogger("uvicorn.error")
    _lg.addHandler(_Metricas())
    _lg.setLevel(logging.INFO)

def _entrega(st, respuesta):
    """Lo que hace `finalize_chatwoot_delivery` con el estado y el texto (sin mandar nada)."""
    if st.pending_note:
        st.pending_note = None
    if st.pending_escalation_reason:
        st.pending_escalation_reason = None  # en PRE el pase a Chatwoot sale bien
    if not respuesta:
        return None, 0
    partes = [p.strip() for p in respuesta.split(MESSAGE_SPLIT) if p.strip()] if MESSAGE_SPLIT in respuesta else [respuesta]
    if settings.formato_whatsapp:
        from src.channels.formato import a_whatsapp
        partes = [a_whatsapp(p) for p in partes]
    return "\n---\n".join(partes), len(partes)

async def _dialogo(sem, n, batch, tag, turnos):
    async with sem:
        conv = BASE_ID + n
        st = ConversationState(conversation_id=str(conv), language=settings.default_language)
        for i, msg in enumerate(turnos, 1):
            st = deserialize_state(serialize_state(st), str(conv))  # como Redis entre turnos
            t0 = time.perf_counter()
            try:
                respuesta = await supervisor.route_message(st, msg)
                error = None
            except Exception as exc:  # noqa: BLE001 — un turno roto se apunta y sigue la tanda
                respuesta, error = None, f"{type(exc).__name__}: {exc}"
            reply, burbujas = _entrega(st, respuesta)
            print(json.dumps({"at": datetime.now(UTC).isoformat(timespec="seconds"), "batch": batch, "tag": tag,
                              "conv": conv, "turn": i, "turns": len(turnos), "msg": msg, "reply": reply,
                              "bubbles": burbujas, "client_latency_s": round(time.perf_counter() - t0, 1),
                              "via": "local", "error": error}, ensure_ascii=False), flush=True)
            if reply is None:
                break

async def main():
    sem = asyncio.Semaphore(PARALELO)
    await asyncio.gather(*(_dialogo(sem, n, b, t, ts) for n, (b, t, ts) in enumerate(CASOS, 1)))

asyncio.run(main())
'''


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--name", required=True, help="nombre corto (el fichero es <fecha UTC>-<name>.jsonl)")
    ap.add_argument("--sample", choices=["core", "golden", "rapida"], default="core")
    ap.add_argument("--ids", help="solo estas etiquetas, separadas por coma")
    ap.add_argument("--codigo-local", action="store_true", help="el código LOCAL (sin desplegar) en tu carpeta del contenedor")
    ap.add_argument("--flag", action="append", default=[], help="interruptor SOLO en este proceso; 'no:X' lo apaga (repetible)")
    ap.add_argument("--env", action="append", default=[], metavar="CLAVE=VALOR",
                    help="variable de entorno SOLO en este proceso (para lo que se lee al importar); repetible")
    ap.add_argument("--paralelo", type=int, default=4, help="diálogos a la vez dentro del contenedor (por defecto 4)")
    ap.add_argument("--golden", help="con --sample golden: otro fichero de diálogos con el mismo formato (los exámenes "
                                     "ocultos G9/G10: se pasan UNA sola vez y nadie los abre)")
    ap.add_argument("--metricas", action="store_true",
                    help="guarda también las métricas de cada turno (llamadas, modelos y tokens) en <jsonl>.metricas")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args(argv)

    if args.golden:
        run_synthetic_pre.GOLDEN_FILE = Path(args.golden)
    casos = select_cases(load_batches(), args.sample, None)
    if args.ids:
        quiero = set(args.ids.split(","))
        casos = [c for c in casos if c[1] in quiero]
    turnos = sum(len(t) for _, _, t in casos)
    out = RUNS_DIR / f"{datetime.now(UTC):%Y-%m-%d}-{args.name}.jsonl"
    print(f"{len(casos)} conversaciones, {turnos} turnos → {out}", flush=True)
    if args.dry:
        return 0
    if out.exists():
        print(f"{out} ya existe: elige otro --name (el jsonl de una ronda no se mezcla con otra).", file=sys.stderr)
        return 2

    from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

    conv_base = int(datetime.now(UTC).timestamp()) * 1000  # ids únicos: el juez se queda con el conv más alto por etiqueta
    script = (f"CASOS_JSON = {json.dumps(casos, ensure_ascii=False)!r}\nN_PARALELO = {args.paralelo}\n"
              f"CONV_BASE = {conv_base}\nFLAGS = {args.flag!r}\nMETRICAS = {args.metricas!r}\n{_REMOTO}")
    entorno = dict(e.split("=", 1) for e in args.env)
    codigo = subir_codigo_local() if args.codigo_local else None
    r = pre_ssh(docker_python(entorno, codigo), input_text=script,
                timeout=max(900, 25 * turnos // max(1, args.paralelo) + 600))
    filas = [ln for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
    out.write_text("".join(ln + "\n" for ln in filas), encoding="utf-8")
    if args.metricas:
        metricas = [ln[2:] for ln in (r.stdout or "").splitlines() if ln.startswith("M {")]
        out.with_suffix(".metricas").write_text("".join(ln + "\n" for ln in metricas), encoding="utf-8")
        print(f"métricas de {len(metricas)} turnos → {out.with_suffix('.metricas')}", flush=True)
        # 28-oct: sin saldo de OpenAI, Luna fallaba y escribía el respaldo (DeepSeek); 0 turnos sin respuesta y la ronda
        # parecía buena (caln4-B: 218 de 465 turnos con errores de LLM). Una ronda así no mide el bot de verdad.
        con_errores = sum(1 for ln in metricas if json.loads(ln).get("llm_errores"))
        if con_errores:
            print(f"⚠️ {con_errores}/{len(metricas)} turnos con errores de LLM (contestó un respaldo): "
                  "mira el saldo y los modelos antes de juzgar", flush=True)
        if con_errores > 0.05 * len(metricas):
            return 3
    sin = sum(1 for ln in filas if json.loads(ln)["reply"] is None)
    print(f"FIN {out}: {len(filas)}/{turnos} turnos, {sin} sin respuesta", flush=True)
    if len(filas) < turnos:
        print("⚠️ faltan turnos; stderr de PRE:\n" + (r.stderr or "")[-2000:], flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
