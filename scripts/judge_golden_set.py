"""LLM-juez end-to-end del golden-set (plan maestro, M0 m0-3).

Lee una ejecucion de `scripts.run_synthetic_pre --sample golden` (la conversacion REAL que
dio PRE), y para cada dialogo del golden-set pide a un modelo juez que marque cada criterio
(globales + propios) como `cumple`, `no_cumple` o `no_aplica`, con el motivo.

El juez no recibe los hechos escritos en los criterios: recibe la referencia del negocio
desde el repo (precios, politicas, descuentos, disponibilidad, escalado y un extracto de
actividades), asi que un cambio de catalogo no obliga a tocar el golden-set. La referencia
va primero y es identica en todas las llamadas, para aprovechar la cache de prompts de
OpenAI.

Uso (una llamada al juez por dialogo, en serie):

    ENV_FILE=.env.dev python -m scripts.judge_golden_set \\
        --run docs/robustness/synthetic-runs/2026-09-17-golden.jsonl [--model gpt-4.1] [--snapshot foto.json]

Escribe `docs/robustness/golden-set/results/<nombre de la ejecucion>.json` con el veredicto
por criterio y el resumen. Con `--snapshot` anade el bloque `quality` a una foto de
`scripts.langfuse_snapshot`, para que la calidad salga en la linea temporal junto a la latencia.
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from scripts.langfuse_snapshot import _env

GOLDEN_FILE = Path("docs/robustness/golden-set/golden-dialogues.json")
RESULTS_DIR = Path("docs/robustness/golden-set/results")
KB_DIR = Path("data/knowledge_base")
VERDICTS = ("cumple", "no_cumple", "no_aplica")

JUDGE_INSTRUCTIONS = """Eres un evaluador estricto de conversaciones de Coral, el asistente de reservas de Diving Planet (buceo en las Islas del Rosario, Colombia).

Recibes:
1. REFERENCIA: los datos oficiales del negocio (precios 2026, politicas, descuentos, disponibilidad, reglas de escalado a humano y actividades con edades). Es la unica fuente de verdad.
2. Una CONVERSACION real entre un cliente y el bot.
3. Una lista de CRITERIOS.

Para cada criterio decide:
- "cumple": la conversacion lo cumple.
- "no_cumple": lo incumple. Un precio, edad, horario, politica o descuento que no coincide con la REFERENCIA es un incumplimiento, aunque suene razonable.
- "no_aplica": la conversacion no llega a la situacion que el criterio evalua (por ejemplo, el bot nunca da un precio y el criterio es sobre el precio). No uses "no_aplica" para disculpar un fallo: si el bot debia llegar a esa situacion y no llego, es "no_cumple".

