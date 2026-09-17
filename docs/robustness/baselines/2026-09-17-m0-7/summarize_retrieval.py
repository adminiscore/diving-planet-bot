"""Convierte el volcado de `eval_retrieval` en cifras comparables.

`eval_retrieval` imprime los top-k por consulta: sirve para diagnosticar, pero no
da un numero que se pueda comparar entre dos tandas, que es lo que una LINEA BASE
necesita (m0-7). Resume lo que si es comparable:

  - cuantas consultas traen al menos un documento por encima del umbral de
    confianza que usa el bot (`rag_min_score`, hoy 0.40 sobre el score CRUDO:
    el boost por temas solo reordena, no decide si hay respuesta);
  - la mediana y el minimo del mejor score, para ver si el margen se estrecha;
  - las consultas mas debiles, por nombre, para poder mirarlas caso a caso.
"""

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"c:\Users\gonza\.devin\diving-planet-bot")))

from src.config import settings  # noqa: E402

UMBRAL = settings.rag_min_score


def resumen(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    filas = []
    for r in data["results"]:
        docs = r.get("docs") or []
        mejor = max((d["score"] for d in docs), default=0.0)
        filas.append((r["query"], mejor))
    mejores = [m for _, m in filas]
    por_encima = [q for q, m in filas if m >= UMBRAL]
    return {
        "lang": data["lang"],
        "consultas": len(filas),
        "sobre_umbral": len(por_encima),
        "mediana_top1": round(statistics.median(mejores), 4) if mejores else 0.0,
        "min_top1": round(min(mejores), 4) if mejores else 0.0,
        "debiles": sorted(filas, key=lambda f: f[1])[:3],
    }


if __name__ == "__main__":
    print(f"umbral de confianza (rag_min_score) = {UMBRAL}\n")
    for p in sys.argv[1:]:
        r = resumen(Path(p))
        print(f"[{r['lang']}] {r['sobre_umbral']}/{r['consultas']} consultas con top-1 >= {UMBRAL}"
              f" | mediana top-1 {r['mediana_top1']} | minimo {r['min_top1']}")
        for q, m in r["debiles"]:
            print(f"      {m:.4f}  {q}")
