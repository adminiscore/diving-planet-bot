"""Mapa de Coral: genera los datos del mapa de arquitectura desde el CÓDIGO (29-sep).

Junta lo que sale del código con los textos curados de `docs/arquitectura/componentes.json`:
- el grafo LangGraph real (`orchestration/graph.py`) y el subgrafo de la reserva (`booking_agent.py`);
- los interruptores booleanos y los ajustes de modelo de `settings`, con lo que fija PRE (`docker-compose.vps.yml`);
- los tiempos de la foto de ronda más reciente (`docs/robustness/snapshots/*.json`: p50/p95 por nodo, llamadas por
  modelo, reparto del enrutador);
y escribe `docs/arquitectura/arquitectura.json`, que lee el artifact "Mapa de Coral".

Valida (y sale con error) si un nodo del grafo no tiene descripción, si un `donde` apunta a un fichero o símbolo
que no existe, o si se cita un interruptor o modelo que no está en `settings`. Si la ESTRUCTURA cambió (piezas,
flechas, interruptores, modelos; no los tiempos) guarda una versión en `docs/arquitectura/historial/`.

    ENV_FILE=.env.ci python -m scripts.arquitectura           # genera y guarda historial si cambió
    ENV_FILE=.env.ci python -m scripts.arquitectura --check   # solo valida (lo usa el test)

Después, republicar el mapa en la misma URL (ver `docs/project-history/session-handoff.md`).
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault("ENV_FILE", ".env.ci")

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "docs" / "arquitectura"
CURADO = DIR / "componentes.json"
LOGOS = DIR / "logos.json"
SALIDA = DIR / "arquitectura.json"
HISTORIAL = DIR / "historial"
SNAPSHOTS = ROOT / "docs" / "robustness" / "snapshots"
_EXTREMOS = ("__start__", "__end__")
_MARCA_PROVEEDOR = {"OpenAI": "openai", "OpenRouter": "openrouter"}


def grafos() -> dict[str, dict]:
    """Nodos y aristas reales: el grafo principal (vista general) y el subgrafo de la reserva."""
    from src.agents.booking_agent import _build_booking_subgraph
    from src.orchestration.graph import get_compiled_graph

    out = {}
    for vista, g in (("general", get_compiled_graph().get_graph()), ("booking", _build_booking_subgraph().get_graph())):
        out[vista] = {"nodos": [n for n in g.nodes if n not in _EXTREMOS],
                      "aristas": [(e.source, e.target, bool(e.conditional)) for e in g.edges]}
    return out


def ajustes() -> tuple[dict, dict, dict]:
    """(interruptores {nombre: valor en código}, modelos {ajuste: valor en código}, lo que fija PRE)."""
    from scripts.check_deploy import expected_from_compose
    from src.config import Settings

    campos = Settings.model_fields
    bools = {k: f.default for k, f in campos.items() if f.annotation is bool}
    modelos = {k: f.default for k, f in campos.items() if k.endswith("_model")}
    return bools, modelos, expected_from_compose()


def _simbolo_existe(donde: str) -> bool:
    fichero, _, simbolo = donde.partition(":")
    ruta = ROOT / fichero
    if not ruta.is_file():
        return False
    if not simbolo:
        return True
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    patron = rf"^\s*(?:async\s+def|def|class)\s+{re.escape(simbolo)}\b|^{re.escape(simbolo)}\s*[:=]"
    return re.search(patron, texto, re.MULTILINE) is not None


def validar(curado: dict, g: dict, bools: dict, modelos: dict) -> list[str]:
    errores = []
    comps = {c["id"]: c for c in curado["componentes"]}
    if len(comps) != len(curado["componentes"]):
        errores.append("hay ids de componente repetidos")
    for vista, datos in g.items():
        descritos = {c.get("nodo_grafo") for c in curado["componentes"] if c["vista"] == vista}
        for nodo in datos["nodos"]:
            if nodo not in descritos:
                errores.append(f"el nodo '{nodo}' del grafo ({vista}) no tiene descripción: "
                               f"añádelo a docs/arquitectura/componentes.json con \"nodo_grafo\": \"{nodo}\"")
    for c in curado["componentes"]:
        if c["vista"] not in curado["vistas"]:
            errores.append(f"{c['id']}: vista '{c['vista']}' desconocida")
        if c.get("zoom") and c["zoom"] not in curado["vistas"]:
            errores.append(f"{c['id']}: zoom a una vista que no existe ('{c['zoom']}')")
        if c.get("nodo_grafo") and c["nodo_grafo"] not in g.get(c["vista"], {}).get("nodos", []):
            errores.append(f"{c['id']}: el nodo '{c['nodo_grafo']}' ya no está en el grafo ({c['vista']})")
        if c.get("donde") and not _simbolo_existe(c["donde"]):
            errores.append(f"{c['id']}: no existe {c['donde']}")
        for m in c.get("modelos", []):
            if m not in modelos:
                errores.append(f"{c['id']}: el ajuste de modelo '{m}' no está en settings")
        for f in c.get("interruptores", []):
            if f not in bools:
                errores.append(f"{c['id']}: el interruptor '{f}' no está en settings")
    for a in curado["aristas"]:
        for extremo in (a["de"], a["a"]):
            if extremo not in comps:
                errores.append(f"flecha {a['de']} → {a['a']}: no existe '{extremo}'")
    for f in curado.get("sin_efecto", {}):
        if f not in bools:
            errores.append(f"sin_efecto: '{f}' no está en settings")
    textos = curado.get("interruptores", {})
    for f in bools:
        if f not in textos:
            errores.append(f"el interruptor '{f}' no tiene nombre ni frase en llano: añádelo a \"interruptores\" en "
                           "docs/arquitectura/componentes.json")
    for f, info in textos.items():
        if f not in bools:
            errores.append(f"interruptores: '{f}' ya no está en settings")
        elif info.get("area") not in curado.get("areas", []):
            errores.append(f"interruptores.{f}: zona '{info.get('area')}' no está en \"areas\"")
    logos = json.loads(LOGOS.read_text(encoding="utf-8"))["logos"] if LOGOS.exists() else {}
    for c in curado["componentes"]:
        if c.get("marca") and c["marca"] not in logos:
            errores.append(f"{c['id']}: no hay logo '{c['marca']}' en docs/arquitectura/logos.json")
    for c in curado["componentes"]:
        if c.get("capa_de") and c["capa_de"] not in {x["id"] for x in curado["componentes"] if x["vista"] == c["vista"]}:
            errores.append(f"{c['id']}: capa_de '{c['capa_de']}' no está en su vista")
    for vista, mapa in curado.get("grafo", {}).items():
        for extremo, cid in mapa.items():
            if cid not in comps:
                errores.append(f"grafo.{vista}.{extremo}: no existe '{cid}'")
    return errores


def ultima_foto() -> tuple[Path | None, dict]:
    fotos = []
    for p in SNAPSHOTS.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("nodes"):
            fotos.append((str(d.get("run_at") or d.get("taken_at") or ""), p, d))
    if not fotos:
        return None, {}
    _, p, d = max(fotos, key=lambda x: (x[0], x[1].name))
    return p, d


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def construir(curado: dict, g: dict, bools: dict, modelos: dict, pre: dict, foto_path: Path | None, foto: dict) -> dict:
    nodos_foto = foto.get("nodes", {})
    llamadas = foto.get("models", {}) or {}
    comps = []
    for c in curado["componentes"]:
        c = dict(c)
        c["modelos"] = [{"ajuste": m, "codigo": modelos[m], "pre": pre.get(m, modelos[m])} for m in c.get("modelos", [])]
        c["interruptores"] = [{"nombre": f, "titulo": curado["interruptores"][f]["titulo"], "codigo": bools[f],
                               "pre": bool(pre.get(f, bools[f])), "sin_efecto": f in curado.get("sin_efecto", {})}
                              for f in c.get("interruptores", [])]
        # Logo: el del servicio que usa la pieza; si no se dice y llama a un modelo, el de su proveedor.
        if not c.get("marca") and c["modelos"]:
            c["marca"] = _MARCA_PROVEEDOR.get("OpenRouter" if "/" in str(c["modelos"][0]["pre"]) else "OpenAI")
        nodo = c.get("nodo_grafo")
        if nodo and nodo in nodos_foto:
            c["tiempos"] = nodos_foto[nodo]
        comps.append(c)

    # Aristas: las del grafo real (con sus extremos traducidos) + las curadas, sin duplicar.
    por_nodo = {(c["vista"], c.get("nodo_grafo")): c["id"] for c in curado["componentes"] if c.get("nodo_grafo")}
    aristas, vistas_de = [], set()
    for vista, datos in g.items():
        extremos = curado.get("grafo", {}).get(vista, {})
        for src, dst, cond in datos["aristas"]:
            de = extremos.get(src) if src in _EXTREMOS else por_nodo.get((vista, src))
            a = extremos.get(dst) if dst in _EXTREMOS else por_nodo.get((vista, dst))
            if de and a and (de, a) not in vistas_de:
                vistas_de.add((de, a))
                aristas.append({"de": de, "a": a, "origen": "grafo", "estilo": "condicional" if cond else "normal",
                                "etiqueta": "si toca" if cond else ("sale" if dst == "__end__" else "")})
    for a in curado["aristas"]:
        clave = (a["de"], a["a"])
        previa = next((x for x in aristas if (x["de"], x["a"]) == clave), None)
        if previa:
            previa.update({k: v for k, v in a.items() if k not in ("grafo",)})
            continue
        vistas_de.add(clave)
        aristas.append({**{k: v for k, v in a.items() if k != "grafo"}, "origen": "curada", "estilo": a.get("estilo", "normal")})
    vista_de = {c["id"]: c["vista"] for c in comps}
    for a in aristas:
        a["vista"] = vista_de[a["de"]]

    usados_f: dict[str, list[str]] = {}
    usados_m: dict[str, list[str]] = {}
    for c in comps:
        for f in c["interruptores"]:
            usados_f.setdefault(f["nombre"], []).append(c["id"])
        for m in c["modelos"]:
            usados_m.setdefault(m["ajuste"], []).append(c["id"])
    interruptores = [{"nombre": k, **curado["interruptores"][k], "codigo": v, "pre": bool(pre.get(k, v)),
                      "fijado_en_pre": k in pre, "usado_por": usados_f.get(k, []),
                      "sin_efecto": curado.get("sin_efecto", {}).get(k)}
                     for k, v in sorted(bools.items())]
    modelos_out = [{"ajuste": k, "codigo": v, "pre": pre.get(k, v), "usado_por": usados_m.get(k, []),
                    "proveedor": "OpenRouter" if "/" in str(pre.get(k, v)) else "OpenAI",
                    "llamadas_ultima_ronda": llamadas.get(pre.get(k, v))} for k, v in sorted(modelos.items())]

    ronda = {}
    if foto:
        calidad = foto.get("quality") or {}
        ronda = {"etiqueta": foto.get("label"), "run_at": foto.get("run_at"), "fichero": foto_path.name if foto_path else None,
                 "commit": foto.get("commit"), "por_tipo": foto.get("by_type"), "enrutador": foto.get("router"),
                 "cliente": foto.get("client_latency"), "llamadas_por_modelo": llamadas,
                 "calidad": {k: calidad.get(k) for k in ("criteria_pass_pct", "dialogues_passed", "dialogues", "model")
                             if k in calidad} or None}
    return {
        "meta": {"generado": datetime.now(UTC).isoformat(timespec="seconds"),
                 "commit": _git("rev-parse", "--short", "HEAD"), "rama": _git("rev-parse", "--abbrev-ref", "HEAD")},
        "vistas": curado["vistas"], "areas": curado.get("areas", []), "componentes": comps, "aristas": aristas,
        "interruptores": interruptores, "modelos": modelos_out, "ronda": ronda,
        "pesos_fuente": curado.get("pesos_fuente"),
    }


def estructura(datos: dict) -> dict:
    """Lo que cuenta como 'cambio de arquitectura' (sin tiempos ni fechas)."""
    return {
        "componentes": sorted([{"id": c["id"], "vista": c["vista"], "titulo": c["titulo"], "tipo": c["tipo"],
                                "nodo_grafo": c.get("nodo_grafo"), "modelos": [m["ajuste"] for m in c["modelos"]],
                                "interruptores": [f["nombre"] for f in c["interruptores"]]} for c in datos["componentes"]],
                              key=lambda x: x["id"]),
        "aristas": sorted([[a["de"], a["a"], a.get("estilo", "normal")] for a in datos["aristas"]]),
        "interruptores": {f["nombre"]: {"codigo": f["codigo"], "pre": f["pre"]} for f in datos["interruptores"]},
        "modelos": {m["ajuste"]: {"codigo": m["codigo"], "pre": m["pre"]} for m in datos["modelos"]},
    }


def cambios(antes: dict, despues: dict) -> dict:
    ca = {c["id"]: c for c in antes.get("componentes", [])}
    cd = {c["id"]: c for c in despues["componentes"]}
    aa = {tuple(a[:2]) for a in antes.get("aristas", [])}
    ad = {tuple(a[:2]) for a in despues["aristas"]}
    fa, fd = antes.get("interruptores", {}), despues["interruptores"]
    ma, md = antes.get("modelos", {}), despues["modelos"]
    return {
        "piezas_nuevas": sorted(set(cd) - set(ca)), "piezas_quitadas": sorted(set(ca) - set(cd)),
        "flechas_nuevas": sorted(map(list, ad - aa)), "flechas_quitadas": sorted(map(list, aa - ad)),
        "interruptores": sorted(k for k in set(fa) | set(fd) if fa.get(k) != fd.get(k)),
        "modelos": sorted(k for k in set(ma) | set(md) if ma.get(k) != md.get(k)),
    }


def guardar_historial(datos: dict) -> str | None:
    HISTORIAL.mkdir(parents=True, exist_ok=True)
    indice_path = HISTORIAL / "indice.json"
    indice = json.loads(indice_path.read_text(encoding="utf-8")) if indice_path.exists() else {"versiones": []}
    est = estructura(datos)
    previa = {}
    if indice["versiones"]:
        previa = json.loads((HISTORIAL / indice["versiones"][-1]["fichero"]).read_text(encoding="utf-8"))["estructura"]
        if previa == est:
            return None
    fecha = datos["meta"]["generado"][:10]
    nombre = f"{fecha}-{datos['meta']['commit'] or 'local'}.json"
    delta = cambios(previa, est) if previa else None
    (HISTORIAL / nombre).write_text(json.dumps({"meta": datos["meta"], "estructura": est, "cambios": delta},
                                               ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    indice["versiones"] = [v for v in indice["versiones"] if v["fichero"] != nombre]
    indice["versiones"].append({"fichero": nombre, "fecha": fecha, "commit": datos["meta"]["commit"], "cambios": delta})
    indice_path.write_text(json.dumps(indice, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return nombre


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="solo validar, sin escribir nada")
    args = ap.parse_args()

    curado = json.loads(CURADO.read_text(encoding="utf-8"))
    g = grafos()
    bools, modelos, pre = ajustes()
    errores = validar(curado, g, bools, modelos)
    if errores:
        print("✗ El mapa no está al día con el código:")
        for e in errores:
            print(f"  - {e}")
        return 1
    if args.check:
        print(f"✓ Mapa al día: {len(curado['componentes'])} piezas, {sum(len(v['nodos']) for v in g.values())} nodos del grafo descritos")
        return 0
    foto_path, foto = ultima_foto()
    datos = construir(curado, g, bools, modelos, pre, foto_path, foto)
    SALIDA.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    version = guardar_historial(datos)
    print(f"✓ {SALIDA.relative_to(ROOT)}: {len(datos['componentes'])} piezas, {len(datos['aristas'])} flechas, "
          f"{len(datos['interruptores'])} interruptores, tiempos de {foto_path.name if foto_path else '(sin foto)'}")
    print(f"  historial: {'nueva versión ' + version if version else 'sin cambios de estructura'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
