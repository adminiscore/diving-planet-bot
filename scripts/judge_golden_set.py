"""LLM-juez end-to-end del golden-set (plan maestro, M0 m0-3).

Lee una ejecucion de `scripts.run_synthetic_pre --sample golden` (la conversacion REAL que
dio PRE) y evalua cada criterio (globales + propios) de cada dialogo del golden-set:

- **Criterios `auto`** (mecanicos: se presenta una vez, da el link, importes del catalogo):
  los comprueba codigo, sin LLM. Deterministas y gratis.
- **El resto**: una llamada al modelo juez POR CRITERIO. Para marcar `no_cumple` tiene que
  citar literalmente lo que dijo el bot (y, si aplica, lo que ya habia dicho el cliente).
  Si la cita no aparece en la conversacion, el veredicto baja a `revisar`: un fallo sin
  evidencia verificable no cuenta como fallo.

Veredictos: `cumple`, `no_cumple`, `no_aplica`, `revisar` (lo decide una persona) y
`error` (el juez no devolvio nada valido). La nota de calidad solo cuenta cumple/no_cumple.

El juez recibe la referencia del negocio desde el repo (precios, politicas, descuentos,
disponibilidad, escalado y un extracto de actividades), primero y siempre igual, para
aprovechar la cache de prompts de OpenAI.

Uso (en serie):

    ENV_FILE=.env.dev python -m scripts.judge_golden_set \\
        --run docs/robustness/synthetic-runs/2026-09-17-golden.jsonl [--model gpt-5 --effort low] [--snapshot foto.json]

Escribe `docs/robustness/golden-set/results/<ejecucion>__<modelo>.json`. Con `--snapshot`
anade `quality` a una foto de `scripts.langfuse_snapshot` (linea temporal de la pagina).
"""

import argparse
import json
import re
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from scripts.langfuse_snapshot import _env

GOLDEN_FILE = Path("docs/robustness/golden-set/golden-dialogues.json")
RESULTS_DIR = Path("docs/robustness/golden-set/results")
KB_DIR = Path("data/knowledge_base")
VERDICTS = ("cumple", "no_cumple", "no_aplica")
BOOKING_LINK = "book.divingplanet.org"

# USD por millon de tokens (entrada, entrada en cache, salida), tabla de modelos de
# Langfuse a 2026-09-17. Solo para informar del coste de cada ronda.
PRICES = {
    "gpt-4.1": (2.0, 0.5, 8.0),
    "gpt-4.1-mini": (0.4, 0.1, 1.6),
    "gpt-5": (1.25, 0.125, 10.0),
    "gpt-5-mini": (0.25, 0.025, 2.0),
}

JUDGE_INSTRUCTIONS = """Eres un evaluador estricto de conversaciones de Coral, el asistente de reservas de Diving Planet (buceo en las Islas del Rosario, Colombia).

Recibes:
1. REFERENCIA: los datos oficiales del negocio (precios 2026, politicas, descuentos, disponibilidad, reglas de escalado a humano y actividades con edades). Es la unica fuente de verdad.
2. Una CONVERSACION real entre un CLIENTE y el BOT.
3. UN CRITERIO.

Decide si la conversacion cumple ese criterio:
- "cumple": lo cumple.
- "no_cumple": lo incumple. Algo que contradice la REFERENCIA es un incumplimiento, aunque suene razonable.
- "no_aplica": la conversacion no llega a la situacion que evalua el criterio. No lo uses para disculpar un fallo: si el bot debia llegar ahi y no llego, es "no_cumple".

Reglas:
- Juzga solo lo que dice el BOT; el cliente puede decir cosas falsas.
- Los precios "reservando online" de la referencia son los validos. Un precio redondeado a la unidad es correcto.
- Un "saludo" es presentarse o decir hola/hi. "¡Genial!", "¡Buena noticia!" o "¡Con gusto te ayudo!" no son saludos.
- Una "repregunta" es volver a pedir un dato que el cliente YA dio. Repetir una pregunta que el cliente no ha contestado NO es repreguntar.
- Ofrecer que un asesor contacte al cliente cuenta como pasar a un asesor.

EVIDENCIA OBLIGATORIA para "no_cumple":
- "evidencia_bot": copia LITERAL (sin cambiar palabras) del fragmento del BOT que demuestra el incumplimiento; si el fallo es no hacer algo, copia la respuesta del bot donde debia hacerlo.
- "evidencia_cliente": copia LITERAL del fragmento del CLIENTE que lo prueba (por ejemplo, donde ya dio el dato que el bot repregunta), o null si no hace falta.
Si no puedes citar evidencia literal, no marques "no_cumple".

Responde SOLO con JSON: {"verdict": "cumple|no_cumple|no_aplica", "evidencia_bot": "..." o null, "evidencia_cliente": "..." o null, "motivo": "una o dos frases"}"""


