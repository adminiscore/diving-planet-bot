"""Huella de cada nombre de nivel superior (su nodo AST sin posiciones) de unos ficheros, para comprobar que partir un
módulo solo MUEVE código: python scripts/huella_ast.py salida.json fichero.py [fichero.py ...]
Con --comparar antes.json: cada nombre de antes tiene que estar, idéntico, en alguno de los ficheros de ahora."""
import ast
import json
import sys
from pathlib import Path


def huellas(ficheros):
    out = {}
    for f in ficheros:
        arbol = ast.parse(Path(f).read_text(encoding="utf-8"))
        for nodo in arbol.body:
            nombres = []
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nombres = [nodo.name]
            elif isinstance(nodo, (ast.Assign, ast.AnnAssign)):
                objetivos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
                nombres = [t.id for t in objetivos if isinstance(t, ast.Name)]
            for n in nombres:
                out.setdefault(n, []).append({"fichero": f, "ast": ast.dump(nodo, include_attributes=False)})
    return out


args = sys.argv[1:]
if args[0] == "--comparar":
    antes = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    ahora = huellas(args[2:])
    malos = 0
    for n, vs in antes.items():
        for v in vs:
            if not any(w["ast"] == v["ast"] for w in ahora.get(n, [])):
                malos += 1
                print("CAMBIA o FALTA:", n, "(antes en", v["fichero"] + ")", "ahora en", [w["fichero"] for w in ahora.get(n, [])])
    nuevos = sorted(set(ahora) - set(antes))
    print(f"{len(antes)} nombres de antes; {malos} cambian o faltan; nombres nuevos: {nuevos}")
else:
    Path(args[0]).write_text(json.dumps(huellas(args[1:]), ensure_ascii=False), encoding="utf-8")
    print("ok", args[0])