Reglas:
- Juzga solo lo que dice el BOT; el cliente puede decir cosas falsas.
- Los precios "reservando online" de la referencia son los validos para el bot. Un precio redondeado a la unidad (126 USD por 125,57) es correcto.
- Un "saludo" es presentarse o decir hola/hi. Exclamaciones de enlace como "¡Genial!", "¡Buena noticia!" o "¡Con gusto te ayudo!" no son un segundo saludo.
- Una "repregunta" es volver a pedir un dato que el cliente YA dio. Repetir una pregunta que el cliente todavia no ha contestado no lo es (aunque puede incumplir otro criterio si ignora lo que el cliente pidio).
- Ofrecer que un asesor contacte al cliente cuenta como pasar a un asesor.
- Motivo breve (una o dos frases), citando lo que dijo el bot cuando incumple.
- Responde SOLO con JSON: {"criteria": [{"id": "...", "verdict": "cumple|no_cumple|no_aplica", "reason": "..."}]}, con TODOS los ids recibidos y ninguno mas."""


def latest_conversations(run_file: str) -> dict[str, list[dict]]:
    """Turnos por dialogo, quedandose con la ULTIMA conversacion de cada uno: relanzar solo
    algunos dialogos (`--ids`) anade al mismo fichero sin pisar los demas."""
    by_conv: dict[tuple[str, int], list[dict]] = defaultdict(list)
    with open(run_file, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rec = json.loads(line)
                by_conv[(rec["tag"], rec["conv"])].append(rec)
    latest: dict[str, int] = {}
    for tag, conv in by_conv:
        latest[tag] = max(conv, latest.get(tag, conv))
    return {tag: by_conv[(tag, conv)] for tag, conv in latest.items()}


def load_reference() -> str:
    """Referencia del negocio para el juez, desde los ficheros de la base de conocimiento."""
    parts = []
    for name in ("pricing", "policies", "discounts", "availability", "escalation_rules"):
        data = json.loads((KB_DIR / f"{name}.json").read_text(encoding="utf-8-sig"))
        parts.append(f"### {name}.json\n{json.dumps(data, ensure_ascii=False, separators=(',', ':'))}")
    activities = json.loads((KB_DIR / "activities.json").read_text(encoding="utf-8-sig"))["activities"]
    compact = [{k: a.get(k) for k in ("id", "label", "requires_certification", "min_age", "max_age")} for a in activities]
    parts.append(f"### activities.json (extracto)\n{json.dumps(compact, ensure_ascii=False, separators=(',', ':'))}")
    return "\n\n".join(parts)


def transcript(records: list[dict]) -> str:
    lines = []
    for r in sorted(records, key=lambda r: r["turn"]):
        lines.append(f"CLIENTE: {r['msg']}")
        if r.get("reply") is None:
            lines.append("BOT: [sin respuesta en el tiempo de espera]")
        else:
            bubbles = r["reply"].split("\n---\n")
            lines += [f"BOT: {b}" for b in bubbles]
    return "\n".join(lines)


def criteria_for(dialogue: dict, global_criteria: list[dict]) -> list[dict]:
    own = [{"id": c["id"], "check": c["check"]} for c in dialogue["criteria"]]
    own_ids = {c["id"] for c in own}
    # Un criterio propio con el mismo id que uno global lo concreta: manda el propio.
    return [{"id": f"global:{c['id']}", "check": c["check"]} for c in global_criteria if c["id"] not in own_ids] + own


def parse_verdicts(raw: str, expected_ids: list[str]) -> list[dict]:
    """Valida la respuesta del juez: todos los ids, veredictos conocidos. Lo que falte o
    venga mal se marca `error` (cuenta aparte, nunca como cumple)."""
    try:
        got = {c["id"]: c for c in json.loads(raw).get("criteria", []) if isinstance(c, dict) and "id" in c}
    except (json.JSONDecodeError, AttributeError):
        got = {}
    out = []
    for cid in expected_ids:
        c = got.get(cid)
        if c and c.get("verdict") in VERDICTS:
            out.append({"id": cid, "verdict": c["verdict"], "reason": str(c.get("reason", ""))})
        else:
            out.append({"id": cid, "verdict": "error", "reason": "el juez no devolvio un veredicto valido"})
    return out


def summarize(results: list[dict]) -> dict:
    """Nota de calidad: % de criterios cumplidos (sin contar no_aplica ni error) y % de
    dialogos sin ningun no_cumple, en total y por categoria."""

    def block(items: list[dict]) -> dict:
        verdicts = [c["verdict"] for d in items for c in d["criteria"]]
        judged = [v for v in verdicts if v in ("cumple", "no_cumple")]
        passed = [d for d in items if not any(c["verdict"] in ("no_cumple", "error") for c in d["criteria"])]
        return {
            "dialogues": len(items),
            "dialogues_passed": len(passed),
            "dialogues_pass_pct": round(100 * len(passed) / len(items), 1) if items else None,
            "criteria_judged": len(judged),
            "criteria_failed": judged.count("no_cumple"),
            "criteria_pass_pct": round(100 * judged.count("cumple") / len(judged), 1) if judged else None,
            "not_applicable": verdicts.count("no_aplica"),
            "errors": verdicts.count("error"),
        }

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for d in results:
        by_cat[d["category"]].append(d)
    return {**block(results), "by_category": {k: block(v) for k, v in sorted(by_cat.items())}}


def judge(client, model: str, reference: str, dialogue: dict, records: list[dict], global_criteria: list[dict]) -> dict:
    crits = criteria_for(dialogue, global_criteria)
    user = (
        f"CONVERSACION (dialogo '{dialogue['id']}', categoria {dialogue['category']}):\n{transcript(records)}\n\n"
        f"CRITERIOS:\n" + "\n".join(f"- {c['id']}: {c['check']}" for c in crits)
    )
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": f"{JUDGE_INSTRUCTIONS}\n\nREFERENCIA:\n{reference}"},
            {"role": "user", "content": user},
        ],
    )
    usage = resp.usage
    cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    return {
        "id": dialogue["id"],
        "category": dialogue["category"],
        "conv": records[0]["conv"] if records else None,
        "criteria": parse_verdicts(resp.choices[0].message.content or "", [c["id"] for c in crits]),
        "usage": {"input": usage.prompt_tokens, "cached": cached, "output": usage.completion_tokens},
    }


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True, help="JSONL de scripts.run_synthetic_pre --sample golden")
    parser.add_argument("--model", default="gpt-4.1")
    parser.add_argument("--snapshot", help="foto JSON de scripts.langfuse_snapshot a la que anadir `quality`")
    args = parser.parse_args(argv)

    from openai import OpenAI  # import tardio: los tests no necesitan la clave

    api_key = _env("OPENAI_API_KEY")
    if not api_key:
        print("Falta OPENAI_API_KEY (entorno o ENV_FILE).", file=sys.stderr)
        return 2

    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    runs = latest_conversations(args.run)

    client, reference = OpenAI(api_key=api_key), load_reference()
    results, missing = [], []
    for n, dialogue in enumerate(golden["dialogues"], 1):
        records = runs.get(dialogue["id"])
        if not records:
            missing.append(dialogue["id"])
            continue
        result = judge(client, args.model, reference, dialogue, records, golden["global_criteria"])
        results.append(result)
        failed = [c["id"] for c in result["criteria"] if c["verdict"] in ("no_cumple", "error")]
        print(f"[{n}/{len(golden['dialogues'])}] {dialogue['id']}: {'OK' if not failed else 'FALLA ' + ', '.join(failed)}", flush=True)
        time.sleep(0.5)

    usage = {k: sum(r["usage"][k] for r in results) for k in ("input", "cached", "output")}
    summary = summarize(results)
    report = {
        "judged_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_file": args.run.replace("\\", "/"),
        "golden_version": golden["version"],
        "model": args.model,
        "missing_dialogues": missing,
        "usage": usage,
        "summary": summary,
        "dialogues": results,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{Path(args.run).stem}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    if args.snapshot:
        snap = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
        snap["quality"] = {
            "results_file": out.as_posix(),
            "model": args.model,
            **{k: v for k, v in summary.items() if k != "by_category"},
            "by_category": {k: v["criteria_pass_pct"] for k, v in summary["by_category"].items()},
        }
        Path(args.snapshot).write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(
        f"\nCriterios cumplidos: {summary['criteria_pass_pct']} % ({summary['criteria_failed']} fallos de {summary['criteria_judged']}); "
        f"dialogos sin fallos: {summary['dialogues_passed']}/{summary['dialogues']}; no evaluados: {len(missing)}; "
        f"tokens: {usage['input']} entrada ({usage['cached']} en cache), {usage['output']} salida.\nResultado: {out}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
