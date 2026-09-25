"""Banco de calibracion de las dos preguntas de Jev que distinguen AFIRMAR de PREGUNTAR.

Por que existe (u3-4, 25-sep): en un turno con pregunta, un lugar o un producto nombrado DENTRO
de la pregunta no es un dato del cliente. Ni el relleno ni la verificacion saben distinguirlo:
las dos son EXTRACCION, y para un extractor "me recomiendas hoteles en la isla?" es una señal
clara de location=island. Meter el matiz en el prompt fallo dos veces, con medida (relleno
24-sep, verificacion 25-sep). Jev si lo distingue, y va en la MISMA llamada del router, asi que
no gasta ninguna peticion de mas.

Los casos NO son inventados: son los datos inventados que hay que matar y los datos buenos que
una version anterior de la redaccion destruyo -- datos que el propio flag APAGADO ya capturaba.
Por eso esto es un banco de calibracion y no una sonda: cualquier cambio en la redaccion se pasa
por aqui ANTES de gastar una tanda de `replay_golden_local` (20 min), y se mide contra la
redaccion anterior, no contra la intuicion.

    python -m scripts.sonda_afirma_vs_pregunta

Leccion de metodo, que costo una medida: una sonda de frases SUELTAS no vale para juzgar el
camino de la verificacion (`scripts/sonda_verificacion_fiel.py`), porque sin historial el LLM ya
se abstiene donde en el replay no. Aqui si vale, porque Jev tampoco ve el historial: recibe
exactamente este mensaje, igual que en produccion.
"""
import asyncio
import os
import sys
import time

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("JEV_ROUTER_ENABLED", "true")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx  # noqa: E402

from src.agents import jev_router  # noqa: E402
from src.config import settings  # noqa: E402

# La redaccion DESCARTADA, para que el resultado negativo sea reproducible y no haya que
# creerselo: descartaba de mas y se comia datos afirmados (15/20 frente a 19/20).
V1_LOC = ("The customer STATES where they themselves are staying or departing from (a hotel, a "
          "city, an island they are actually at). Asking for recommendations, wondering 'what if "
          "I stayed there', or naming a place as the DESTINATION of the trip is NOT stating it.")
V1_ACT = ("The customer STATES which activity/course they want to do. Asking about one "
          "conditionally ('in case I decided to', 'is it possible to') is NOT stating it.")

# (que pregunta, mensaje, lo que TIENE que contestar)
CASOS = [
    # --- ubicacion: datos INVENTADOS que hay que matar ---
    ("loc", "What if I decide to stay one day longer in rosario, can you provide de transfer back to cartagena?", False),
    ("loc", "Ok. Thanks. We will work out the best days. Do you recommend any hotels on the island convenient for the diving?", False),
    ("loc", "Mi madre puede acompañarme en el buceo y se quedar en la isla de apoyo?", False),
    ("loc", "Does isla grande count acceptable is it part of the roasirio island^", False),
    # --- ubicacion: datos BUENOS que la redaccion v1 destruyo ---
    ("loc", "Hi, I plan on being in Cartagena and do scuba diving on April 21 and 22. I have open water, advanced open water", True),
    ("loc", "Buena Tardes quería preguntarte estaremos en islas del rosario en junio y quería regalarle a mi esposo una experiencia de buceo", True),
    ("loc", "Hii!! I am staying at Isla Grande and I would love to dive here, can I join the fun dives?", True),
    ("loc", "Vale, reservaremos hotel en la isla para esas noches", True),
    ("loc", "Estamos alojados en Bocagrande, ¿nos recogéis allí?", True),
    # --- actividad: datos INVENTADOS que hay que matar ---
    ("act", "Hi, My understanding is that the transportation to rosario is included, in case I decided to do PADI Open Water Diver certification course., correct?", False),
    ("act", "Hi. Is it possible for my son a PADi certificat ?", False),
    ("act", "entonces que actividad le recomiendan", False),
    # --- actividad: datos BUENOS que la redaccion v1 destruyo ---
    ("act", "Hola buenos días, mi nombre es [NOMBRE]. Quería averiguar por el costo de un fundive para este fin de semana", True),
    ("act", "Queria saber los valores de dos buceos o del pack de 5 buceos en 2 dias", True),
    ("act", "hola, cuanto cuesta el paquete de 5 inmersiones?", True),
    ("act", "hola cuanto cuesta el buceo certificado", True),
    ("act", "Buena Tardes quería preguntarte estaremos en islas del rosario en junio y quería regalarle a mi esposo una experiencia de buceo", True),
    ("act", "Hi, I plan on being in Cartagena and do scuba diving on April 21 and 22. I have open water, advanced open water", True),
    ("act", "bueno, reservemos snorkel para toda la familia, somos 4", True),
    ("act", "Buenos días. Quiero hacer el paquete de 5 buceos.", True),
]
N = 2  # Jev es estable (±0,03); 2 repeticiones bastan para ver si una respuesta baila


async def _preguntar(cli: httpx.AsyncClient, mensaje: str, instrucciones: str) -> float:
    r = await cli.post(
        jev_router.JEV_URL,
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json={
            "model": settings.jev_model,
            "state": f"{jev_router._CONTEXT}\n\nCustomer message: {mensaje}",
            "questions": {"q": {"type": "noul", "instructions": instrucciones}},
        },
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()["answers"]["q"].get("noul", 0.0)


async def main() -> None:
    viva = jev_router._AFFIRMS_QUESTIONS
    variantes = (
        ("v1 — DESCARTADA (descarta de más)", V1_LOC, V1_ACT),
        ("la que está en el código", viva[jev_router.AFFIRMS_LOCATION]["instructions"],
         viva[jev_router.AFFIRMS_ACTIVITY]["instructions"]),
    )
    async with httpx.AsyncClient() as cli:
        for etiqueta, loc, act in variantes:
            print(f"\n{'=' * 84}\n{etiqueta}\n{'=' * 84}")
            bien = 0
            t0 = time.perf_counter()
            for cual, mensaje, esperado in CASOS:
                instrucciones = loc if cual == "loc" else act
                ps = [round(await _preguntar(cli, mensaje, instrucciones), 2) for _ in range(N)]
                ok = all((p >= jev_router.AFFIRMS_MIN) == esperado for p in ps)
                bien += ok
                print(f"  [{'OK ' if ok else 'MAL'}] {cual} esperado={esperado!s:<5} p={ps}  {mensaje[:70]!r}")
            print(f"  --> {bien}/{len(CASOS)}  ({time.perf_counter() - t0:.0f} s, umbral {jev_router.AFFIRMS_MIN})")


if __name__ == "__main__":
    asyncio.run(main())
