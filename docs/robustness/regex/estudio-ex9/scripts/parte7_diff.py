"""Parte 7: qué cambia al quitar lo que lee el detector (replays de la parte 5). Compara estado y respuesta turno a turno.
Uso: python parte7_diff.py replay-oraculo-base.json replay-oraculo-sin_dominios.json
"""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comun  # noqa: E402

a = json.loads((comun.OUT / sys.argv[1]).read_text(encoding="utf-8"))
b = json.loads((comun.OUT / sys.argv[2]).read_text(encoding="utf-8"))
campos = Counter()
dialogos_estado, dialogos_reply = set(), set()
turnos_estado = turnos_reply = 0
ejemplos = []
primer_cambio = {}
for x, y in zip(a["filas"], b["filas"]):
    assert (x["id"], x["turno"]) == (y["id"], y["turno"])
    dif = {k for k in x["estado"] if x["estado"].get(k) != y["estado"].get(k)}
    if x["estado"].get("carrito") != y["estado"].get("carrito"):
        dif.add("carrito")
    if dif:
        turnos_estado += 1
        dialogos_estado.add(x["id"])
        campos.update(dif)
    if x["reply"] != y["reply"]:
        turnos_reply += 1
        dialogos_reply.add(x["id"])
    if (dif or x["reply"] != y["reply"]) and x["id"] not in primer_cambio:
        primer_cambio[x["id"]] = {"turno": x["turno"], "msg": x["msg"][:120],
                                  "cambios": {k: [x["estado"].get(k), y["estado"].get(k)] for k in sorted(dif)},
                                  "reply_a": x["reply"][:220], "reply_b": y["reply"][:220]}
print(f"{sys.argv[1]} vs {sys.argv[2]}: turnos con estado distinto {turnos_estado}/{len(a['filas'])}, "
      f"con respuesta distinta {turnos_reply}; diálogos con estado distinto {len(dialogos_estado)}, "
      f"con respuesta distinta {len(dialogos_reply)} de {len({f['id'] for f in a['filas']})}")
print("campos que cambian (turnos):", dict(campos.most_common()))
for did, c in list(primer_cambio.items()):
    print(f"\n* {did} t{c['turno']}: {c['msg']!r}\n  cambios: {c['cambios']}\n  A: {c['reply_a']!r}\n  B: {c['reply_b']!r}")
salida = comun.OUT / f"diff-{Path(sys.argv[1]).stem}-vs-{Path(sys.argv[2]).stem}.json"
salida.write_text(json.dumps({"turnos_estado": turnos_estado, "turnos_reply": turnos_reply,
                              "dialogos_estado": sorted(dialogos_estado), "dialogos_reply": sorted(dialogos_reply),
                              "campos": dict(campos), "primer_cambio": primer_cambio}, ensure_ascii=False, indent=1),
                  encoding="utf-8")
