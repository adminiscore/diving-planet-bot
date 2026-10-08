"""Cambio de modelos, fase 3 (8-oct): el juez de grounding v3 con OTRO modelo (p. ej. gpt-6-luna) frente al de PRE.

Mismo banco que `scripts.sonda_juez_tipo` (respuestas REALES de rag_piezas del 1-oct, etiquetadas a mano en
`docs/robustness/juez/banco-etiquetas.json`): "invento" = debe rechazarse, "falso" = debe pasar; más una muestra de
las aprobadas en la medición, que deben seguir pasando. Grupos de diseño y ciego. Mide también el tiempo de cada juicio
(el juez está dentro de la latencia del RAG).

    python -m scripts.sonda_juez_modelo gpt-4.1 gpt-6-luna
"""
import asyncio
import random
import statistics
import sys
import time

from scripts.sonda_juez_tipo import ETIQUETAS, items
from src.agents import grounding_check
from src.config import settings

N_RECH = 2
MUESTRA = 40


async def juzgar(item: dict, modelo: str) -> tuple[bool, float]:
    settings.grounding_v3_model = modelo
    settings.juez_por_tipo = False
    t = time.perf_counter()
    ok, _ = await grounding_check.is_grounded(item["respuesta"], item["contexto"], item["lang"])
    return ok, time.perf_counter() - t


async def main(modelos: list[str]) -> None:
    import json

    etiquetas = json.loads(ETIQUETAS.read_text(encoding="utf-8"))["etiquetas"]
    todos = items()
    rech = [x for x in todos if not x["v3_original"] and etiquetas.get(x["clave"], {}).get("etiqueta") in ("invento", "falso")]
    random.seed(1)
    aprob = random.sample([x for x in todos if x["v3_original"]], MUESTRA)
    for modelo in modelos:  # secuencial: el modelo del juez es global en `settings`
        tiempos = []
        print(f"\n######## {modelo}")
        for grupo in ("diseño", "ciego"):
            tabla = {"invento": [0, 0], "falso": [0, 0], "aprobada": [0, 0]}
            for x in [r for r in rech if r["grupo"] == grupo]:
                et = etiquetas[x["clave"]]["etiqueta"]
                for _ in range(N_RECH):
                    ok, dt = await juzgar(x, modelo)
                    tabla[et][0] += ok
                    tabla[et][1] += 1
                    tiempos.append(dt)
            for x in [a for a in aprob if a["grupo"] == grupo]:
                ok, dt = await juzgar(x, modelo)
                tabla["aprobada"][0] += ok
                tabla["aprobada"][1] += 1
                tiempos.append(dt)
            print(f"  {grupo:6}: inventos que deja pasar {tabla['invento'][0]}/{tabla['invento'][1]} (mejor 0) · "
                  f"verdades que deja pasar {tabla['falso'][0]}/{tabla['falso'][1]} (mejor todas) · "
                  f"aprobadas que siguen pasando {tabla['aprobada'][0]}/{tabla['aprobada'][1]}")
        print(f"  tiempo por juicio: mediana {statistics.median(tiempos):.2f}s · p90 "
              f"{sorted(tiempos)[int(0.9 * len(tiempos))]:.2f}s ({len(tiempos)} juicios)")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["gpt-4.1", "gpt-6-luna"]))