# --------------------------------------------------------------------------- datos


def latest_conversations(run_file: str) -> dict[str, list[dict]]:
    """Turnos por dialogo, quedandose con la ULTIMA conversacion de cada uno: relanzar solo
    algunos dialogos (`run_synthetic_pre --ids`) anade al mismo fichero sin pisar los demas."""
    by_conv: dict[tuple[str, int], list[dict]] = defaultdict(list)
    with open(run_file, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rec = json.loads(line)
                by_conv[(rec["tag"], rec["conv"])].append(rec)
    latest: dict[str, int] = {}
    for tag, conv in by_conv:
        latest[tag] = max(conv, latest.get(tag, conv))
    return {tag: sorted(by_conv[(tag, conv)], key=lambda r: r["turn"]) for tag, conv in latest.items()}


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


def bot_bubbles(record: dict) -> list[str]:
    return [] if record.get("reply") is None else record["reply"].split("\n---\n")


def transcript(records: list[dict]) -> str:
    lines = []
    for r in sorted(records, key=lambda r: r["turn"]):
        lines.append(f"CLIENTE: {r['msg']}")
        bubbles = bot_bubbles(r)
        lines += [f"BOT: {b}" for b in bubbles] if bubbles else ["BOT: [sin respuesta en el tiempo de espera]"]
    return "\n".join(lines)


def criteria_for(dialogue: dict, global_criteria: list[dict]) -> list[dict]:
    """Globales + propios. Un propio con el mismo id que un global lo concreta y manda."""
    own_ids = {c["id"] for c in dialogue["criteria"]}
    return [{**c, "id": f"global:{c['id']}"} for c in global_criteria if c["id"] not in own_ids] + list(dialogue["criteria"])


# ------------------------------------------------------------ comprobaciones auto

_GREETING = re.compile(r"\b(soy|i'?m|i am)\s+\*?coral\b", re.IGNORECASE)
# "178 USD", "630.000 COP", "1.429.000 COP", "USD 178"
_AMOUNT = re.compile(r"(?:(\d{1,3}(?:[.,]\d{3})+|\d+)(?:,\d{1,2})?\s*\*?\s*(USD|COP))|(?:(USD|COP)\s*\$?\s*(\d{1,3}(?:[.,]\d{3})+|\d+))")


def _amounts(text: str) -> list[tuple[int, str]]:
    out = []
    for m in _AMOUNT.finditer(text):
        raw, cur = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        out.append((int(re.sub(r"[.,]", "", raw)), cur))
    return out


def catalog_units() -> dict[str, set[int]]:
    """Precios unitarios del catalogo (online y normal) por moneda, recorriendo pricing.json."""
    units: dict[str, set[int]] = {"USD": set(), "COP": set()}

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, (int, float)) and k.startswith(("usd_", "cop_")):
                    units["USD" if k.startswith("usd_") else "COP"].add(round(v))
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(json.loads((KB_DIR / "pricing.json").read_text(encoding="utf-8-sig")))
    return units


def _explained(amount: int, units: set[int], currency: str) -> bool:
    """Un importe se explica si es un precio unitario, unidades x precio (hasta 20) o la suma
    de dos o tres lineas asi. En USD se admiten 5 de margen por el redondeo de cada linea."""
    lines = sorted({k * u for u in units for k in range(1, 21)})
    line_set = set(lines)
    tolerance = 5 if currency == "USD" else 0

    def is_line(value: int) -> bool:
        return any(value + d in line_set for d in range(-tolerance, tolerance + 1))

    if is_line(amount):
        return True
    below = [x for x in lines if x < amount]
    for i, a in enumerate(below):
        if is_line(amount - a):
            return True
        for b in below[i:]:
            if a + b >= amount:
                break
            if is_line(amount - a - b):
                return True
    return False


