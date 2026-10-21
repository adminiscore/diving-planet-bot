"""mej-3 (21-oct): ¿cuánto cambia el juez si juzga DOS veces la MISMA ronda? Mide su ruido, no el del bot.

Juzga la misma ronda N veces sin la cache (el juez oficial: gpt-5-mini, effort medium, referencia de por defecto) y
compara criterio a criterio: cuántos criterios LLM cambian de veredicto entre pasadas, cuáles, y cuánto se mueven la
nota (% de criterios) y los diálogos sin fallos. Con `--votos 3` mide el juez con votos en los dudosos
(`judge_golden_set --votos`), para comparar su estabilidad con la del juez de siempre.

    ENV_FILE=.env.dev python -m scripts.estabilidad_juez --run docs/robustness/synthetic-runs/<ronda>.jsonl --veces 2
    ENV_FILE=.env.dev python -m scripts.estabilidad_juez --run ... --veces 2 --votos 3

Coste: N veces una ronda juzgada entera sin cache (la core: ~0,2-0,4 $ por pasada con gpt-5-mini). No escribe en la
cache del juez. Resultado en docs/robustness/juez/estabilidad/<ronda>__vecesN[__votosV].json.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from scripts import judge_golden_set as jg

SALIDA = Path("docs/robustness/juez/estabilidad")


def juzgar_una_vez(client, golden: dict, runs: dict, reference: str, model: str, effort: str) -> list[dict]:
    resultados = []
    for dialogue in golden["dialogues"]:
        records = runs.get(dialogue["id"])
        if not records:
            continue
        criterios = jg.criteria_for(dialogue, golden["global_criteria"])
        juzgados = jg.judge_criteria(client, model, effort, reference, dialogue, records, criterios, None,
                                     {"hits": 0, "misses": 0})
        resultados.append({"id": dialogue["id"], "category": dialogue["category"], "criteria": juzgados})
    return resultados


def comparar(pasadas: list[list[dict]]) -> dict:
    """Criterio a criterio (solo los del juez LLM): los veredictos de cada pasada y los que no coinciden."""
    por_criterio: dict[tuple[str, str], list[str]] = {}
    for pasada in pasadas:
        for d in pasada:
            for c in d["criteria"]:
                if c.get("by") == "auto":
                    continue
                por_criterio.setdefault((d["id"], c["id"]), []).append(c["verdict"])
    cambian = [{"dialogo": d, "criterio": c, "veredictos": v}
               for (d, c), v in sorted(por_criterio.items()) if len(set(v)) > 1]
    notas = [jg.summarize(p) for p in pasadas]
    return {
        "criterios_llm": len(por_criterio),
        "criterios_que_cambian": len(cambian),
        "pct_que_cambian": round(100 * len(cambian) / len(por_criterio), 1) if por_criterio else None,
        "cambios_por_tipo": dict(Counter(" -> ".join(sorted(set(x["veredictos"]))) for x in cambian)),
        "notas": [{"criteria_pass_pct": n["criteria_pass_pct"], "dialogues_passed": n["dialogues_passed"],
                   "dialogues": n["dialogues"], "to_review": n["to_review"]} for n in notas],
        "cambian": cambian,
    }


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True, help="JSONL de una ronda (run_synthetic_pre o ronda_local_pre)")
    parser.add_argument("--veces", type=int, default=2)
    parser.add_argument("--votos", type=int, default=1, help="como judge_golden_set --votos")
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--effort", default="medium")
    args = parser.parse_args(argv)

    from openai import OpenAI  # import tardío: los tests no necesitan la clave

    api_key = jg._env("OPENAI_API_KEY")
    if not api_key:
        print("Falta OPENAI_API_KEY (entorno o ENV_FILE).", file=sys.stderr)
        return 2
    jg.VOTOS = max(1, args.votos)
    client = OpenAI(api_key=api_key)
    golden = json.loads(jg.GOLDEN_FILE.read_text(encoding="utf-8"))
    runs = jg.latest_conversations(args.run)
    reference = jg.load_reference(jg.REFERENCIA_POR_DEFECTO)
    pasadas = []
    for i in range(args.veces):
        pasadas.append(juzgar_una_vez(client, golden, runs, reference, args.model, args.effort))
        print(f"pasada {i + 1}/{args.veces}: {jg.summarize(pasadas[-1])['criteria_pass_pct']} %", flush=True)
    informe = {"juzgado": datetime.now(UTC).isoformat(timespec="seconds"), "run": args.run.replace("\\", "/"),
               "model": args.model, "effort": args.effort, "votos": jg.VOTOS, "veces": args.veces,
               **comparar(pasadas)}
    SALIDA.mkdir(parents=True, exist_ok=True)
    sufijo = f"__votos{jg.VOTOS}" if jg.VOTOS > 1 else ""
    out = SALIDA / f"{Path(args.run).stem}__veces{args.veces}{sufijo}.json"
    out.write_text(json.dumps(informe, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n{informe['criterios_que_cambian']} de {informe['criterios_llm']} criterios del juez cambian de veredicto "
          f"({informe['pct_que_cambian']} %); notas: {[n['criteria_pass_pct'] for n in informe['notas']]} %, "
          f"diálogos sin fallos: {[n['dialogues_passed'] for n in informe['notas']]}.\nResultado: {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
