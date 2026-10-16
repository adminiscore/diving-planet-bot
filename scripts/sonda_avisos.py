"""CAL-A5: ver, DENTRO de PRE, por qué el código elige (o no) cada aviso en un turno.

Reproduce los turnos de los casos del banco con el bot real (como `banco_fallos medir`, sin juez: no gasta el
verificador) y, del ÚLTIMO turno, imprime lo que decide la selección de avisos:

- los HECHOS del estado (actividad, origen, nacionalidad, zona, inactividad) con los que se eligen;
- los DOCUMENTOS que trajo la búsqueda, en su orden, con su fuente, su clave y sus temas;
- los TEMAS que salen de ahí y los AVISOS elegidos.

Con eso se ajusta la REGLA (qué señal vale como "de qué va la pregunta"), no el caso.

    ENV_FILE=.env.dev python -m scripts.sonda_avisos --ids cal-32,cal-47,cal-48 --codigo-local
    ENV_FILE=.env.dev python -m scripts.sonda_avisos --tarea CAL-A --codigo-local --out sonda.json

Coste: una conversación por caso (céntimos). La cuenta de OpenAI es la de PRE.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANCO = ROOT / "docs/robustness/cal/banco-fallos.json"

_REMOTO = r'''
import asyncio, json
from src.agents import rag_agent, supervisor
from src.config import settings
from src.flows import avisos as av
from src.flows.state import ConversationState
CASOS = json.loads(CASOS_JSON)
for _f in FLAGS:
    setattr(settings, _f, True)

ultima_busqueda = []
_buscar = rag_agent.search_knowledge_base
async def _spy_buscar(query, lang="es", **kw):
    docs = await _buscar(query, lang=lang, **kw)
    ultima_busqueda.append({"consulta": query, "docs": [
        {"fuente": (d.get("metadata") or {}).get("source"),
         "clave": (d.get("metadata") or {}).get("key") or (d.get("metadata") or {}).get("section")
                  or (d.get("metadata") or {}).get("subtype"),
         "temas": (d.get("metadata") or {}).get("topics") or [],
         "score": round(float(d.get("score_final", d.get("score", 0)) or 0), 3)} for d in docs]})
    return docs
rag_agent.search_knowledge_base = _spy_buscar

elegidos = []
_seleccionar = av.seleccionar
def _spy_seleccionar(hechos, temas, fuentes=None):
    salida = _seleccionar(hechos, temas, fuentes)
    elegidos.append({"hechos": {k: sorted(v) if isinstance(v, set) else v for k, v in hechos.items()},
                     "temas": sorted(temas), "fuentes": sorted(fuentes or []),
                     "avisos": [a["id"] for a in salida]})
    return salida
av.seleccionar = _spy_seleccionar

async def main():
    for caso in CASOS:
        st = ConversationState(conversation_id="sonda-avisos-" + caso["id"])
        ultima_busqueda.clear(); elegidos.clear()
        reply = ""
        for i, msg in enumerate(caso["turnos"], 1):
            if i == len(caso["turnos"]):
                ultima_busqueda.clear(); elegidos.clear()
            try:
                reply = await supervisor.route_message(st, msg)
            except Exception as exc:  # noqa: BLE001
                reply = "ERROR %s: %s" % (type(exc).__name__, exc)
        print(json.dumps({"id": caso["id"], "criterio": caso["criterio"], "mensaje": caso["turnos"][-1],
                          "reply": reply, "busquedas": list(ultima_busqueda), "selecciones": list(elegidos),
                          "estado": {c: getattr(st, c, None) for c in
                                     ("location", "island", "hotel", "is_colombian", "mixed_nationality_notice",
                                      "detected_activity", "selected_service", "detected_group_allocation",
                                      "is_certified", "last_dive_over_2_years", "refresher_interested",
                                      "avisos_dados")}},
                         ensure_ascii=False, default=str), flush=True)

asyncio.run(main())
'''


def casos_del_banco(ids: list[str] | None, tarea: str | None) -> list[dict]:
    datos = json.loads(BANCO.read_text(encoding="utf-8"))
    casos = []
    for f in datos["fallos"]:
        if not f["turno"] or (ids and f["id"] not in ids) or (tarea and f.get("tarea") != tarea):
            continue
        turnos = [h["content"] for h in f["historial"] if h["role"] == "user"] + [f["mensaje_cliente"]]
        casos.append({"id": f["id"], "criterio": f["criterio"], "turnos": turnos})
    return casos


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ids", help="solo estos casos (cal-32,cal-47…)")
    ap.add_argument("--tarea", help="solo los casos de esta tarea (CAL-A…)")
    ap.add_argument("--flag", action="append", default=["avisos_condicionados"],
                    help="interruptor encendido solo en ese proceso")
    ap.add_argument("--codigo-local", action="store_true", help="con el código local (sin desplegar)")
    ap.add_argument("--out", help="JSON de salida")
    args = ap.parse_args()

    casos = casos_del_banco(args.ids.split(",") if args.ids else None, args.tarea)
    if not casos:
        raise SystemExit("ningún caso con turno para esos filtros")
    print(f"{len(casos)} casos: {', '.join(c['id'] for c in casos)}")

    from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

    codigo = subir_codigo_local() if args.codigo_local else None
    script = (f"CASOS_JSON = {json.dumps(casos, ensure_ascii=False)!r}\nFLAGS = {args.flag!r}\n{_REMOTO}")
    r = pre_ssh(docker_python({}, codigo_local=codigo), input_text=script,
                timeout=240 + 60 * sum(len(c["turnos"]) for c in casos))
    filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
    if not filas:
        raise SystemExit(f"sin salida: {(r.stderr or r.stdout)[-800:]}")
    for fila in filas:
        print("=" * 110)
        print(f"[{fila['id']}] {fila['criterio']}")
        print(f"  mensaje: {fila['mensaje'][:160]}")
        estado = {k: v for k, v in fila["estado"].items() if v not in (None, "", [], {}, False)}
        print(f"  estado: {estado}")
        for sel in fila["selecciones"]:
            hechos = {k: v for k, v in sel["hechos"].items() if v not in (None, "", [], {}, False)}
            print(f"  hechos: {hechos}")
            print(f"  temas: {sel['temas']}")
            print(f"  fuentes (primeras): {sel.get('fuentes')}")
            print(f"  AVISOS: {sel['avisos']}")
        if not fila["selecciones"]:
            print("  (el turno no pasó por el RAG: ningún aviso)")
        for b in fila["busquedas"]:
            print(f"  búsqueda: {b['consulta'][:120]}")
            for d in b["docs"][:12]:
                print(f"    {d['score']:>6} {str(d['fuente']):10} {str(d['clave'])[:34]:34} {d['temas']}")
        print(f"  respuesta: {fila['reply'][:400]}")
    if args.out:
        destino = Path(args.out)
        destino.write_text(json.dumps(filas, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\n→ {destino}")


if __name__ == "__main__":
    main()
