"""Banco de calibracion de `customer_place` (s4-28): ¿puede Jev decir DÓNDE está / desde dónde sale el cliente
(Cartagena / islas / no lo dice) mejor que place_by_role (la regex de preposiciones)? Banco 1 = los casos etiquetados de tests/test_location_single_source.py;
banco 2 = frases nuevas propias (ciego, no del golden); banco 3 = mensajes largos de primer contacto; banco 4 (27-oct,
(a) de LAT-0b) = negaciones («sin pasar por Cartagena»), sueltas y como respuesta a la pregunta del origen. Ningun
mensaje sale del golden. Mide aciertos de Jev y de la regex y cuantas respuestas de Jev son seguras y equivocadas.

27-oct: la pregunta es la de PRE (`_con_hoteles_de_la_base(_CUSTOMER_PLACE_Q_BARU_CARTAGENA)`) y el estado se arma como
en PRE (`_estado_para_jev`, con el turno del bot delante si lo hay). Con gen-6, Barú sale desde Cartagena.

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

Q = jev_router._con_hoteles_de_la_base(jev_router._CUSTOMER_PLACE_Q_BARU_CARTAGENA)

BANCO = [  # tests/test_location_single_source.py (place_by_role)
    ("quiero ir a las islas del rosario desde cartagena", "cartagena"),
    ("estoy en cartagena pero el hotel es en isla grande", "islands"),
    ("we're in cartagena now, staying on the islands tomorrow", "islands"),
    ("salimos desde cartagena, no estamos en las islas", "cartagena"),
    ("llegamos a cartagena y luego nos vamos a baru", "cartagena"),
    ("vamos de cartagena a baru", "cartagena"),
    ("estoy en cartagena, mañana nos vamos a las islas", "cartagena"),
    ("nos quedamos en baru, vamos a cartagena de paseo", "cartagena"),  # gen-6: desde Barú se sale de Cartagena
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
 ("Hi! we booked a night at a hotel in Baru for next week and want to know if you can pick us up there for a dive", "cartagena"),  # gen-6
 ("Estamos en el centro de Cartagena hasta el domingo, somos pareja, ella no bucea y yo soy open water, qué nos recomiendas en las islas", "cartagena"),
 ("Hola, me alojo en Bocagrande y quiero hacer snorkel en el Rosario con mis hijos mañana, a qué hora sale la lancha", "cartagena"),
 ("Good morning, we arrive on the islands tomorrow by ferry and stay 2 nights, could we do a fun dive from our hotel?", "islands"),
 ("Hola, somos 6 compañeros de trabajo, queremos hacer una actividad de buceo en las Islas del Rosario en octubre, ninguno es certificado", "none"),
]
# (a) de LAT-0b: el cliente dice desde dónde NO sale. Solo hay dos salidas: «sin pasar por Cartagena» es salir desde las
# islas; «sin salir de Cartagena», quedarse en la ciudad. Con «Assistant: …», la frase contesta a la pregunta del origen.
_PREGUNTA_ORIGEN = ("Assistant: ¿Saldrías *desde Cartagena* o ya estás *en las Islas del Rosario*? Así te paso el plan y "
                    "el enlace exactos.")
NEGACIONES = [
    ("Quiero reservar sin pasar por Cartagena", "islands"),
    ("No vamos a salir desde Cartagena, ya estaremos en las islas esos días", "islands"),
    ("We don't want to go back to Cartagena for the dive", "islands"),
    ("No estaremos en Cartagena, solo en Isla Grande", "islands"),
    ("Sin salir de Cartagena, ¿qué buceo puedo hacer?", "cartagena"),
    ("No nos quedamos en las islas, volvemos a Cartagena en la tarde", "cartagena"),
    ("We won't stay on the islands, we're based in Cartagena", "cartagena"),
    ("No sabemos todavía si dormiremos en las islas", "none"),
    ("¿Hay que ir a Cartagena para bucear con ustedes?", "none"),
    ("No conozco Cartagena, ¿es lindo bucear allá?", "none"),
    (f"{_PREGUNTA_ORIGEN}\nCustomer: Prefiero reservar sin tener que ir a Cartagena", "islands"),
    (f"{_PREGUNTA_ORIGEN}\nCustomer: No, desde Cartagena no", "islands"),
    (f"{_PREGUNTA_ORIGEN}\nCustomer: Desde la isla, no pienso ir a Cartagena", "islands"),
    (f"{_PREGUNTA_ORIGEN}\nCustomer: Ni idea, todavía no lo hemos decidido", "none"),
    (f"{_PREGUNTA_ORIGEN}\nCustomer: Desde Cartagena, no estaremos en las islas", "cartagena"),
]
N = 2


def _historial_y_mensaje(caso: str) -> tuple[list[dict], str]:
    """«Assistant: …\\nCustomer: …» → (el turno del bot como historial, el mensaje); una frase suelta, sin historial."""
    if not caso.startswith("Assistant: "):
        return [], caso
    bot, cliente = caso.split("\nCustomer: ", 1)
    return [{"role": "assistant", "content": bot.removeprefix("Assistant: ")}], cliente


async def preguntar(cli, caso):
    historial, msg = _historial_y_mensaje(caso)
    r = await cli.post(
        jev_router.JEV_URL,
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json={"model": settings.jev_model, "state": jev_router._estado_para_jev(msg, historial),
              "questions": {"q": Q}},
        timeout=10.0,
    )
    r.raise_for_status()
    a = r.json()["answers"]["q"]
    return a.get("choice"), float(a.get("confidence", 0.0))


async def main():
    regex_map = {"cartagena": "cartagena", "island": "islands", None: "none"}
    total_ok = total = total_mal = 0
    async with httpx.AsyncClient() as cli:
        for nombre, banco in (("BANCO (tests)", BANCO), ("CIEGO (nuevas)", CIEGO), ("LARGOS", LARGOS),
                              ("NEGACIONES", NEGACIONES)):
            print(f"\n## {nombre}")
            ok_j = ok_r = seguros_mal = 0
            for caso, esperado in banco:
                res = [await preguntar(cli, caso) for _ in range(N)]
                elec = {c for c, _ in res}
                conf = min(c for _, c in res)
                jev = res[0][0] if len(elec) == 1 else "dudoso"
                reg = regex_map[place_by_role(_historial_y_mensaje(caso)[1].lower())]
                ok_j += jev == esperado
                ok_r += reg == esperado
                seguros_mal += (jev != esperado and jev != "dudoso" and conf >= jev_router.CUSTOMER_PLACE_MIN)
                marca = "ok " if jev == esperado else "MAL"
                print(f"{marca} jev={jev:9} ({conf:.2f}) regex={reg:9} esperado={esperado:9} | {caso.replace(chr(10), ' / ')}")
            print(f"--> Jev {ok_j}/{len(banco)} · regex {ok_r}/{len(banco)} · Jev seguro (>=0,6) y equivocado: {seguros_mal}")
            total_ok, total, total_mal = total_ok + ok_j, total + len(banco), total_mal + seguros_mal
    print(f"\nTOTAL Jev {total_ok}/{total} · seguro y equivocado: {total_mal}")


if __name__ == "__main__":
    asyncio.run(main())
