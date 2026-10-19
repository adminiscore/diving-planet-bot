"""Junta el mapa (clase/propuesta por grupo) con los saltos en el golden visible (partes 1 y 6) por grupo funcional.
Salida: out/resumen.json y una tabla en pantalla."""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comun  # noqa: E402

DEST = comun.REPO / "docs/robustness/regex/estudio-ex9"
filas = list(csv.DictReader(open(DEST / "grupos.csv", encoding="utf-8")))
p6 = json.loads((comun.OUT / "parte6.json").read_text(encoding="utf-8"))
p1 = json.loads((comun.OUT / "parte1.json").read_text(encoding="utf-8"))
msgs = [x["msg"] for x in p1["por_mensaje"]]
assert len(msgs) == p6["mensajes"]
idx_por_msg = {m: i for i, m in enumerate(msgs)}


def gf_local(func: str, linea: int) -> str | None:
    if func == "_detect_group_info":
        return "ID-GRUPO-N" if linea < 1470 else "ID-GRUPO-R"
    if func in ("_detect_ages", "_add"):
        return "ID-EDAD"
    if func == "_detect_last_dive":
        return "ID-BUCEO2"
    if func == "_detect_location":
        return "ID-HOTEL" if linea in (2166, 2314) else "ID-ORIGEN"
    if func == "place_by_role":
        return "ID-ORIGEN"
    if func == "_detect_activity":
        return "ID-ACT"
    if func in ("course_level_is_ambiguous", "other_person_certification", "_other_person_cert_re") and linea != 539:
        return "ID-CERT"
    return None  # tokenizadores


# Índices de mensajes que hacen saltar cada grupo funcional.
saltos = defaultdict(set)
ejemplos = defaultdict(list)
for f in filas:
    clave = f"{f['fichero']}:{f['linea']}"
    g = p6["grupos"].get(clave)
    if g and "idx" in g:
        saltos[f["grupo_funcional"]] |= set(g["idx"])
# Locales del detector: de la traza de la parte 1 (los ejemplos son texto; se vuelve a indexar).
for r in p1["patrones"]:
    if r["modulo"] != "src.agents.intent_detector" or not r["patron"].startswith("local:"):
        continue
    _, func, linea = r["patron"].split(":")
    gf = gf_local(func, int(linea))
    if gf is None:
        continue
    # La traza guarda los 4 primeros ejemplos; para contar se recalcula abajo desde por_mensaje si hace falta.
    for e in r["ejemplos"]:
        for m in msgs:
            if m[:140] == e:
                saltos[gf].add(idx_por_msg[m])
# Las decisiones del detector por campo (más fiable que los ejemplos truncados): mensajes donde detect() pone el campo.
campo_gf = {"activity": "ID-ACT", "cert_dives": "ID-NUM", "cert_days": "ID-NUM", "duration": "ID-DUR",
            "is_certified": "ID-CERT", "group_size": "ID-GRUPO-N", "solo_confirmed": "ID-GRUPO-N",
            "group_allocation": "ID-GRUPO-R", "ages": "ID-EDAD", "last_dive_over_2_years": "ID-BUCEO2",
            "location": "ID-ORIGEN", "island": "ID-HOTEL", "hotel": "ID-HOTEL", "is_colombian": "ID-NAC"}
decide = defaultdict(set)
for x in p1["por_mensaje"]:
    for c in x["detect"]:
        if c in campo_gf:
            decide[campo_gf[c]].add(x["i"])
            saltos[campo_gf[c]].add(x["i"])

por_gf = defaultdict(lambda: {"patrones": 0, "a": 0, "b": 0, "c": 0, "d": 0, "propuestas": defaultdict(int), "grupos": []})
for f in filas:
    if f["familia_corregida"] != "entender al cliente" and not f["grupo_funcional"].startswith(("S-ALCOHOL", "S-IA", "S-MISMOPRECIO", "R-RESUMEN")):
        continue
    d = por_gf[f["grupo_funcional"]]
    n = int(f["patrones"])
    d["patrones"] += n
    d[f["clase"]] += n
    d["propuestas"][f["propuesta"]] += n
    d["grupos"].append(f"{f['nombre']}({n})")
    d["nombre"] = f["nombre_grupo_funcional"]
out = {}
for gf, d in sorted(por_gf.items(), key=lambda kv: -kv[1]["patrones"]):
    s = saltos.get(gf, set())
    out[gf] = {**{k: v for k, v in d.items() if k != "propuestas"}, "propuestas": dict(d["propuestas"]),
               "saltos_golden": len(s), "decide_detect": len(decide.get(gf, ())),
               "ejemplos": [msgs[i][:100] for i in sorted(s)[:6]]}
    print(f"{gf:14} {d['patrones']:4} a{d['a']:3} b{d['b']:3} c{d['c']:3} d{d['d']:3} salta {len(s):3} "
          f"decide {len(decide.get(gf, ())):3}  {dict(d['propuestas'])}  {d['nombre'][:50]}")
ent = [f for f in filas if f["familia_corregida"] == "entender al cliente"]
union = set()
for gf in out:
    if any(f["grupo_funcional"] == gf and f["clase"] in ("a", "b") for f in ent):
        union |= saltos.get(gf, set())
print("mensajes (de", len(msgs), ") que hacen saltar algún grupo a/b de 'entender':", len(union))
(comun.OUT / "resumen.json").write_text(json.dumps({"por_gf": out, "mensajes": len(msgs), "union_ab": len(union)},
                                                   ensure_ascii=False, indent=1), encoding="utf-8")
