"""Bloque 4P: el mecanismo, sin juez, en las tiradas ×5 (docs/robustness/caln/4p/mec-*.jsonl de dpb-4p).

Uso:  ENV_FILE=.env.ci python -m scripts.mecanismo_4p docs/robustness/caln/4p
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from src.domain.politicas import politicas

PASE_FIJO = ("te paso ahora", "i'm passing you", "te paso con", "passing you to", "para preguntas médicas específicas",
             "esto tiene que revisarlo una persona")
NO_HAY_TARIFA = re.compile(r"no (hay|tenemos|manejamos|existe)[^.]{0,40}(tarifa|precio|comisi)|sin (tarifa|precio) de agencia|"
                           r"mismo precio|no agency|no (net rate|commission)", re.I)


def filas(carpeta: Path):
    por_dialogo = defaultdict(lambda: defaultdict(list))
    for f in sorted(carpeta.glob("mec-*.jsonl")):
        for linea in f.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                r = json.loads(linea)
                por_dialogo[r["dialogo"]][r["rep"]].append(r)
    return por_dialogo


def pase(r):
    return (r.get("estado") or {}).get("pending_escalation_reason")


def main(carpeta: str) -> None:
    datos = filas(Path(carpeta))
    politica = (politicas().get("reschedule") or {}).get("es", "")[:60]
    for dialogo, reps in sorted(datos.items()):
        print(f"\n=== {dialogo}: {len(reps)} repeticiones, {sum(len(t) for t in reps.values())} turnos")
        for rep, turnos in sorted(reps.items()):
            turnos.sort(key=lambda r: r["turn"])
            pases = [(r["turn"], pase(r)[:40]) for r in turnos if pase(r)]
            fijos = [r["turn"] for r in turnos if any(p in (r["reply"] or "").lower() for p in PASE_FIJO)]
            repetidos = [t for t in fijos if any(p[0] < t for p in pases)]
            errores = sum(1 for r in turnos if (r["reply"] or "").startswith("ERROR"))
            marcas = sorted({x.split("]")[2].strip()[:50] for r in turnos for x in (r.get("traza") or []) if "[CORE][4P]" in x})
            extra = ""
            if dialogo.endswith("agencia") or dialogo == "ciego-n09":
                t4 = next((r for r in turnos if "tarifa" in (r["msg"] or "").lower() or "rate" in (r["msg"] or "").lower()), None)
                extra = f" | tarifa: {'dice que no hay' if t4 and NO_HAY_TARIFA.search(t4['reply'] or '') else 'NO lo dice'}"
            if dialogo.endswith("cambio") or dialogo == "ciego-n06":
                con_politica = [r["turn"] for r in turnos if politica and politica in (r["reply"] or "")]
                extra = f" | turnos con la política: {con_politica}"
            if dialogo == "visto-6937":
                t2 = next((r for r in turnos if r["turn"] == 2), None)
                vuelo = bool(t2 and re.search(r"vol(ar|ver)|vuelo|fly|flight|7:00|18 ?h", t2["reply"] or "", re.I))
                extra = f" | t2 contesta el vuelo: {vuelo}"
            print(f"  rep {rep}: pases {pases or '-'} · texto fijo de pase en {fijos or '-'} · repetidos {repetidos or '-'}"
                  f" · errores {errores} · 4P {marcas or '-'}{extra}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1])