def check_single_greeting(records: list[dict]) -> dict:
    hits = [b for r in records for b in bot_bubbles(r) if _GREETING.search(b)]
    if len(hits) <= 1:
        return {"verdict": "cumple", "reason": f"se presenta {len(hits)} vez/veces"}
    return {"verdict": "no_cumple", "reason": f"se presenta {len(hits)} veces", "evidencia_bot": hits[1][:200]}


def check_last_reply_has_booking_link(records: list[dict]) -> dict:
    last = records[-1] if records else {}
    if last.get("reply") is None:
        return {"verdict": "no_cumple", "reason": "el ultimo turno no tuvo respuesta"}
    if BOOKING_LINK in last["reply"]:
        return {"verdict": "cumple", "reason": "la respuesta incluye el link de reserva"}
    return {"verdict": "no_cumple", "reason": "la respuesta no incluye el link de reserva", "evidencia_bot": last["reply"][:300]}


def check_amounts_match_catalog(records: list[dict]) -> dict:
    units = catalog_units()
    found = [(a, c) for r in records for b in bot_bubbles(r) for a, c in _amounts(b)]
    if not found:
        return {"verdict": "no_aplica", "reason": "el bot no da importes"}
    odd = [f"{a} {c}" for a, c in found if not _explained(a, units[c], c)]
    if not odd:
        return {"verdict": "cumple", "reason": f"{len(found)} importes, todos del catalogo"}
    # No se marca fallo: un descuento aplicado o un formato nuevo no deben contar como invencion.
    return {"verdict": "revisar", "reason": "importes que no salen del catalogo: " + ", ".join(odd)}


AUTO_CHECKS = {
    "single_greeting": check_single_greeting,
    "last_reply_has_booking_link": check_last_reply_has_booking_link,
    "amounts_match_catalog": check_amounts_match_catalog,
}


# ------------------------------------------------------------------ juez LLM


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    return " ".join(re.sub(r"[^\w\s]", " ", text).split())


def quote_found(quote: str | None, text: str) -> bool:
    """La cita (o cada trozo si viene con '...') aparece literal en el texto, ignorando
    mayusculas, puntuacion, emojis y markdown."""
    if not quote:
        return False
    haystack = _norm(text)
    parts = [_norm(p) for p in re.split(r"\.\.\.|…", quote)]
    parts = [p for p in parts if len(p) >= 6]
    return bool(parts) and all(p in haystack for p in parts)


def check_evidence(verdict: dict, records: list[dict]) -> dict:
    """Un `no_cumple` sin cita verificable del bot (o con cita del cliente inventada) baja a `revisar`."""
    if verdict["verdict"] != "no_cumple":
        return verdict
    bot_text = "\n".join(b for r in records for b in bot_bubbles(r))
    client_text = "\n".join(r["msg"] for r in records)
    if not quote_found(verdict.get("evidencia_bot"), bot_text):
        return {**verdict, "verdict": "revisar", "reason": f"[evidencia del bot no encontrada] {verdict.get('reason', '')}"}
    if verdict.get("evidencia_cliente") and not quote_found(verdict["evidencia_cliente"], client_text):
        return {**verdict, "verdict": "revisar", "reason": f"[evidencia del cliente no encontrada] {verdict.get('reason', '')}"}
    return verdict


def parse_verdict(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"verdict": "error", "reason": "el juez no devolvio JSON"}
    if not isinstance(data, dict) or data.get("verdict") not in VERDICTS:
        return {"verdict": "error", "reason": "el juez no devolvio un veredicto valido"}
    return {
        "verdict": data["verdict"],
        "reason": str(data.get("motivo") or data.get("reason") or ""),
        "evidencia_bot": data.get("evidencia_bot"),
        "evidencia_cliente": data.get("evidencia_cliente"),
    }


def llm_judge_criterion(client, model: str, effort: str | None, reference: str, dialogue: dict, records: list[dict], criterion: dict) -> dict:
    user = (
        f"CONVERSACION (dialogo '{dialogue['id']}', categoria {dialogue['category']}):\n{transcript(records)}\n\n"
        f"CRITERIO ({criterion['id']}): {criterion['check']}"
    )
    kwargs = {"reasoning_effort": effort} if model.startswith(("gpt-5", "o")) and effort else {"temperature": 0}
    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": f"{JUDGE_INSTRUCTIONS}\n\nREFERENCIA:\n{reference}"},
            {"role": "user", "content": user},
        ],
        **kwargs,
    )
    usage = resp.usage
    cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    verdict = check_evidence(parse_verdict(resp.choices[0].message.content or ""), records)
    return {**verdict, "usage": {"input": usage.prompt_tokens, "cached": cached, "output": usage.completion_tokens}}


