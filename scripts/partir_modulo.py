"""Partir un módulo moviendo bloques de nivel superior tal cual (lat-9 paso 4, Gadea #2077).

    python scripts/partir_modulo.py docs/robustness/lat/partir/plan-core.json

plan.json: {"origen": "src/agents/conversational_core.py", "paquete": "src.agents.nucleo",
            "modulos": [{"nombre": "huecos", "doc": "...", "capa": "arriba"|"abajo", "nombres": [...]}, ...]}

- Cada bloque es el nodo de nivel superior con los comentarios que tiene justo encima; se copia byte a byte.
- "arriba": el módulo no depende del de origen; el origen lo importa al principio (y lo re-exporta).
- "abajo": el módulo importa del de origen lo que se queda allí; el origen lo importa al final (como las fases).
- Las importaciones de cabecera del origen que use cada bloque se copian; las que dejen de usarse en el origen las quita
  `ruff --fix` después (solo F401 de la cabecera).
"""
import ast
import json
import sys
from pathlib import Path

plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
ruta = Path(plan["origen"])
crudo = ruta.read_bytes()
nl = "\r\n" if b"\r\n" in crudo else "\n"
texto = crudo.decode("utf-8").replace("\r\n", "\n")
lineas = texto.split("\n")
arbol = ast.parse(texto)
modulo_origen = plan["origen"].removesuffix(".py").replace("/", ".")


def nombres_de(nodo):
    if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [nodo.name]
    if isinstance(nodo, (ast.Assign, ast.AnnAssign)):
        objetivos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
        return [t.id for t in objetivos if isinstance(t, ast.Name)]
    return []


# Cabecera: las importaciones de nivel superior antes del primer def/asignación (sin __future__).
cabecera = {}  # nombre ligado -> línea de import que lo da
for nodo in arbol.body:
    if isinstance(nodo, ast.Import):
        for a in nodo.names:
            cabecera[(a.asname or a.name).split(".")[0]] = f"import {a.name}" + (f" as {a.asname}" if a.asname else "")
    elif isinstance(nodo, ast.ImportFrom) and nodo.module != "__future__" and nodo.col_offset == 0:
        for a in nodo.names:
            cabecera[a.asname or a.name] = (nodo.module, a.name, a.asname)

bloques = []  # (ini0, fin0, nombres, nodo)
anterior_fin = 0
for nodo in arbol.body:
    ini = nodo.lineno - 1
    if getattr(nodo, "decorator_list", None):
        ini = min(d.lineno for d in nodo.decorator_list) - 1
    # sube por los comentarios pegados (sin línea en blanco de por medio)
    j = ini
    while j - 1 >= anterior_fin and lineas[j - 1].lstrip().startswith("#"):
        j -= 1
    bloques.append((j, nodo.end_lineno, nombres_de(nodo), nodo))
    anterior_fin = nodo.end_lineno

destino = {}
for m in plan["modulos"]:
    for n in m["nombres"]:
        destino[n] = m["nombre"]
definidos = {n for _, _, ns, _ in bloques for n in ns}
faltan = [n for n in destino if n not in definidos]
assert not faltan, f"no están en el origen: {faltan}"

por_modulo = {m["nombre"]: [] for m in plan["modulos"]}
quitar = set()
for ini, fin, ns, nodo in bloques:
    sitios = {destino.get(n) for n in ns}
    if not ns or sitios == {None}:
        continue
    assert len(sitios) == 1 and None not in sitios, f"bloque partido entre módulos: {ns}"
    por_modulo[sitios.pop()].append((ini, fin, ns, nodo))
    quitar.update(range(ini, fin))

