"""arq-0b (22-oct): nota de un banco del RAG corrido con `reproducir_juez_pre --banco ... --reps N`.

El indicador de la fase ARQ: un banco FIJO de preguntas con frases nuestras (de los tipos de fallo de G9/G10), cada una
con lo que la última respuesta debe decir (`todas`: cada fragmento, con alternativas separadas por «|») y lo que no
(`ninguno`). Se compara sin tildes ni mayúsculas. Además cuenta las invenciones: los juicios de grounding que no
pasan (`juicios[].ok` falso) en cualquier turno.

    python -m scripts.puntuar_banco_rag --banco docs/robustness/arq/banco-rag.json --run <salida.jsonl>
    python -m scripts.puntuar_banco_rag --banco ... --run A.jsonl --run B.jsonl     # A frente a B

Da, por ejecución: diálogos que pasan (de diálogos × repeticiones), fragmentos cumplidos, invenciones y diálogos
constantes (mismo resultado en todas las repeticiones), y el desglose por tipo.
"""
import argparse
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path


def _n(texto: str) -> str:
    return unicodedata.normalize("NFKD", (texto or "").lower()).encode("ascii", "ignore").decode()


def _cumple(fragmento: str, respuesta: str) -> bool:
    return any(_n(alt.strip()) in respuesta for alt in fragmento.split("|") if alt.strip())


def puntuar(banco: dict, filas: list[dict]) -> dict:
    por_dialogo = defaultdict(lambda: defaultdict(list))
    for f in filas:
        por_dialogo[f["dialogo"]][f["rep"]].append(f)
    total = defaultdict(lambda: {"pasan": 0, "casos": 0, "frag_ok": 0, "frag": 0, "inventa": 0, "constantes": 0,
                                 "dialogos": 0})
    detalle = []
    for d in banco["dialogos"]:
        reps = por_dialogo.get(d["id"], {})
        resultados = []
        for _, turnos in sorted(reps.items()):
            turnos = sorted(turnos, key=lambda t: t["turn"])
            ultima = _n(turnos[-1].get("reply") or "")
            faltan = [x for x in d.get("todas", []) if not _cumple(x, ultima)]
            sobran = [x for x in d.get("ninguno", []) if _cumple(x, ultima)]
            inventa = sum(1 for t in turnos for j in (t.get("juicios") or []) if not j.get("ok", True))
            ok = not faltan and not sobran and not inventa
            resultados.append(ok)
            for clave in ("_total", d.get("tipo", "?")):
                t = total[clave]
                t["casos"] += 1
                t["pasan"] += ok
                t["frag"] += len(d.get("todas", [])) + len(d.get("ninguno", []))
                t["frag_ok"] += len(d.get("todas", [])) - len(faltan) + len(d.get("ninguno", [])) - len(sobran)
                t["inventa"] += inventa
            detalle.append((d["id"], ok, faltan, sobran, inventa))
        if resultados:
            for clave in ("_total", d.get("tipo", "?")):
                total[clave]["dialogos"] += 1
                total[clave]["constantes"] += len(set(resultados)) == 1
    return {"total": total, "detalle": detalle}


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--banco", required=True)
    p.add_argument("--run", action="append", required=True, help="jsonl de reproducir_juez_pre (repetible: A, B…)")
    p.add_argument("--detalle", action="store_true", help="enseña cada diálogo y repetición que no pasa")
    args = p.parse_args(argv)
    banco = json.loads(Path(args.banco).read_text(encoding="utf-8"))
    for run in args.run:
        filas = [json.loads(linea) for linea in Path(run).read_text(encoding="utf-8").splitlines() if linea.strip()]
        res = puntuar(banco, filas)
        t = res["total"]["_total"]
        print(f"== {run}")
        print(f"   pasan {t['pasan']}/{t['casos']} ({100 * t['pasan'] / max(t['casos'], 1):.1f} %) · fragmentos "
              f"{t['frag_ok']}/{t['frag']} · invenciones {t['inventa']} · constantes {t['constantes']}/{t['dialogos']}")
        for tipo, v in sorted(res["total"].items()):
            if tipo != "_total":
                print(f"   {tipo:12} pasan {v['pasan']:3}/{v['casos']:<3} fragmentos {v['frag_ok']}/{v['frag']}"
                      f" invenciones {v['inventa']}")
        if args.detalle:
            for did, ok, faltan, sobran, inventa in res["detalle"]:
                if not ok:
                    print(f"   NO {did}: faltan {faltan} · sobran {sobran} · invenciones {inventa}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
