"""Los rechazos del juez de grounding, sacados de los logs de PRE guardados (análisis del 1-oct).

Cada intento rechazado deja en el log `[RAG][GROUNDING] attempt N rejected (HALLUCINATED - <hecho> NO | - <hecho> NO)
query=...`. Este script los lista por ronda, parte cada rechazo en sus hechos marcados NO y, para cada hecho con
cifras, dice si TODAS sus cifras están en el catálogo que el juez tiene delante (`catalog_facts`). No decide si el
juez acertó: eso se lee a mano (ver `docs/robustness/juez/README.md`).

    python -m scripts.juez_rechazos 2026-09-30-rag5-A 2026-09-30-rag5-B 2026-10-01-rag5-C > salida.json
"""
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("ENV_FILE", ".env.ci")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.agents.grounding_check import _context_number_set, _number_variants  # noqa: E402
from src.flows.catalog import catalog_facts  # noqa: E402

_RECHAZO = re.compile(r"\[RAG\]\[GROUNDING\] attempt (\d+) rejected \((.*)\) query=(.*)$")
_FINAL = re.compile(r"\[RAG\]\[GROUNDING\] Rejecting after (\d+) attempts query=(.*?) reason=")
_CIFRA = re.compile(r"\d[\d.,]*\d|\d")


def hechos(razon: str) -> list[str]:
    razon = re.sub(r"^HALLUCINATED\s*-?\s*", "", razon.strip())
    return [h.strip(" -|") for h in re.split(r"\s+NO\s*\|?\s*-?", razon) if h.strip(" -|")]


def cifras_en_catalogo(hecho: str, numeros_catalogo: set[str]) -> bool | None:
    cifras = [c for c in _CIFRA.findall(hecho) if len(c.replace(".", "").replace(",", "")) >= 2]
    if not cifras:
        return None
    return all(_number_variants(c) & numeros_catalogo for c in cifras)


def main(rondas: list[str]) -> None:
    catalogo = _context_number_set(catalog_facts("es") + "\n" + catalog_facts("en"))
    salida = []
    for ronda in rondas:
        lineas = Path(f"docs/robustness/logs-pre-{ronda}.txt").read_text(encoding="utf-8", errors="replace").splitlines()
        finales = {m.group(2)[:60] for lin in lineas if (m := _FINAL.search(lin))}
        for lin in lineas:
            m = _RECHAZO.search(lin)
            if not m:
                continue
            intento, razon, query = int(m.group(1)), m.group(2), m.group(3)
            salida.append({
                "ronda": ronda, "intento": intento, "query": query.strip(),
                "acabo_en_no_lo_tengo": query.strip()[:60] in finales,
                "hechos": [{"hecho": h, "cifras_en_catalogo": cifras_en_catalogo(h, catalogo)} for h in hechos(razon)],
            })
    print(json.dumps(salida, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
