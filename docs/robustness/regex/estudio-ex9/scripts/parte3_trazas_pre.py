"""Parte 3: en PRE, ¿el regex y el extractor coinciden? Trazas de docs/robustness/cal/estabilidad/*.jsonl (24 diálogos
VISIBLES del golden, varias repeticiones, con la traza del turno). Las líneas [EXTRACT][EX5..EX8] dicen el valor del
extractor y el que leía el regex ("(regex: X)" o "el regex leía X; el cliente no lo afirma"). La etiqueta del banco ex0
(mismo diálogo y turno) dice quién tenía razón.
Salida: out/parte3.json
"""
import ast
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comun  # noqa: E402

ocultos = comun.ids_ocultos()
etiquetas = json.loads((comun.REPO / "docs/robustness/regex/banco-ex0/etiquetas.json").read_text(encoding="utf-8"))

R_VALOR = re.compile(r"^\[EXTRACT\]\[EX(\d)\] (\w+)=(.+?) \(regex: (.+?)(?:, guardado: .*)?\)$")
R_LEIA = re.compile(r"^\[EXTRACT\]\[EX(\d)\] el regex le[ií]a (\w+)=(.+?); el cliente no (?:lo afirma|la elige)")
R_U3 = re.compile(r"^\[EXTRACT\]\[U3-(\d)\] campo=(\w+) regex=(.+?) descartado por Jev")


def _v(txt):
    try:
        return ast.literal_eval(txt)
    except Exception:  # noqa: BLE001
        return txt


por_campo = defaultdict(Counter)
distintos = defaultdict(lambda: defaultdict(set))
ejemplos = defaultdict(list)
otras = Counter()
turnos = 0
turnos_dialogo = set()
for f in sorted(glob.glob(str(comun.REPO / "docs/robustness/cal/estabilidad/*.jsonl"))):
    dialogo = os.path.basename(f)[:-6]
    if dialogo in ocultos:
        continue
    for x in open(f, encoding="utf-8"):
        r = json.loads(x)
        turnos += 1
        turnos_dialogo.add((dialogo, r["turn"]))
        et = etiquetas.get(f"ex0-{dialogo}-t{r['turn']}") or {}
        esperado = et.get("expected") if et.get("slot") != "DUDOSO" else None
        for linea in r.get("traza") or []:
            m = R_VALOR.match(linea)
            if m:
                _, campo, ext, rx = m.groups()
                ext, rx = _v(ext), _v(rx)
                if rx is None:
                    clave = "solo el extractor (el regex no leía nada)"
                elif rx == ext:
                    clave = "coinciden"
                else:
                    clave = "distinto valor"
                por_campo[campo][clave] += 1
                distintos[campo][clave].add((dialogo, r["turn"]))
                if esperado is not None and rx is not None and rx != ext:
                    quien = ("extractor acierta" if esperado.get(campo) == ext else
                             "regex acierta" if esperado.get(campo) == rx else "ninguno")
                    por_campo[campo][f"distinto: {quien}"] += 1
                    distintos[campo][f"distinto: {quien}"].add((dialogo, r["turn"]))
                    ejemplos[f"{campo} distinto ({quien})"].append(f"{r['msg'][:90]!r}: extractor={ext!r} regex={rx!r}")
                if esperado is not None and rx is None:
                    por_campo[campo]["solo extractor: " + ("acierta" if esperado.get(campo) == ext else "no etiquetado")] += 1
                continue
            m = R_LEIA.match(linea)
            if m:
                _, campo, rx = m.groups()
                rx = _v(rx)
                por_campo[campo]["el regex leía y el extractor dice que NO lo afirma"] += 1
                distintos[campo]["el regex leía y el extractor dice que NO lo afirma"].add((dialogo, r["turn"]))
                if esperado is not None:
                    quien = "extractor acierta (no lo dice)" if campo not in esperado else (
                        "regex acierta" if esperado.get(campo) == rx else "ninguno")
                    por_campo[campo][f"descartado: {quien}"] += 1
                    distintos[campo][f"descartado: {quien}"].add((dialogo, r["turn"]))
                    ejemplos[f"{campo} descartado ({quien})"].append(f"{r['msg'][:90]!r}: regex={rx!r}")
                continue
            m = R_U3.match(linea)
            if m:
                otras[f"Jev descarta lo del regex (U3-{m.group(1)}) en {m.group(2)}"] += 1
                continue
            for clave in ("[CORE][S4-26] la regex ve a otra persona y Jev no", "[CORE][CAL-C5] el extractor leyó",
                          "[EXTRACT][EX5] el extractor falló", "[EXTRACT][EX] el extractor falló",
                          "[INTENT] Detected duration", "[INTENT] Detected cert dive count",
                          "[INTENT] Detected cert day count", "[INTENT] Detected ages", "[INTENT] Detected island",
                          "[INTENT] Detected hotel", "[INTENT] Detected language", "[CORE] singular course booking",
                          "[CORE][SIGNALS]", "[CORE][U3-6]", "[EXTRACT][CUTOVER]"):
                if linea.startswith(clave):
                    otras[clave] += 1
                    if len(ejemplos[clave]) < 6:
                        ejemplos[clave].append(f"{r['msg'][:90]!r}: {linea[:150]}")

print("DISTINTOS (dialogo, turno):")
for c, v in distintos.items():
    print(" ", c, {k: len(x) for k, x in v.items()})
print("turnos con traza:", turnos, "turnos distintos:", len(turnos_dialogo))
for c, v in por_campo.items():
    print(f"\n{c}: {dict(v)}")
print()
for k, v in otras.most_common():
    print(v, k)
for k, v in ejemplos.items():
    print(f"* {k} ({len(v)}): {v[:3]}")
(comun.OUT / "parte3.json").write_text(json.dumps(
    {"turnos": turnos, "turnos_distintos": len(turnos_dialogo), "por_campo": {c: dict(v) for c, v in por_campo.items()},
     "distintos": {c: {k: len(x) for k, x in v.items()} for c, v in distintos.items()},
     "otras": dict(otras), "ejemplos": {k: v[:10] for k, v in ejemplos.items()}}, ensure_ascii=False, indent=1),
    encoding="utf-8")
