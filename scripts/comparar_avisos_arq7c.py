"""arq-7c (23-oct): compara dos medidas del banco de avisos (reproducir_juez_pre) por el aviso final que añade cada
turno y lo que tarda. Lee de la traza las líneas `[RAG][AVISO_FINAL]`: «<id> (cita: ...)» cuando se añade un aviso y
«<N> ms model=<modelo>» con el tiempo de la llamada. Solo diagnóstico.

    python scripts/comparar_avisos_arq7c.py --banco docs/robustness/arq/banco-arq7c-avisos.json A.jsonl B.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

_MS = re.compile(r"\[RAG\]\[AVISO_FINAL\] (\d+) ms model=(\S+)")
_ELEGIDO = re.compile(r"\[RAG\]\[AVISO_FINAL\] ([a-z0-9-]+) \(cita:")


def _leer(ruta: str) -> dict:
    por_dialogo: dict = defaultdict(lambda: {"avisos": [], "ms": [], "segundos": [], "modelos": set()})
    for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        r = json.loads(linea)
        d = por_dialogo[r["dialogo"]]
        elegidos = [m.group(1) for t in r.get("traza") or [] for m in [_ELEGIDO.search(t)] if m]
        d["avisos"].append(elegidos[-1] if elegidos else None)
        for t in r.get("traza") or []:
            m = _MS.search(t)
            if m:
                d["ms"].append(int(m.group(1)))
                d["modelos"].add(m.group(2))
        d["segundos"].append(r.get("segundos") or 0.0)
    return por_dialogo


def _p(valores: list[float], q: float) -> float:
    if not valores:
        return 0.0
    v = sorted(valores)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", required=True)
    ap.add_argument("medidas", nargs="+")
    args = ap.parse_args()
    esperado = {d["id"]: d.get("aviso") for d in json.loads(Path(args.banco).read_text(encoding="utf-8"))["dialogos"]}
    for ruta in args.medidas:
        datos = _leer(ruta)
        ms = [x for d in datos.values() for x in d["ms"]]
        seg = [x for d in datos.values() for x in d["segundos"]]
        aciertos = total = inventados = 0
        print(f"== {ruta}  modelos={sorted(set().union(*(d['modelos'] for d in datos.values())))}")
        for dialogo, quiere in esperado.items():
            d = datos.get(dialogo)
            if not d:
                continue
            ok = sum(1 for a in d["avisos"] if a == quiere)
            otros = [a for a in d["avisos"] if a and a != quiere]
            aciertos += ok
            total += len(d["avisos"])
            inventados += len(otros)
            print(f"   {'OK' if ok == len(d['avisos']) else 'NO'} {dialogo}: quiere {quiere} · da {d['avisos']}")
        print(f"   avisos como el esperado {aciertos}/{total} · otros avisos {inventados} · "
              f"aviso_final p50 {statistics.median(ms) if ms else 0:.0f} ms p90 {_p(ms, 0.9):.0f} ms (n={len(ms)}) · "
              f"turno p50 {statistics.median(seg) if seg else 0:.2f} s p90 {_p(seg, 0.9):.2f} s")


if __name__ == "__main__":
    main()
