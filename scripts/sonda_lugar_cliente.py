"""Banco de calibracion de `customer_place` (s4-28): ¿puede Jev decir DÓNDE está / desde dónde sale el cliente
(Cartagena / islas / no lo dice) mejor que place_by_role (la regex de preposiciones)? Banco 1 = los casos etiquetados de tests/test_location_single_source.py;
banco 2 = frases nuevas propias (ciego, no del golden); banco 3 = mensajes largos de primer contacto. Ningun
mensaje sale del golden. Mide aciertos de Jev y de la regex y cuantas respuestas de Jev son seguras y equivocadas.

    python -m scripts.sonda_lugar_cliente
"""
import asyncio
import os
import sys

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx  # noqa: E402

from src.agents import jev_router  # noqa: E402
from src.agents.intent_detector import place_by_role  # noqa: E402
from src.config import settings  # noqa: E402

Q = jev_router._CUSTOMER_PLACE_Q

BANCO = [  # tests/test_location_single_source.py (place_by_role)
    ("quiero ir a las islas del rosario desde cartagena", "cartagena"),
    ("estoy en cartagena pero el hotel es en isla grande", "islands"),
    ("we're in cartagena now, staying on the islands tomorrow", "islands"),
    ("salimos desde cartagena, no estamos en las islas", "cartagena"),
    ("llegamos a cartagena y luego nos vamos a baru", "cartagena"),
    ("vamos de cartagena a baru", "cartagena"),
    ("estoy en cartagena, mañana nos vamos a las islas", "cartagena"),
    ("nos quedamos en baru, vamos a cartagena de paseo", "islands"),
    ("we are staying at isla grande, arriving from cartagena", "islands"),
    ("no sé si cartagena o las islas", "none"),
]
CIEGO = [  # frases nuevas
    ("vamos a estar unos días en Cartagena y nos gustaría bucear en las Islas del Rosario", "cartagena"),
    ("we'll be visiting Cartagena next month and want to dive the Rosario islands", "cartagena"),
    ("estamos de vacaciones en Cartagena, ¿qué planes tienen para bucear en las islas?", "cartagena"),
    ("I'm on Isla Grande this week, can I join a dive from here?", "islands"),
    ("nos alojamos en una cabaña en isla grande y queremos bucear el jueves", "islands"),
    ("queremos ir a las islas a bucear, ¿cuánto cuesta?", "none"),
    ("¿hay hoteles en las islas del rosario?", "none"),
    ("can you recommend a hotel on the islands?", "none"),
    ("mañana llego a Cartagena y pasado me voy a dormir a una isla", "cartagena"),
    ("ya estamos en la isla, nos recogen?", "islands"),
    ("nuestro hotel está en Bocagrande y queremos conocer el arrecife del Rosario", "cartagena"),
    ("hola, quiero bucear en las islas del rosario", "none"),
]
LARGOS = [
 ("Buenas! Somos tres amigos de Chile, llegamos a Cartagena el 12 y queremos hacer un par de inmersiones en el Rosario, dos somos open water y uno nunca buceó", "cartagena"),
 ("Hi there, my wife and I are flying into Cartagena on Friday, we're both advanced divers and would love to dive the Rosario islands on Saturday, what do you offer?", "cartagena"),
 ("Hola, estamos alojados en el hotel San Pedro de Majagua desde el lunes, somos 2, queremos bucear el martes y miércoles, cuánto sale?", "islands"),
 ("hello! we are a family of 4 staying in Getsemani, kids 10 and 13, interested in snorkel at the islands and maybe a mini course for the kids", "cartagena"),
 ("Que tal, vengo desde Medellín la próxima semana, voy a estar en Cartagena 4 días y quiero sacar el open water en las islas", "cartagena"),
 ("We're spending three nights on Isla Grande (Cocoliso) at the end of the month, both certified, looking for 2 days of diving", "islands"),
 ("Hola!! Les escribo desde México, viajamos a Colombia en marzo, la idea es conocer Cartagena y bucear en las Islas del Rosario. Somos buzos avanzados", "cartagena"),
 ("Hi, I'll be in Colombia in May, thinking about diving in the Rosario islands, how does it work and what are the prices?", "none"),
 ("Buenas tardes, queremos regalarle a mi papá un bautismo de buceo en las islas, estamos pensando ir en junio, que opciones hay", "none"),
 ("Hi! we booked a night at a hotel in Baru for next week and want to know if you can pick us up there for a dive", "islands"),
 ("Estamos en el centro de Cartagena hasta el domingo, somos pareja, ella no bucea y yo soy open water, qué nos recomiendas en las islas", "cartagena"),
 ("Hola, me alojo en Bocagrande y quiero hacer snorkel en el Rosario con mis hijos mañana, a qué hora sale la lancha", "cartagena"),
 ("Good morning, we arrive on the islands tomorrow by ferry and stay 2 nights, could we do a fun dive from our hotel?", "islands"),
 ("Hola, somos 6 compañeros de trabajo, queremos hacer una actividad de buceo en las Islas del Rosario en octubre, ninguno es certificado", "none"),
]
N = 2


async def preguntar(cli, msg):
    r = await cli.post(
        jev_router.JEV_URL,
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json={"model": settings.jev_model, "state": f"{jev_router._CONTEXT}\n\nCustomer message: {msg}",
              "questions": {"q": Q}},
        timeout=10.0,
    )
    r.raise_for_status()
    a = r.json()["answers"]["q"]
    return a.get("choice"), float(a.get("confidence", 0.0))


async def main():
    regex_map = {"cartagena": "cartagena", "island": "islands", None: "none"}
    async with httpx.AsyncClient() as cli:
        for nombre, banco in (("BANCO (tests)", BANCO), ("CIEGO (nuevas)", CIEGO), ("LARGOS", LARGOS)):
            print(f"\n## {nombre}")
            ok_j = ok_r = seguros_mal = 0
            for msg, esperado in banco:
                res = [await preguntar(cli, msg) for _ in range(N)]
                elec = {c for c, _ in res}
                conf = min(c for _, c in res)
                jev = res[0][0] if len(elec) == 1 else "dudoso"
                reg = regex_map[place_by_role(msg.lower())]
                ok_j += jev == esperado
                ok_r += reg == esperado
                seguros_mal += (jev != esperado and jev != "dudoso" and conf >= 0.6)
                marca = "ok " if jev == esperado else "MAL"
                print(f"{marca} jev={jev:9} ({conf:.2f}) regex={reg:9} esperado={esperado:9} | {msg}")
            print(f"--> Jev {ok_j}/{len(banco)} · regex {ok_r}/{len(banco)} · Jev seguro (>=0,6) y equivocado: {seguros_mal}")


if __name__ == "__main__":
    asyncio.run(main())
