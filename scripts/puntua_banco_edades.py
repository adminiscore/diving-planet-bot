"""Puntúa un banco de edades (CALN2-04) en corridas de reproducir_juez_pre, por código y sin juez: por diálogo y
repetición, el estado y la respuesta del ÚLTIMO turno.

    python scripts/puntua_banco_edades.py docs/robustness/caln/banco-edades.json A.jsonl [B.jsonl]

- "estado": cada campo igual; "estado_no": ningún campo con ese valor;
- "edades": esas edades en `detected_ages`;
- "debe": cada fragmento («a|b» = cualquiera) sale en la respuesta (minúsculas, sin tildes);
- "ninguno": ningún fragmento sale.
"""
import json
import sys
import unicodedata
from collections import defaultdict


def plano(s):
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


def motivos(d, fila):
    est, reply, out = fila.get("estado") or {}, plano(fila.get("reply")), []
    for campo, v in (d.get("estado") or {}).items():
        if est.get(campo) != v:
            out.append(f"{campo}={est.get(campo)}")
    for campo, v in (d.get("estado_no") or {}).items():
        if est.get(campo) == v:
            out.append(f"{campo}={v}!")
    faltan = set(d.get("edades") or []) - set(est.get("detected_ages") or [])
    if faltan:
        out.append(f"edades sin guardar {sorted(faltan)}")
    for frag in d.get("debe") or []:
        if not any(plano(f) in reply for f in frag.split("|")):
            out.append(f"falta «{frag}»")
    for frag in d.get("ninguno") or []:
        if any(plano(f) in reply for f in frag.split("|")):
            out.append(f"dice «{frag}»")
    return out


banco = json.load(open(sys.argv[1], encoding="utf-8"))["dialogos"]
corridas = {}
for nombre, ruta in zip("AB", sys.argv[2:4]):
    ultimos = {}
    for ln in open(ruta, encoding="utf-8"):
        f = json.loads(ln)
        k = (f["dialogo"], f["rep"])
        if k not in ultimos or f["turn"] >= ultimos[k]["turn"]:
            ultimos[k] = f
    corridas[nombre] = ultimos
total = defaultdict(lambda: [0, 0])
for d in banco:
    linea = [f"{d['id']:<30}"]
    for nombre, ultimos in corridas.items():
        filas = [f for (dlg, _), f in sorted(ultimos.items()) if dlg == d["id"]]
        malos = [motivos(d, f) for f in filas]
        ok = sum(not m for m in malos)
        total[nombre][0] += ok
        total[nombre][1] += len(filas)
        detalle = "; ".join(sorted({", ".join(m) for m in malos if m}))
        linea.append(f"{nombre} {ok}/{len(filas)}" + (f" ({detalle})" if detalle else ""))
    print("  ".join(linea))
print("TOTAL", "  ".join(f"{n} {a}/{b}" for n, (a, b) in total.items()))
