"""LAT-10 (27-oct, Gadea #2088): el tiempo de cada turno sin ninguna llamada en marcha.

De las .metricas de una ronda (`ronda_local_pre --metricas`): cada llamada trae `t` (cuándo empieza, desde el inicio
del turno) y `s` (cuánto dura), y el turno su `latency`. Por turno, el hueco es la latencia menos el tiempo cubierto por
alguna llamada (la unión de los intervalos, embeddings incluidos), partido en tres tramos: antes de la primera llamada,
entre llamadas y después de la última. Se reparte por tipo de turno (`turn_type`, y en los del RAG por `hechos`).

    python scripts/hueco_sin_llamadas.py docs/robustness/synthetic-runs/2026-10-26-integra5-B.metricas [otra.metricas ...]
    python scripts/hueco_sin_llamadas.py --detalle antes ronda.metricas   # los turnos con más hueco en ese tramo
    python scripts/hueco_sin_llamadas.py --por-llamada ronda.metricas     # el hueco que deja cada pieza al acabar

Ojo con las .metricas anteriores al 27-oct: la duración `s` acababa al llegar las cabeceras, y OpenRouter las manda
antes de que el modelo acabe de escribir. El «hueco» tras el extractor (~0,6 s, crece con sus tokens de salida) era el
modelo escribiendo su JSON, no tiempo sin llamadas (ver `--por-llamada`; arreglado en `observability._on_response`).

Sin red ni OpenAI.
"""
import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TRAMOS = ("antes", "entre", "despues")


def huecos(turno: dict) -> dict[str, float]:
    """{antes, entre, despues, total, cubierto} en segundos para un turno."""
    latencia = float(turno.get("latency") or 0.0)
    intervalos = sorted((float(c["t"]), float(c["t"]) + float(c["s"])) for c in turno.get("llamadas") or []
                        if c.get("t") is not None and c.get("s") is not None)
    if not intervalos:
        return {"antes": latencia, "entre": 0.0, "despues": 0.0, "total": latencia, "cubierto": 0.0}
    unidos = [list(intervalos[0])]
    for ini, fin in intervalos[1:]:
        if ini <= unidos[-1][1]:
            unidos[-1][1] = max(unidos[-1][1], fin)
        else:
            unidos.append([ini, fin])
    antes = max(0.0, unidos[0][0])
    entre = sum(max(0.0, b[0] - a[1]) for a, b in zip(unidos, unidos[1:]))
    despues = max(0.0, latencia - unidos[-1][1])
    cubierto = sum(fin - ini for ini, fin in unidos)
    return {"antes": antes, "entre": entre, "despues": despues, "total": antes + entre + despues, "cubierto": cubierto}


def grupo(turno: dict) -> str:
    tipo = turno.get("turn_type") or "?"
    return f"rag/{turno.get('hechos') or 'sin_hechos'}" if tipo == "rag" else tipo


def _p(valores: list[float], q: float) -> float:
    if not valores:
        return 0.0
    orden = sorted(valores)
    return orden[min(len(orden) - 1, int(q * len(orden)))]


def resumen(ruta: Path) -> None:
    filas = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]
    por_grupo: dict[str, list[dict]] = defaultdict(list)
    for f in filas:
        h = huecos(f)
        por_grupo["TODOS"].append(h)
        por_grupo[grupo(f)].append(h)
    print(f"\n== {ruta.name}: {len(filas)} turnos  (mediana / p90 en s)")
    print(f"{'grupo':28} {'n':>4}  {'latencia':>11}  {'hueco':>11}  " + "  ".join(f"{t:>11}" for t in TRAMOS))
    for nombre, hs in sorted(por_grupo.items(), key=lambda kv: (kv[0] != "TODOS", -len(kv[1]))):
        lat = [h["total"] + h["cubierto"] for h in hs]
        celdas = [f"{statistics.median(v):5.2f}/{_p(v, 0.9):5.2f}"
                  for v in (lat, [h["total"] for h in hs], *([h[t] for h in hs] for t in TRAMOS))]
        print(f"{nombre:28} {len(hs):>4}  " + "  ".join(f"{c:>11}" for c in celdas))


def detalle(ruta: Path, tramo: str, n: int) -> None:
    filas = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]
    filas.sort(key=lambda f: -huecos(f)[tramo])
    for f in filas[:n]:
        h = huecos(f)
        llamadas = " ".join(f"{c['p']}@{c['t']:.2f}+{c['s']:.2f}" for c in sorted(f.get("llamadas") or [], key=lambda c: c["t"]))
        nodos = " ".join(f"{k}={v:.2f}" for k, v in (f.get("nodes") or {}).items())
        print(f"{h[tramo]:5.2f}s {grupo(f):22} lat={f['latency']:.2f}  {llamadas}\n        nodos: {nodos}")


def por_llamada(ruta: Path) -> None:
    """El hueco que deja cada llamada al acabar (hasta la siguiente o el final del turno), si no queda otra en marcha."""
    filas = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]
    tras: dict[tuple, list[tuple[float, int | None]]] = defaultdict(list)
    for f in filas:
        llamadas = sorted(f.get("llamadas") or [], key=lambda c: c["t"])
        for c in llamadas:
            fin, otras = c["t"] + c["s"], [d for d in llamadas if d is not c]
            if any(d["t"] <= fin < d["t"] + d["s"] for d in otras):
                continue
            siguientes = [d["t"] for d in otras if d["t"] >= fin]
            hueco = (min(siguientes) if siguientes else f["latency"]) - fin
            tras[(c["p"], c.get("m"), "sigue" if siguientes else "última")].append((hueco, (c.get("u") or {}).get("out")))
    print(f"\n== {ruta.name}: hueco tras cada pieza (mediana), y su correlación con los tokens de salida")
    for (pieza, modelo, cuando), v in sorted(tras.items(), key=lambda kv: -len(kv[1])):
        if len(v) < 5:
            continue
        con_tokens = [(h, o) for h, o in v if o]
        corr = (statistics.correlation([o for _, o in con_tokens], [h for h, _ in con_tokens])
                if len(con_tokens) > 2 and len({o for _, o in con_tokens}) > 1 else float("nan"))
        print(f"  {pieza:28} {str(modelo):32} {cuando:6} n={len(v):4}  hueco={statistics.median(h for h, _ in v):5.2f}s"
              f"  corr(tokens)={corr:5.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("metricas", nargs="+", type=Path)
    parser.add_argument("--detalle", choices=TRAMOS, help="Lista los turnos con más hueco en ese tramo.")
    parser.add_argument("--por-llamada", action="store_true", help="El hueco que deja cada pieza al acabar.")
    parser.add_argument("-n", type=int, default=15)
    args = parser.parse_args()
    for ruta in args.metricas:
        if args.detalle:
            detalle(ruta, args.detalle, args.n)
        elif args.por_llamada:
            por_llamada(ruta)
        else:
            resumen(ruta)


if __name__ == "__main__":
    main()
