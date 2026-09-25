"""¿Distingue JEV afirmar de preguntar donde el extractor no puede?

La pregunta que falta en el sistema es cerrada ("¿el cliente AFIRMA que se aloja aquí?") y
Jev es exactamente eso: preguntas tipadas, ~0,3 s, y ya se llama una vez por turno (asi entro
`asks_question`, a coste 0 de peticiones). Esto NO cambia codigo: solo mide si sabria.
"""
import asyncio
import os
import sys
import time

os.environ.update({"ENV_FILE": ".env.dev", "APP_ENV": "development", "JEV_ROUTER_ENABLED": "true"})
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import httpx  # noqa: E402

from src.agents.jev_router import _CONTEXT, JEV_URL  # noqa: E402
from src.config import settings  # noqa: E402

P_ALOJA = ("The customer STATES where they themselves are staying or departing from (a hotel, a "
           "city, an island they are actually at). Asking for recommendations, wondering 'what if "
           "I stayed there', or naming a place as the DESTINATION of the trip is NOT stating it.")
P_ACTIV = ("The customer STATES which activity/course they want to do. Asking about one "
           "conditionally ('in case I decided to', 'is it possible to') is NOT stating it.")

CASOS = [
    # (mensaje, pregunta, LO CORRECTO)
    ("What if I decide to stay one day longer in rosario, can you provide de transfer back to cartagena?", "aloja", False),
    ("Ok. Thanks. We will work out the best days. Do you recommend any hotels on the island convenient for the diving?", "aloja", False),
    ("Mi madre puede acompañarme en el buceo y se quedar en la isla de apoyo?", "aloja", False),
    ("Hii!! I am staying at Isla Grande and I would love to dive here, can I join the fun dives?", "aloja", True),
    ("Vale, reservaremos hotel en la isla para esas noches", "aloja", True),
    ("Estamos alojados en Bocagrande, ¿nos recogéis allí?", "aloja", True),
    ("i'd like to inquiry about the modalities for a 2 day dive package at the rosario islands, i'll be in cartagena", "aloja", False),
    ("Hi, My understanding is that the transportation to rosario is included, in case I decided to do PADI Open Water Diver certification course., correct?", "activ", False),
    ("Hi. Is it possible for my son a PADi certificat ?", "activ", False),
    ("Hi, I’m trying to checkout to take PADI Open Water Diver certification course but the discount is not showing up.", "activ", True),
    ("Buenos días. Quiero hacer el paquete de 5 buceos.", "activ", True),
    ("bueno, reservemos snorkel para toda la familia, somos 4", "activ", True),
]
N = 3


async def preguntar(cli, msg, desc):
    r = await cli.post(JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                       json={"model": settings.jev_model, "state": f"{_CONTEXT}\n\nCustomer message: {msg}",
                             "questions": {"afirma": {"type": "noul", "instructions": desc}}},
                       timeout=10.0)
    r.raise_for_status()
    return r.json()["answers"]["afirma"]


async def main():
    async with httpx.AsyncClient() as cli:
        bien = 0
        t0 = time.perf_counter()
        for msg, cual, esperado in CASOS:
            desc = P_ALOJA if cual == "aloja" else P_ACTIV
            probs = []
            for _ in range(N):
                a = await preguntar(cli, msg, desc)
                probs.append(round(a.get("noul", 0.0), 2))
            votos = [p >= 0.5 for p in probs]
            ok = all(v == esperado for v in votos)
            bien += ok
            print(f"  [{'OK ' if ok else 'MAL'}] {cual} esperado={esperado!s:<5} p={probs}  {msg[:78]!r}")
        print(f"\n  ACIERTOS: {bien}/{len(CASOS)}  |  {(time.perf_counter()-t0)/(len(CASOS)*N):.2f} s por pregunta")

asyncio.run(main())
