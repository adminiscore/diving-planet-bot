"""ex-10 (15-oct): el resultado de una ronda del juez, partido por grupos del golden.

El resumen del juez da el total; las metas de la fase EX se miden por partes: los diálogos REALES (sacados de
WhatsApp, `source.kind == "whatsapp"`) frente a los sintéticos, y el examen OCULTO (`suite == "oculto"`) frente a lo
visible. Mismas cuentas que `summary` del juez: criterios cumplidos sobre juzgados (sin los "no aplica" ni los
"revisar"), y un diálogo pasa si no tiene ningún "no_cumple" (comprobado con 2026-10-08-luna-visible: 92,8 %, 61/95;
reales 88,7 %, 24/52).

    python -m scripts.resumen_por_grupo docs/robustness/golden-set/results/<ronda>__gpt-5-mini-medium.json
    python -m scripts.resumen_por_grupo A.json B.json        # dos rondas lado a lado (solo los diálogos de las dos)
"""
import json
import sys
from pathlib import Path

GOLDEN = Path(__file__).resolve().parent.parent / "docs/robustness/golden-set/golden-dialogues.json"


def _golden() -> dict:
    datos = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return {d["id"]: d for d in (datos.get("dialogues") if isinstance(datos, dict) else datos)}


def grupo(dialogo: dict) -> tuple[str, str]:
    suite = "oculto" if dialogo.get("suite") == "oculto" else "visible"
    fuente = dialogo.get("source") or {}
    origen = "real" if isinstance(fuente, dict) and fuente.get("kind") == "whatsapp" else "sintético"
    return suite, origen


def cuentas(resultado: dict, ids: set | None = None) -> dict:
    golden = _golden()
    tabla: dict = {}
    for d in resultado.get("dialogues") or []:
        if ids is not None and d["id"] not in ids:
            continue
        veredictos = [c.get("verdict") for c in d.get("criteria") or []]
        juzgados = [v for v in veredictos if v in ("cumple", "no_cumple", "revisar")]
        fallos = sum(v == "no_cumple" for v in juzgados)
        revisar = sum(v == "revisar" for v in juzgados)
        suite, origen = grupo(golden.get(d["id"], {}))
        for clave in ((suite, origen), (suite, "todos"), ("todos", origen), ("todos", "todos")):
            t = tabla.setdefault(clave, {"dialogos": 0, "pasan": 0, "juzgados": 0, "fallos": 0, "revisar": 0})
            t["dialogos"] += 1
            t["pasan"] += fallos == 0  # como el juez: "revisar" no cuenta como fallo del diálogo
            t["juzgados"] += len(juzgados) - revisar
            t["fallos"] += fallos
            t["revisar"] += revisar
    return tabla


def _fila(t: dict | None) -> str:
    if not t:
        return f"{'—':>28}"
    pct = 100 * (t["juzgados"] - t["fallos"]) / t["juzgados"] if t["juzgados"] else 0.0
    return f"{pct:5.1f} % · {t['pasan']:>3}/{t['dialogos']:<3} sin fallos · revisar {t['revisar']}"


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rondas = [json.loads(Path(p).read_text(encoding="utf-8")) for p in argv]
    ids = None
    if len(rondas) == 2:
        ids = {d["id"] for d in rondas[0]["dialogues"]} & {d["id"] for d in rondas[1]["dialogues"]}
    tablas = [cuentas(r, ids) for r in rondas]
    print(f"{'grupo':<22}" + "".join(f"{Path(p).name[:40]:<44}" for p in argv))
    for clave in (("todos", "todos"), ("visible", "todos"), ("visible", "real"), ("visible", "sintético"),
                  ("oculto", "todos"), ("oculto", "real"), ("oculto", "sintético"), ("todos", "real")):
        if not any(clave in t for t in tablas):
            continue
        print(f"{clave[0] + ' / ' + clave[1]:<22}" + "".join(f"{_fila(t.get(clave)):<44}" for t in tablas))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