def evaluate_criterion(client, model, effort, reference, dialogue, records, criterion) -> dict:
    if criterion.get("auto"):
        result = {**AUTO_CHECKS[criterion["auto"]](records), "by": "auto"}
    else:
        result = {**llm_judge_criterion(client, model, effort, reference, dialogue, records, criterion), "by": model}
    return {"id": criterion["id"], **result}


# ------------------------------------------------------------------ resumen


def summarize(results: list[dict]) -> dict:
    """Nota de calidad: % de criterios cumplidos sobre los decididos (cumple + no_cumple) y
    % de dialogos sin ningun no_cumple/error, en total y por categoria. `revisar` se cuenta aparte."""

    def block(items: list[dict]) -> dict:
        verdicts = [c["verdict"] for d in items for c in d["criteria"]]
        decided = [v for v in verdicts if v in ("cumple", "no_cumple")]
        passed = [d for d in items if not any(c["verdict"] in ("no_cumple", "error") for c in d["criteria"])]
        return {
            "dialogues": len(items),
            "dialogues_passed": len(passed),
            "dialogues_pass_pct": round(100 * len(passed) / len(items), 1) if items else None,
            "criteria_judged": len(decided),
            "criteria_failed": decided.count("no_cumple"),
            "criteria_pass_pct": round(100 * decided.count("cumple") / len(decided), 1) if decided else None,
            "not_applicable": verdicts.count("no_aplica"),
            "to_review": verdicts.count("revisar"),
            "errors": verdicts.count("error"),
        }

    by_cat: dict[str, list[dict]] = defaultdict(list)
    for d in results:
        by_cat[d["category"]].append(d)
    return {**block(results), "by_category": {k: block(v) for k, v in sorted(by_cat.items())}}


def cost_usd(model: str, usage: dict) -> float | None:
    if model not in PRICES:
        return None
    price_in, price_cached, price_out = PRICES[model]
    return round(((usage["input"] - usage["cached"]) * price_in + usage["cached"] * price_cached + usage["output"] * price_out) / 1e6, 4)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True, help="JSONL de scripts.run_synthetic_pre --sample golden")
    parser.add_argument("--model", default="gpt-5")
    parser.add_argument("--effort", default="low", help="reasoning_effort para modelos razonadores")
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
        criteria = [evaluate_criterion(client, args.model, args.effort, reference, dialogue, records, c) for c in criteria_for(dialogue, golden["global_criteria"])]
        results.append({"id": dialogue["id"], "category": dialogue["category"], "conv": records[0]["conv"], "criteria": criteria})
        flagged = [f"{c['id']}={c['verdict']}" for c in criteria if c["verdict"] not in ("cumple", "no_aplica")]
        print(f"[{n}/{len(golden['dialogues'])}] {dialogue['id']}: {'OK' if not flagged else ', '.join(flagged)}", flush=True)
        time.sleep(0.2)

    usage = {k: sum(c.get("usage", {}).get(k, 0) for d in results for c in d["criteria"]) for k in ("input", "cached", "output")}
    summary = summarize(results)
    report = {
        "judged_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_file": args.run.replace("\\", "/"),
        "golden_version": golden["version"],
        "model": args.model,
        "effort": args.effort,
        "missing_dialogues": missing,
        "usage": usage,
        "cost_usd": cost_usd(args.model, usage),
        "summary": summary,
        "dialogues": results,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{Path(args.run).stem}__{args.model}-{args.effort}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    if args.snapshot:
        snap = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
        snap["quality"] = {
            "results_file": out.as_posix(),
            "model": f"{args.model} ({args.effort})",
            **{k: v for k, v in summary.items() if k != "by_category"},
            "by_category": {k: v["criteria_pass_pct"] for k, v in summary["by_category"].items()},
        }
        Path(args.snapshot).write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(
        f"\nCriterios cumplidos: {summary['criteria_pass_pct']} % ({summary['criteria_failed']} fallos de {summary['criteria_judged']}); "
        f"a revisar: {summary['to_review']}; dialogos sin fallos: {summary['dialogues_passed']}/{summary['dialogues']}; "
        f"coste: {report['cost_usd']} $ ({usage['input']} entrada, {usage['cached']} en cache, {usage['output']} salida).\nResultado: {out}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
