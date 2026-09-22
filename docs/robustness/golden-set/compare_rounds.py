"""Compara dos rondas juzgadas del golden-set dialogo a dialogo (antes/despues de un cambio).

Usa la nota REVISADA si la ronda la tiene (`reviewed_dialogues`, de apply_golden_review) y la del juez
si no. Solo compara los dialogos presentes en las dos (p. ej. el core contra la ronda completa).
Lista los que pasan de cumplir a fallar y al reves, criterio a criterio: eso es lo que hay que revisar
a mano antes de decir "no ha cambiado nada" o "ha mejorado".

    python docs/robustness/golden-set/compare_rounds.py <antes.json> <despues.json>
"""

import json
import sys
from pathlib import Path

RAW = "--raw" in sys.argv  # juez contra juez (cuando una de las dos rondas aun no esta revisada)


def verdicts(path: Path) -> dict[str, dict[str, str]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    dialogues = report["dialogues"] if RAW else (report.get("reviewed_dialogues") or report["dialogues"])
    return {d["id"]: {c["id"]: c["verdict"] for c in d["criteria"]} for d in dialogues}


def passed(crits: dict[str, str]) -> bool:
    return all(v in ("cumple", "no_aplica") for v in crits.values())


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = [a for a in sys.argv[1:] if a != "--raw"]
    before, after = verdicts(Path(args[0])), verdicts(Path(args[1]))
    common = sorted(set(before) & set(after))
    ok_b = sum(passed(before[i]) for i in common)
    ok_a = sum(passed(after[i]) for i in common)
    print(f"{len(common)} dialogos en comun · sin fallos: antes {ok_b} -> despues {ok_a}")
    for label, cond in (("EMPEORAN", lambda b, a: b == "cumple" and a == "no_cumple"),
                        ("MEJORAN", lambda b, a: b == "no_cumple" and a == "cumple"),
                        ("PASAN A REVISAR", lambda b, a: a == "revisar" and b != "revisar")):
        rows = [(i, c) for i in common for c in after[i] if c in before[i] and cond(before[i][c], after[i][c])]
        print(f"{label}: {len(rows)}")
        for i, c in rows:
            print(f"  - {i} · {c}")


if __name__ == "__main__":
    main()
