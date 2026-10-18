"""mod-3, resolutor (RESOLUTOR_MODEL): `resolve_slot_answer` con los casos de scripts/sonda_respuesta_pendiente.py.

Cada caso: (slot, mensaje, valor esperado; None = el mensaje NO contesta y el resolutor debe abstenerse). 3 pasadas.
Lo grave es un valor EQUIVOCADO (se aplicaría al estado); abstenerse en una respuesta real solo hace repreguntar.
"""
import asyncio
import os
import sys
import time

os.environ.setdefault("ENV_FILE", ".env.dev")
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scripts.sonda_respuesta_pendiente import CASOS  # noqa: E402
from src.agents.llm_extractor import resolve_slot_answer  # noqa: E402
from src.config import settings  # noqa: E402

# 18-oct (flag `resolutor_sin_contradicciones`): respuestas que se contradicen; el resolutor tiene que abstenerse
# (ronda mod-D: "no, buceé hace poco" a "¿Eres buzo certificado?" → minicurso). Solo aquí: CASOS es también de Jev.
CASOS = list(CASOS) + [
    ("certification", "no, buceé hace poco", None),
    ("certification", "no, tengo como 40 inmersiones", None),
    # el dato explícito (5 años) pesa más que el "no", que contestaba a otra cosa: más de 2 años = True
    ("safety", "no, la última fue hace como 5 años", True),
]


async def main():
    tiempos, bien, equivocados, abstenciones, detalle = [], 0, 0, 0, []
    for slot, mensaje, esperado in CASOS:
        lang = "en" if any(w in f" {mensaje.lower()} " for w in (" the ", " i ", " we ", " from ", " just ")) else "es"

        async def una():
            t0 = time.perf_counter()
            r = await resolve_slot_answer(slot, mensaje, lang=lang)
            tiempos.append(time.perf_counter() - t0)
            return r.get("value") if isinstance(r, dict) else None

        valores = await asyncio.gather(*[una() for _ in range(3)])
        ok = all(v == esperado for v in valores)
        bien += ok
        mal = sum(1 for v in valores if v is not None and v != esperado)
        equivocados += mal
        abstenciones += sum(1 for v in valores if v is None and esperado is not None)
        if not ok:
            detalle.append(f"   {slot:14} {mensaje[:45]!r:50} esperado={esperado!r} -> {valores}")
    tiempos.sort()
    print(f"MODELO {settings.resolutor_model}: bien 3/3 {bien}/{len(CASOS)} | valores EQUIVOCADOS {equivocados}/"
          f"{3 * len(CASOS)} | abstenciones en respuestas reales {abstenciones} | p50 {tiempos[len(tiempos) // 2]:.2f} s")
    print("\n".join(detalle))


asyncio.run(main())
