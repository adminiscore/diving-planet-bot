"""Parte 6: cuánto SALTA cada grupo (de módulo o de clase) sobre los 342 mensajes de cliente visibles distintos, mirado
aparte del flujo (¿casa el patrón con el mensaje?). Los trozos que solo sirven para componer otros patrones
(FRAGMENTOS) no se miden solos. Los grupos locales (dentro de funciones) salen de la traza del detector (parte 1).
Salida: out/parte6.json
"""
import importlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comun  # noqa: E402

comun.bloquear_red()
from scripts.inventario_regex import inventario  # noqa: E402
from src.utils.text import strip_accents  # noqa: E402

FRAGMENTOS = {"_DIVE_NUMBER", "_DURATION_UNITS", "_DURATION_QTY", "_DURATION_FILLER", "_NEVER_AUX", "_NEVER_TRIED_IT",
              "_INTEREST_VERB_WRITER", "_INTEREST_VERB_OTHER", "_INTEREST_VERB", "_DESIRE_VERB", "_WANT_VERB",
              "_WANT_OBJECT_PREFIX", "_CERT_NOUN", "_PERSON_NOUN_MENTION_ES", "_PERSON_NOUN_MENTION_EN",
              "_PERSON_NOUN_SINGULAR_ES", "_PERSON_NOUN_SINGULAR_EN", "_PERSON_NOUN_PLURAL_ES", "_PERSON_NOUN_PLURAL_EN",
              "_THIRD_PERSON_VERB", "_CERT_LEVEL", "_HOLD_VERB_WRITER_ES", "_HOLD_VERB_OTHER_ES", "_HOLD_VERB_EN",
              "_HOLDS_WRITER", "_HOLDS_OTHER_PERSON", "_ADDITION_CUE", "_QUE_CONJUNCION", "_OTHER_PERSON_SUBJECT"}


def patrones(valor):
    if isinstance(valor, re.Pattern):
        return [valor]
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, dict):
        out = []
        for v in valor.values():
            out += patrones(v)
        return out
    if isinstance(valor, (list, tuple)):
        out = []
        for v in valor:
            if isinstance(v, (re.Pattern, str)):
                out.append(v)
            elif isinstance(v, (list, tuple)) and v and isinstance(v[0], (re.Pattern, str)):
                out.append(v[0] if not (isinstance(v[0], str) and len(v) > 1 and isinstance(v[1], str)) else v[1])
        return out
    return []


def casa(p, texto):
    try:
        if isinstance(p, re.Pattern):
            return bool(p.search(texto))
        return bool(re.search(p, texto, re.IGNORECASE))
    except re.error:
        return False


msgs = list(dict.fromkeys(f["msg"] for f in comun.corpus()))
res = {}
for g in inventario():
    if g["nombre"] in FRAGMENTOS:
        res[f"{g['fichero']}:{g['linea']}"] = {"nombre": g["nombre"], "fragmento": True}
        continue
    mod = importlib.import_module(g["fichero"][:-3].replace("/", "."))
    valor = getattr(mod, g["nombre"], None)
    if valor is None:
        for v in vars(mod).values():
            if isinstance(v, type) and v.__module__ == mod.__name__ and g["nombre"] in vars(v):
                valor = vars(v)[g["nombre"]]
    ps = patrones(valor) if valor is not None else []
    if not ps:
        continue  # local: sale de la traza
    hits = [i for i, m in enumerate(msgs)
            if any(casa(p, m.lower()) or casa(p, strip_accents(m.lower())) for p in ps)]
    res[f"{g['fichero']}:{g['linea']}"] = {"nombre": g["nombre"], "mensajes": len(hits),
                                          "ejemplos": [msgs[i][:110] for i in hits[:4]], "idx": hits}
(comun.OUT / "parte6.json").write_text(json.dumps({"mensajes": len(msgs), "grupos": res}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
for k, v in sorted(res.items(), key=lambda kv: -kv[1].get("mensajes", -1)):
    if "mensajes" in v:
        print(f"{v['mensajes']:4} {k:48} {v['nombre'][:34]:34} | {(v['ejemplos'][0] if v['ejemplos'] else '')[:60]}")
