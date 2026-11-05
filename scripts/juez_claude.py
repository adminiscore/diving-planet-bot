"""El juez del golden con Claude Code (la suscripción de quien lo lanza), en vez de gpt-5-mini por la API.

`scripts/judge_golden_set.py` hace una llamada POR CRITERIO y cada una lleva la referencia entera (~60.000 tokens): 268 llamadas y
17 millones de tokens por lado de una mini, ~1,1 $. Aquí, una llamada POR DIÁLOGO con todos sus criterios. Lo demás es lo de
siempre: las mismas instrucciones, referencia y comprobaciones por código (citas literales y «un fallo, un criterio», sin la
pregunta extra al modelo), y el mismo formato de resultados, así que `compara` y `summarize` sirven igual.

Cada llamada va aislada: sin herramientas, sin CLAUDE.md, memoria, hooks ni MCP (`--safe-mode`), sin guardar sesión, fuera del
repo y sin saber si es el lado A o el B. Se quitan del entorno las claves de API: con ellas `claude -p` facturaría a la API.
Las condiciones de Anthropic piden uso individual: cada persona, con su propia suscripción. Es una herramienta de pruebas; no va en
ningún flujo del producto.

    python -m scripts.juez_claude --run docs/robustness/synthetic-runs/X.jsonl --modelo opus [--esfuerzo medium] [--ids a,b]
    python -m scripts.juez_claude --calibrar --modelo opus      # contra las etiquetas de calibration/
    python -m scripts.juez_claude --charlas 6908,6909 --nombre s05d   # tanda de sparring: criterios generales y graves, a ciegas

El examen oculto no se juzga sin `--con-oculto`, y con él no se imprimen sus ids.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from scripts.judge_golden_set import (
    AUTO_CHECKS,
    GOLDEN_FILE,
    JUDGE_INSTRUCTIONS,
    REFERENCIA_POR_DEFECTO,
    RESULTS_DIR,
    check_evidence,
    counted_failures,
    criteria_for,
    discount_counted,
    is_general,
    latest_conversations,
    load_reference,
    parse_verdict,
    review_list,
    summarize,
    transcript,
)

CACHE = RESULTS_DIR / "juez-claude-cache.jsonl"
CHARLAS = Path("docs/robustness/g3/charlas")
# El criterio de Álvaro (#2716) para las tandas: quien las escribe también clasifica, así que este juicio es la segunda opinión.
CRITERIO_GRAVES = {
    "id": "sin-graves",
    "check": ("No hay ningún fallo GRAVE: el cliente no reserva mal ni se queda sin poder reservar. Es grave un importe, moneda, enlace o "
              "plan equivocado; una fecha u horario falso; un consejo inseguro; algo contra una política o decisión de la referencia; un "
              "callejón sin salida; o la misma pregunta por 3.ª vez. La fricción que no impide reservar y el estilo NO son graves."),
}
CALIBRACION = Path("docs/robustness/golden-set/calibration")
_CLAVES_FUERA = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE")
_CANDADO = threading.Lock()

FORMATO = """En este encargo recibes UNA conversacion y VARIOS criterios: juzgalos TODOS, cada uno por separado.

Para los criterios cuyo id empieza por "global:" (generales), NO apliques la regla UN FALLO, UN CRITERIO: no descartes nada porque otro criterio pudiera cubrirlo (el sistema descuenta despues lo que ya se cuenta en otro criterio). Revisa las respuestas del BOT UNA POR UNA, en orden, comparando cada una con lo que el cliente dijo hasta ese momento y con la REFERENCIA; no juzgues por la impresion de conjunto. Enumera en "problemas" CADA incumplimiento distinto de ese criterio (uno por hecho), cada uno con su evidencia literal; marca "no_cumple" si y solo si "problemas" no esta vacia.

