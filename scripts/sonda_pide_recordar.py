"""Banco de calibración de la pregunta de Jev `asks_recall` (paso 5, flag `rag_v2`, 27-sep).

El "¿me recuerdas lo que dije?" (`recall_field` de `detect_special_signals`) contesta con el
dato guardado y CANCELA la respuesta del RAG. En la ronda A del paso 3 salió 15 veces y casi
ninguna era una petición de recordar: "could you just confirm at what time and where we make the
appointment?", "Hope you are operating on Easter Sunday?", "¿el curso que te he pedido cuánto
tiempo dura?"… Cada una fue una pregunta sin contestar. Los negativos de abajo son ESOS mensajes;
los positivos, las peticiones reales (las de los tests y variantes).

    python -m scripts.sonda_pide_recordar
"""
import asyncio
import os
import sys

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx  # noqa: E402

from scripts.sonda_afirma_vs_pregunta import _preguntar  # noqa: E402
from src.agents import jev_router  # noqa: E402

POSITIVOS = [
    "cuantas personas somos, me lo recuerdas?",
    "cuantos somos, recuerdame?",
    "¿qué te había pedido?",
    "¿qué llevamos hasta ahora?",
    "remind me what I said",
    "what did I ask for?",
    "¿qué actividad te dije que quería?",
    "me recuerdas en qué hotel te dije que estaba?",
    "can you remind me how many people I told you?",
    "¿me repites lo que tenemos de la reserva?",
    "sorry, what did I tell you about the kids' ages?",
    "¿te había dicho que soy colombiano?",
]
# Ronda A del paso 3 (27-sep): mensajes que recibieron la respuesta de "recordar" sin pedirlo.
NEGATIVOS = [
    "El curso que te he pedido cuánto tiempo dura ?",
    "Si cuantos días son?",
    "como residente?",
    "Great. We will book diving with you on the website and will book our hotel on the island . Hope you are "
    "operating on Easter Sunday? We want to dive on April 5 and 6. How do we book/pay for the $50 refresher course?",
    "Me dijiste que a las 7:30 am",
    "so, if I understood correctly, booking just for one night will be enough, right?",
    "also- I saw pictures and videos are not included...?",
    "PADI open water, advanced open water and deep diver certs",
    "What island on rosario islands should I look for the hotel?",
    "Yo vi un video en YT de alguien que hizo el paquete con ustedes e hicieron dos inmersiones en dos distintos puntos",
    "Full name of dive center, location, dates etc",
    "OK, could you just confirm at what time and where we make the appointment?",
    "Soy argentino pero resido en Bogotá",
    "Its been more than 1.5 years since last dive. So is there additional cost for refresher?",
]
N = 2


async def main() -> None:
    q = jev_router._ASKS_RECALL_Q["instructions"]
    async with httpx.AsyncClient() as cli:
        async def score(m):
            vals = [await _preguntar(cli, m, q) for _ in range(N)]
            return sum(vals) / len(vals)
        pos = await asyncio.gather(*(score(m) for m in POSITIVOS))
        neg = await asyncio.gather(*(score(m) for m in NEGATIVOS))
    for label, msgs, vals in (("POS", POSITIVOS, pos), ("NEG", NEGATIVOS, neg)):
        for m, v in sorted(zip(msgs, vals), key=lambda x: x[1]):
            print(f"{label} {v:.2f}  {m[:90]}")
    t = jev_router.ASKS_RECALL_MIN
    print(f"\numbral {t}: positivos {sum(v >= t for v in pos)}/{len(pos)}, "
          f"falsas alarmas {sum(v >= t for v in neg)}/{len(neg)}")


if __name__ == "__main__":
    asyncio.run(main())
