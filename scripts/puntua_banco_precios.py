"""CALN-3 paso 0 (27-oct): puntúa el banco de precios por código, sin juez, con la ÚLTIMA respuesta de cada diálogo.

    ENV_FILE=.env.dev python -m scripts.reproducir_juez_pre --banco docs/robustness/caln/banco-precios.json --reps 2 \\
        --out <salida>.jsonl                       # A = PRE (sin --codigo-local) o B (con --codigo-local)
    ENV_FILE=.env.ci python -m scripts.puntua_banco_precios <salida>.jsonl [--banco docs/robustness/caln/banco-precios.json]

Los importes de la respuesta se buscan en el catálogo (`caln0_comprobaciones.planes_y_origenes`) y se comparan con lo
esperado del caso: `planes` (los tiene que cotizar todos), `solo_planes` (y ninguno más), `origen` ('cartagena',
'islas' o 'los_dos'), `moneda` (esa tiene que estar) y `sin_total` (sin total del grupo en el texto: decisión A1).
Una respuesta sin ningún importe del catálogo falla (el caso pide un precio). Lo que el caso no trae no se mira.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

from scripts.caln0_comprobaciones import _precios, planes_y_origenes

ROOT = Path(__file__).resolve().parent.parent
BANCO = ROOT / "docs/robustness/caln/banco-precios.json"


def fallos(esperado: dict, respuesta: str) -> list[str]:
    """Lo que no cuadra entre lo esperado del caso y los importes de la respuesta."""
    planes, origenes, monedas = planes_y_origenes(respuesta)
    if not planes:
        return ["ningún precio del catálogo"]
    malos = []
    faltan = [p for p in esperado.get("planes", []) if p not in planes]
    if faltan:
        malos.append(f"no cotiza {faltan}")
    if esperado.get("solo_planes") and planes - set(esperado.get("planes", [])):
        malos.append(f"cotiza además {sorted(planes - set(esperado['planes']))}")
    origen = esperado.get("origen")
    if origen == "los_dos" and origenes != {"cartagena", "islas"}:
        malos.append(f"un solo origen {sorted(origenes)} sin saberlo")
    elif origen in ("cartagena", "islas") and origen not in origenes:
        malos.append(f"origen {sorted(origenes)} (esperaba {origen})")
    if esperado.get("moneda") and esperado["moneda"] not in monedas:
        malos.append(f"moneda {sorted(monedas)} (esperaba {esperado['moneda']})")
    if esperado.get("sin_total") and "total_en_texto" in _precios(respuesta, None, None, False):
        malos.append("total del grupo en el texto")
    return malos


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("salidas", nargs="+", type=Path, help="JSONL de reproducir_juez_pre (A y B, por ejemplo)")
    ap.add_argument("--banco", type=Path, default=BANCO)
    args = ap.parse_args()
    esperados = {d["id"]: d.get("esperado") or {} for d in json.loads(args.banco.read_text(encoding="utf-8"))["dialogos"]}
    for salida in args.salidas:
        ultimas: dict[tuple, dict] = {}
        for linea in salida.read_text(encoding="utf-8").splitlines():
            if linea.strip():
                fila = json.loads(linea)
                clave = (fila["dialogo"], fila.get("rep"))
                if fila.get("turn", 0) >= ultimas.get(clave, {}).get("turn", -1):
                    ultimas[clave] = fila
        bien, por_dialogo = 0, collections.defaultdict(list)
        for (dialogo, rep), fila in sorted(ultimas.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
            malos = fallos(esperados.get(dialogo, {}), fila.get("reply") or "")
            bien += not malos
            por_dialogo[dialogo].append(malos)
        print(f"\n== {salida.name}: {bien}/{len(ultimas)} respuestas bien")
        for dialogo, lista in por_dialogo.items():
            marcas = " ".join("ok" if not m else "X" for m in lista)
            detalle = "; ".join(sorted({x for m in lista for x in m}))
            print(f"  {dialogo:44} {marcas:8} {detalle}")


if __name__ == "__main__":
    main()
