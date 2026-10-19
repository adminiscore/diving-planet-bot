"""ex-9b paso 4: qué cambia entre dos pasadas de `paso4_replay.py` (estado, respuesta y contexto del RAG), turno a turno.
Uso: python paso4_diff.py paso4-oraculo-base.json paso4-oraculo-flag.json [--todos]
Sin --todos enseña el primer cambio de cada diálogo; con --todos, todos los turnos que cambian.
"""
import difflib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comun  # noqa: E402

args = [x for x in sys.argv[1:] if not x.startswith("--")]
todos = "--todos" in sys.argv
a = json.loads((comun.OUT / args[0]).read_text(encoding="utf-8"))
b = json.loads((comun.OUT / args[1]).read_text(encoding="utf-8"))
campos = Counter()
dialogos_estado, dialogos_reply, dialogos_rag = set(), set(), set()
turnos_estado = turnos_reply = turnos_rag = 0
cambios = []
for x, y in zip(a["filas"], b["filas"], strict=True):
    assert (x["id"], x["turno"]) == (y["id"], y["turno"])
    dif = {k for k in set(x["estado"]) | set(y["estado"]) if x["estado"].get(k) != y["estado"].get(k)}
    if dif:
        turnos_estado += 1
        dialogos_estado.add(x["id"])
        campos.update(dif)
    if x["reply"] != y["reply"]:
        turnos_reply += 1
        dialogos_reply.add(x["id"])
    rag_dif = x.get("rag") != y.get("rag")
    if rag_dif:
        turnos_rag += 1
        dialogos_rag.add(x["id"])
    if dif or x["reply"] != y["reply"] or rag_dif:
        c = {"id": x["id"], "turno": x["turno"], "msg": x["msg"][:140],
             "estado": {k: [x["estado"].get(k), y["estado"].get(k)] for k in sorted(dif)}}
        if x["reply"] != y["reply"]:
            c["reply_a"], c["reply_b"] = x["reply"][:260], y["reply"][:260]
        if rag_dif:
            ra, rb = "\n".join(x.get("rag") or []), "\n".join(y.get("rag") or [])
            c["rag"] = [ln for ln in difflib.unified_diff(ra.splitlines(), rb.splitlines(), lineterm="", n=0)
                        if ln[:1] in "+-" and not ln.startswith(("+++", "---"))][:12]
        cambios.append(c)
print(f"{args[0]} vs {args[1]}: turnos con estado distinto {turnos_estado}/{len(a['filas'])}, con respuesta distinta "
      f"{turnos_reply}, con contexto del RAG distinto {turnos_rag}; diálogos: estado {len(dialogos_estado)}, "
      f"respuesta {len(dialogos_reply)}, RAG {len(dialogos_rag)} de {len({f['id'] for f in a['filas']})}")
print("campos que cambian (turnos):", dict(campos.most_common()))
vistos = set()
for c in cambios:
    if not todos and c["id"] in vistos:
        continue
    vistos.add(c["id"])
    print(f"\n* {c['id']} t{c['turno']}: {c['msg']!r}")
    if c["estado"]:
        print(f"  estado: {c['estado']}")
    if "reply_a" in c:
        print(f"  A: {c['reply_a']!r}\n  B: {c['reply_b']!r}")
    for ln in c.get("rag", []):
        print(f"  rag {ln[:220]}")
salida = comun.OUT / f"diff-{Path(args[0]).stem}-vs-{Path(args[1]).stem}.json"
salida.write_text(json.dumps({"turnos_estado": turnos_estado, "turnos_reply": turnos_reply, "turnos_rag": turnos_rag,
                              "dialogos_estado": sorted(dialogos_estado), "dialogos_reply": sorted(dialogos_reply),
                              "dialogos_rag": sorted(dialogos_rag), "campos": dict(campos), "cambios": cambios},
                             ensure_ascii=False, indent=1), encoding="utf-8")