Responde SOLO con JSON, sin texto alrededor ni bloque de codigo:
{"veredictos": [{"id": "<id del criterio>", "verdict": "cumple|no_cumple|no_aplica", "evidencia_bot": "..." o null, "evidencia_cliente": "..." o null, "motivo": "una o dos frases", "problemas": [{"evidencia_bot": "...", "evidencia_cliente": "..." o null, "motivo": "..."}]}]}
"problemas" solo en los criterios "global:". Un veredicto por cada criterio, con su id exacto."""


class LimiteDeUsoError(RuntimeError):
    """Se acabó el uso de la suscripción: parar, no seguir insistiendo."""


def instrucciones(reference: str) -> str:
    base = JUDGE_INSTRUCTIONS.rsplit("Responde SOLO con JSON", 1)[0].rstrip()
    return f"{base}\n\n{FORMATO}\n\nREFERENCIA:\n{reference}"


def mensaje_del_dialogo(dialogue: dict, records: list[dict], criterios: list[dict]) -> str:
    lineas = "\n".join(f"- {c['id']}: {c['check']}" for c in criterios)
    return (f"CONVERSACION (dialogo '{dialogue['id']}', categoria {dialogue['category']}):\n{transcript(records)}\n\n"
            f"CRITERIOS A JUZGAR:\n{lineas}")


def entorno() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _CLAVES_FUERA and not k.startswith(("CLAUDE_CODE_", "CLAUDE_AGENT"))}


def ejecutable() -> str:
    exe = os.environ.get("CLAUDE_CODE_EXECPATH") or shutil.which("claude")
    if not exe:
        raise SystemExit("No encuentro el CLI de Claude Code (`claude`).")
    return exe


# 5-nov (Álvaro, #3513): `opus` es un alias que depende de la versión de Claude Code: 2.1.126 da claude-opus-4-7 y 2.1.318, claude-opus-5-5. Con el
# modelo fijado, los juicios de cada uno se comparan; quien no llegue a él recibe un error, no otro juez sin saberlo. Cambiarlo obliga a rejuzgar la base.
MODELO_EXACTO = {"opus": "claude-opus-5-5"}


def modelo_exacto(modelo: str) -> str:
    return MODELO_EXACTO.get(modelo, modelo)


def llamar(exe: str, sistema: Path, modelo: str, esfuerzo: str, mensaje: str, cwd: str) -> tuple[list[dict], dict]:
    """Los veredictos de una llamada y su uso. Reintenta una vez si la respuesta no es JSON válido."""
    exacto = modelo_exacto(modelo)
    cmd = [exe, "-p", "--safe-mode", "--tools", "", "--no-session-persistence", "--system-prompt-file", str(sistema),
           "--model", exacto, "--effort", esfuerzo, "--output-format", "json"]
    ultimo = ""
    for _ in range(2):
        r = subprocess.run(cmd, input=mensaje, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=entorno(), cwd=cwd, timeout=600)
        try:
            salida = json.loads(r.stdout)
        except ValueError:
            ultimo = f"rc={r.returncode} {r.stdout[-200:]} {r.stderr[-200:]}"
            continue
        texto = str(salida.get("result") or "")
        if salida.get("is_error"):
            if re.search(r"limit|usage|quota", texto, re.I):
                raise LimiteDeUsoError(texto[:200])
            ultimo = texto[:300]
            continue
        limpio = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto.strip())
        try:
            veredictos = json.loads(limpio)["veredictos"]
        except (ValueError, KeyError, TypeError):
            ultimo = f"sin JSON: {texto[:200]}"
            continue
        reales = list(salida.get("modelUsage") or {})
        if modelo in MODELO_EXACTO and reales and exacto not in reales:
            raise RuntimeError(f"se pidió {exacto} y contestó {reales}: el juicio no se compararía con los demás")
        uso = salida.get("usage") or {}
        return veredictos, {"input": uso.get("input_tokens", 0), "cache_read": uso.get("cache_read_input_tokens", 0),
                            "cache_write": uso.get("cache_creation_input_tokens", 0), "output": uso.get("output_tokens", 0),
                            "lista_usd": salida.get("total_cost_usd") or 0.0, "segundos": (salida.get("duration_ms") or 0) / 1000}
    raise RuntimeError(f"el juez no devolvió veredictos: {ultimo}")


def cargar_cache() -> dict:
    if not CACHE.exists():
        return {}
    return {f["clave"]: f["veredictos"] for f in map(json.loads, CACHE.read_text(encoding="utf-8").splitlines()) if f}


def guardar_cache(clave: str, veredictos: list[dict]) -> None:
    with _CANDADO, CACHE.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"clave": clave, "veredictos": veredictos}, ensure_ascii=False) + "\n")


def juzgar_dialogo(dialogue, records, todos, ctx) -> tuple[list[dict], dict]:
    """Como `judge_golden_set.judge_criteria`: primero los concretos y luego los generales, con el descuento por código."""
    llm = [c for c in todos if not c.get("auto")]
    mensaje = mensaje_del_dialogo(dialogue, records, llm)
    clave = hashlib.sha256("\x1f".join([modelo_exacto(ctx["modelo"]), ctx["esfuerzo"], ctx["huella"], mensaje]).encode()).hexdigest()
    uso: dict = {}
    crudos = None if ctx["cache"] is None else ctx["cache"].get(clave)
    if crudos is None:
        crudos, uso = llamar(ctx["exe"], ctx["sistema"], ctx["modelo"], ctx["esfuerzo"], mensaje, ctx["cwd"])
        guardar_cache(clave, crudos)
    por_id = {str(v.get("id")): v for v in crudos if isinstance(v, dict)}
    por = f"claude-{ctx['modelo']}"

    def uno(c: dict) -> dict:
        if c.get("auto"):
            return {"id": c["id"], **AUTO_CHECKS[c["auto"]](records), "by": "auto"}
        crudo = por_id.get(c["id"])
        if crudo is None:
            return {"id": c["id"], "verdict": "error", "reason": "el juez no dio veredicto de este criterio", "by": por}
        return {"id": c["id"], **check_evidence(parse_verdict(json.dumps(crudo, ensure_ascii=False)), records), "by": por}

    hechos: dict[str, dict] = {}
    for c in todos:
        if not is_general(c):
            hechos[c["id"]] = uno(c)
    contados = counted_failures(todos, hechos)
    for c in todos:
        if is_general(c):
            hechos[c["id"]] = discount_counted(uno(c), contados, records, None)
            contados = contados + counted_failures([c], hechos, generals=True)
    return [hechos[c["id"]] for c in todos], uso


def preparar(args) -> dict:
    reference = load_reference(REFERENCIA_POR_DEFECTO)
    texto = instrucciones(reference)
    cwd = tempfile.mkdtemp(prefix="juez-claude-")
    sistema = Path(cwd) / "sistema.txt"
    sistema.write_text(texto, encoding="utf-8", newline="\n")
    return {"exe": ejecutable(), "sistema": sistema, "modelo": args.modelo, "esfuerzo": args.esfuerzo, "cwd": cwd,
            "huella": hashlib.sha256(texto.encode()).hexdigest(), "cache": None if args.no_cache else cargar_cache()}


def en_paralelo(tareas, funcion, paralelo: int) -> tuple[dict, Counter]:
    """{id: resultado} y el uso sumado; si se acaba la suscripción, para y lo dice."""
    hechos, total = {}, Counter()
    tareas = list(tareas)
    if tareas:  # la primera sola: deja la referencia en la caché de prompts y las demás la leen en vez de volver a escribirla
        try:
            clave, resultado, uso = funcion(tareas[0])
        except LimiteDeUsoError as exc:
            raise SystemExit(f"Se acabó el uso de la suscripción: {exc}.") from exc
        hechos[clave] = resultado
        total.update(uso)
    with ThreadPoolExecutor(max_workers=max(1, paralelo)) as pool:
        futuros = {pool.submit(funcion, t): t for t in tareas[1:]}
        try:
            for futuro in as_completed(futuros):
                clave, resultado, uso = futuro.result()
                hechos[clave] = resultado
                total.update({k: v for k, v in uso.items()})
        except LimiteDeUsoError as exc:
            pool.shutdown(wait=False, cancel_futures=True)
            raise SystemExit(f"Se acabó el uso de la suscripción: {exc}. Lo ya juzgado queda en la caché.") from exc
    return hechos, total


def juzgar_ronda(args) -> int:
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    runs = latest_conversations(args.run)
    elegidos = set(args.ids.split(",")) if args.ids else None
    todo = [d for d in golden["dialogues"] if runs.get(d["id"]) and (elegidos is None or d["id"] in elegidos)
            and (args.con_oculto or d.get("suite") != "oculto")]
    ctx = preparar(args)
    t0 = time.perf_counter()

    def tarea(d):
        criterios, uso = juzgar_dialogo(d, runs[d["id"]], criteria_for(d, golden["global_criteria"]), ctx)
        malos = [f"{c['id']}={c['verdict']}" for c in criterios if c["verdict"] not in ("cumple", "no_aplica")]
        if d.get("suite") != "oculto":
            print(f"{d['id']}: {'OK' if not malos else ', '.join(malos)}", flush=True)
        return d["id"], {"id": d["id"], "category": d["category"], "conv": runs[d["id"]][0]["conv"], "criteria": criterios}, uso

    hechos, uso = en_paralelo(todo, tarea, args.paralelo)
    results = [hechos[d["id"]] for d in todo]
    summary = summarize(results)
    report = {"judged_at": datetime.now(UTC).isoformat(timespec="seconds"), "run_file": args.run.replace("\\", "/"),
              "golden_version": golden["version"], "model": f"claude-{args.modelo}", "modelo_exacto": modelo_exacto(args.modelo), "effort": args.esfuerzo,
              "referencia": REFERENCIA_POR_DEFECTO, "usage": dict(uso), "cost_usd": 0.0, "summary": summary,
              "minutos": round((time.perf_counter() - t0) / 60, 1),
              "human_review": review_list(results, 5, Path(args.run).stem), "dialogues": results}
    out = RESULTS_DIR / f"{Path(args.run).stem}__claude-{args.modelo}-{args.esfuerzo}{args.sufijo}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"\nCriterios cumplidos: {summary['criteria_pass_pct']} % ({summary['criteria_failed']} fallos de {summary['criteria_judged']}); "
          f"a revisar: {summary['to_review']}; errores: {summary['errors']}; dialogos sin fallos: {summary['dialogues_passed']}/{summary['dialogues']}; "
          f"{report['minutos']} min; uso: {dict(uso)}\nResultado: {out}", flush=True)
    return 0


def juzgar_charlas(args) -> int:
    """Una tanda de sparring (`scripts/charla_pre`): no tiene criterios propios, así que van los generales y el de graves. A ciegas: el
    juez no sabe qué clasificó quien la escribió."""
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    tareas = []
    for conv in args.charlas.split(","):
        filas = [json.loads(ln) for ln in (CHARLAS / f"{conv.strip()}.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
        records = [{**f, "turn": f["turno"], "tag": conv.strip()} for f in filas]
        tareas.append(({"id": conv.strip(), "category": "sparring", "criteria": [CRITERIO_GRAVES]}, records))
    ctx = preparar(args)

    def tarea(par):
        dialogo, records = par
        criterios, uso = juzgar_dialogo(dialogo, records, criteria_for(dialogo, golden["global_criteria"]), ctx)
        return dialogo["id"], {"id": dialogo["id"], "category": "sparring", "conv": int(dialogo["id"]), "criteria": criterios}, uso

    hechos, uso = en_paralelo(tareas, tarea, args.paralelo)
    results = [hechos[d["id"]] for d, _ in tareas]
    out = RESULTS_DIR / f"tanda-{args.nombre}__claude-{args.modelo}-{args.esfuerzo}{args.sufijo}.json"
    out.write_text(json.dumps({"tanda": args.nombre, "model": f"claude-{args.modelo}", "effort": args.esfuerzo, "usage": dict(uso),
                               "dialogues": results}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    graves = [d for d in results for c in d["criteria"] if c["id"] == "sin-graves" and c["verdict"] != "cumple"]
    print(f"Clientes con grave según el juez: {len(graves)} de {len(results)}")
    for d in results:
        for c in d["criteria"]:
            if c["verdict"] not in ("cumple", "no_aplica"):
                print(f"- {d['id']} / {c['id']}: {(c.get('evidencia_bot') or '')[:180]} | {(c.get('reason') or '')[:260]}")
    print(f"Resultado: {out}")
    return 0


def calibrar(args) -> int:
    """Contra las etiquetas de calibration/: las mismas conversaciones y la misma tabla que `scripts.calibrate_judge`."""
    from scripts.calibrate_judge import consolidate, score

    calib = json.loads((CALIBRACION / "items.json").read_text(encoding="utf-8"))
    etiquetas = [e for nombre in ("labels-claude.json", "labels-gadea.json")
                 for e in json.loads((CALIBRACION / nombre).read_text(encoding="utf-8"))]
    referencia, acuerdo = consolidate(etiquetas)
    runs = latest_conversations(calib["run_file"])
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    dialogos = {d["id"]: d for d in golden["dialogues"]}
    ctx = preparar(args)

    def tarea(item):
        d = dialogos[item["dialogue"]]
        criterios, uso = juzgar_dialogo(d, runs[item["dialogue"]], criteria_for(d, golden["global_criteria"]), ctx)
        return item["dialogue"], criterios, uso

    hechos, uso = en_paralelo(calib["items"], tarea, args.paralelo)
    pares = {"tune": [], "holdout": []}
    filas = []
    for item in calib["items"]:
        for c in hechos[item["dialogue"]]:
            humano = referencia.get((item["dialogue"], c["id"]))
            if humano is None:
                continue
            pares[item["split"]].append((humano, c["verdict"]))
            filas.append({"dialogue": item["dialogue"], "criterion": c["id"], "split": item["split"], "human": humano,
                          "judge": c["verdict"], "reason": c.get("reason"), "evidencia_bot": c.get("evidencia_bot")})
    salida = {"modelo": f"claude-{args.modelo}", "esfuerzo": args.esfuerzo, "human_agreement": acuerdo, "tune": score(pares["tune"]),
              "holdout": score(pares["holdout"]), "all": score(pares["tune"] + pares["holdout"]), "usage": dict(uso), "rows": filas}
    out = CALIBRACION / f"results-{datetime.now(UTC):%Y-%m-%d-%H%M}-claude-{args.modelo}-{args.esfuerzo}.json"
    out.write_text(json.dumps(salida, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: salida[k] for k in ("modelo", "esfuerzo", "tune", "holdout", "all", "usage")}, ensure_ascii=False))
    print(f"Resultado: {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", help="JSONL de scripts.ronda_local_pre o run_synthetic_pre --sample golden")
    parser.add_argument("--calibrar", action="store_true", help="medir contra las etiquetas de calibration/")
    parser.add_argument("--charlas", help="conversaciones de una tanda de sparring, separadas por comas")
    parser.add_argument("--nombre", default="tanda", help="con --charlas: el nombre de la tanda")
    parser.add_argument("--modelo", default="opus", help="opus (fijado en MODELO_EXACTO), sonnet, haiku")
    parser.add_argument("--esfuerzo", default="medium")
    parser.add_argument("--ids", help="solo estos diálogos, separados por comas")
    parser.add_argument("--paralelo", type=int, default=3)
    parser.add_argument("--no-cache", action="store_true", help="juzgar de nuevo aunque esté en la caché")
    parser.add_argument("--sufijo", default="", help="para no pisar otra pasada del mismo modelo")
    parser.add_argument("--con-oculto", action="store_true", help="incluye el examen oculto (una sola vez, en VAL)")
    args = parser.parse_args(argv)
    if args.calibrar:
        return calibrar(args)
    if args.charlas:
        return juzgar_charlas(args)
    if not args.run:
        parser.error("falta --run, --calibrar o --charlas")
    return juzgar_ronda(args)


if __name__ == "__main__":
    sys.exit(main())
