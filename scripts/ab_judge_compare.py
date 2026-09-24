"""A/B del juez: compara criterio a criterio dos resultados de `judge_golden_set`.

    python -m scripts.ab_judge_compare 2026-09-24-u34-A 2026-09-24-u34-B

Imprime el resumen de cada ronda, las MEJORAS y las REGRESIONES con el motivo del juez.
Regla del protocolo: leer el TEXTO del bot de cada regresión antes de concluir (el juez
tiene ruido: a veces marca en B lo que en A era idéntico).
"""
import json
import sys

R = "docs/robustness/golden-set/results/{}__gpt-5-mini-medium.json"
A, B = (json.load(open(R.format(n), encoding="utf-8")) for n in sys.argv[1:3])
for n, d in (("A", A), ("B", B)):
    s = d["summary"]
    print(f"{n}: dialogos {s['dialogues_passed']}/{s['dialogues']} ({s['dialogues_pass_pct']}%) | criterios "
          f"{s['criteria_judged'] - s['criteria_failed']}/{s['criteria_judged']} ({s['criteria_pass_pct']}%) | revisar {s['to_review']} | coste {d['cost_usd']} | cache {d['cache']}")
va = {(d["id"], c["id"]): c for d in A["dialogues"] for c in d["criteria"]}
vb = {(d["id"], c["id"]): c for d in B["dialogues"] for c in d["criteria"]}
mej, reg = [], []
for k in sorted(set(va) & set(vb)):
    a, b = va[k]["verdict"], vb[k]["verdict"]
    if a == b:
        continue
    if a != "cumple" and b == "cumple":
        mej.append((k, a, b, vb[k]))
    elif a == "cumple" and b != "cumple":
        reg.append((k, a, b, vb[k]))
print(f"\nMEJORAS ({len(mej)})")
for k, a, b, c in mej:
    print(f"  + {k[0]} / {k[1]}: {a} -> {b}")
print(f"\nREGRESIONES ({len(reg)})")
for k, a, b, c in reg:
    print(f"  - {k[0]} / {k[1]}: {a} -> {b} | {c.get('reason', '')[:260]}")
