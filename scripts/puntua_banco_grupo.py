"""CALN-2 (27-oct): puntúa el banco de grupos por código, sin juez, con el ESTADO final de cada diálogo.

    ENV_FILE=.env.dev python -m scripts.reproducir_juez_pre --banco docs/robustness/caln/banco-grupo.json --reps 2 \\
        --out <salida>.jsonl                       # A = PRE (sin --codigo-local) o B (con --codigo-local)
    python -m scripts.puntua_banco_grupo <salida>.jsonl [--banco docs/robustness/caln/banco-grupo.json]

El grupo se lee en términos que valen antes y después del rediseño (docs/robustness/caln/diseno-caln2-grupo.md):
`total` (cuántos son), `decididos` (personas con actividad elegida, por actividad), `sin_decidir`, `edades` (las dichas
están todas) y `alguno_mas_de_2` (alguien certificado que lleva más de 2 años sin bucear). Lo que el caso no trae no
se mira. `pregunta` / `no_pregunta`: la pregunta de la reserva que queda pendiente al final (paso 3: se pregunta por
quien no ha elegido, y solo por él).
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANCO = ROOT / "docs/robustness/caln/banco-grupo.json"


def grupo_del_estado(estado: dict) -> dict:
    """El grupo, leído del estado de hoy (después del rediseño, del adaptador que lo deriva de la lista de personas)."""
    total = estado.get("detected_group_size")
    reparto = dict(estado.get("detected_group_allocation") or {})
    if not reparto and estado.get("detected_activity") and total:
        reparto = {estado["detected_activity"]: total}
    decididos = {a: n for a, n in reparto.items() if a != "undecided" and isinstance(n, int) and n > 0}
    sin_decidir = reparto.get("undecided") or estado.get("pending_undecided_qty") or 0
    if not sin_decidir and isinstance(total, int) and total > sum(decididos.values()) and decididos:
        sin_decidir = total - sum(decididos.values())
    return {
        "total": total,
        "decididos": decididos,
        "sin_decidir": sin_decidir,
        "edades": sorted(estado.get("detected_ages") or []),
        "alguno_mas_de_2": bool(estado.get("last_dive_over_2_years") or estado.get("acompanante_certificado_inactivo")),
        "pregunta": estado.get("core_pending_slot"),
    }


def fallos(esperado: dict, leido: dict) -> list[str]:
    """Lo que no cuadra entre lo esperado del caso y lo leído del estado."""
    malos = []
    for campo, valor in esperado.items():
        if campo == "edades":
            if not set(valor) <= set(leido["edades"]):
                malos.append(f"edades {leido['edades']} (esperaba {valor})")
        elif campo == "no_decididos":
            # «No asumir la actividad» (decisión de Gadea): estas actividades no las eligió nadie.
            asumidas = [a for a in valor if leido["decididos"].get(a)]
            if asumidas:
                malos.append(f"asume {asumidas} sin que lo elija")
        elif campo == "no_pregunta":
            if leido["pregunta"] == valor:
                malos.append(f"pregunta {valor!r}")
        elif leido.get(campo) != valor:
            malos.append(f"{campo} {leido.get(campo)!r} (esperaba {valor!r})")
    return malos


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("salida", help="el .jsonl de reproducir_juez_pre --banco")
    ap.add_argument("--banco", default=str(BANCO))
    args = ap.parse_args()
    casos = {d["id"]: d["grupo"] for d in json.loads(Path(args.banco).read_text(encoding="utf-8"))["dialogos"]}
    ultimo: dict[tuple[str, int], dict] = {}
    for linea in Path(args.salida).read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        fila = json.loads(linea)
        clave = (fila["dialogo"], fila.get("rep", 0))
        if clave not in ultimo or fila["turn"] >= ultimo[clave]["turn"]:
            ultimo[clave] = fila
    bien = total = 0
    por_caso = collections.defaultdict(list)
    for (dialogo, rep), fila in sorted(ultimo.items()):
        if dialogo not in casos:
            continue
        malos = fallos(casos[dialogo], grupo_del_estado(fila.get("estado") or {}))
        por_caso[dialogo].append(malos)
        total += 1
        bien += not malos
    for dialogo, reps in por_caso.items():
        ok = sum(not m for m in reps)
        detalle = "; ".join(sorted({x for m in reps for x in m}))
        print(f"  {dialogo:40} {ok}/{len(reps)}" + (f"  {detalle}" if detalle else ""))
    print(f"banco de grupos: {bien}/{total} bien ({len(por_caso)} casos)")


if __name__ == "__main__":
    main()