capa = {m["nombre"]: m["capa"] for m in plan["modulos"]}
se_quedan = definidos - set(destino)
salida = {}
for m in plan["modulos"]:
    nombre = m["nombre"]
    usados = set()
    for _, _, _, nodo in por_modulo[nombre]:
        usados |= {x.id for x in ast.walk(nodo) if isinstance(x, ast.Name)}
    propios = {n for _, _, ns, _ in por_modulo[nombre] for n in ns}
    imports_std, imports_from = set(), {}
    for u in sorted(usados - propios - {"logger"}):
        if u in destino:  # de otro módulo nuevo
            otro = destino[u]
            if capa[nombre] == "arriba":
                assert capa[otro] == "arriba", f"{nombre} (arriba) usa {u} de {otro} (abajo)"
            imports_from.setdefault(f"{plan['paquete']}.{otro}", set()).add(u)
        elif u in se_quedan:
            assert capa[nombre] == "abajo", f"{nombre} (arriba) usa {u}, que se queda en el origen"
            imports_from.setdefault(modulo_origen, set()).add(u)
        elif u in cabecera:
            c = cabecera[u]
            if isinstance(c, str):
                imports_std.add(c)
            else:
                mod, real, alias = c
                imports_from.setdefault(mod, set()).add(real + (f" as {alias}" if alias else ""))
    if "logger" in usados and "logger" not in propios and "logger" in se_quedan:
        imports_std.add("import logging")
        logger_propio = True
    else:
        logger_propio = False
    partes = [f'"""{m["doc"]}"""', "", "from __future__ import annotations", ""]
    partes += sorted(imports_std)
    if imports_std:
        partes.append("")
    for mod in sorted(imports_from):
        ns = sorted(imports_from[mod])
        if not ns:
            continue
        partes.append(f"from {mod} import (")
        partes += [f"    {n}," for n in ns]
        partes.append(")")
    partes.append("")
    if logger_propio:
        partes += ['logger = logging.getLogger("uvicorn.error")', ""]
    # Tramos: bloques seguidos en el origen (sin otro bloque en medio) se copian enteros, con su espaciado.
    indice = {b[0]: k for k, b in enumerate(bloques)}
    tramos = []
    for ini, fin, _, _ in sorted(por_modulo[nombre]):
        k = indice[ini]
        if tramos and tramos[-1][2] == k - 1:
            tramos[-1] = (tramos[-1][0], fin, k)
        else:
            tramos.append((ini, fin, k))
    cuerpo = []
    for ini, fin, _ in tramos:
        quitar.update(range(ini, fin))  # también lo que hay entre sus bloques (comentarios sueltos de ese tramo)
        trozo = lineas[ini:fin]
        while trozo and not trozo[0].strip():
            trozo = trozo[1:]
        cuerpo.append("\n".join(trozo))
    partes.append("\n\n\n".join(cuerpo))
    salida[nombre] = "\n".join(partes).rstrip("\n") + "\n"

# El origen sin los bloques; las líneas en blanco sobrantes se juntan (máximo dos seguidas).
quedan = [ln for i, ln in enumerate(lineas) if i not in quitar]
limpio = []
for ln in quedan:
    if not ln.strip() and len(limpio) >= 2 and not limpio[-1].strip() and not limpio[-2].strip():
        continue
    limpio.append(ln)
texto_origen = "\n".join(limpio)


def reexport(nombre, noqa):
    ns = sorted(n for _, _, nss, _ in por_modulo[nombre] for n in nss)
    return "\n".join([f"from {plan['paquete']}.{nombre} import (  # noqa: {noqa}", *[f"    {n}," for n in ns], ")"])


arriba = [m["nombre"] for m in plan["modulos"] if m["capa"] == "arriba"]
abajo = [m["nombre"] for m in plan["modulos"] if m["capa"] == "abajo"]
# arriba: tras la última importación de cabecera
ultima_import = max(n.end_lineno for n in arbol.body if isinstance(n, (ast.Import, ast.ImportFrom)) and n.col_offset == 0
                    and n.lineno < min(b[0] for b in bloques if b[2]) + 1)
marca = lineas[ultima_import - 1]
assert texto_origen.count(marca + "\n") >= 1
bloque_arriba = plan.get("comentario_arriba", "") + "\n".join(reexport(n, "F401") for n in arriba)
texto_origen = texto_origen.replace(marca + "\n", marca + "\n" + bloque_arriba + "\n", 1)
ancla = plan["ancla_abajo"]
assert texto_origen.count(ancla) == 1, "ancla de abajo"
bloque_abajo = "\n".join(reexport(n, "E402, F401") for n in abajo)
texto_origen = texto_origen.replace(ancla, ancla + bloque_abajo + "\n", 1)

for nombre, contenido in salida.items():
    Path(plan["dir"]).joinpath(f"{nombre}.py").write_bytes(contenido.replace("\n", nl).encode("utf-8"))
ruta.write_bytes(texto_origen.replace("\n", nl).encode("utf-8"))
print({n: len(c.splitlines()) for n, c in salida.items()}, "origen:", len(texto_origen.splitlines()))
