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

    python -m scripts.sonda_afirma_vs_pregunta          # todo (~50 s)
    python -m scripts.sonda_afirma_vs_pregunta u34      # lugar y actividad (las del codigo, ~10 s)
    python -m scripts.sonda_afirma_vs_pregunta u35      # certificado, grupo, nacionalidad (candidatas, ~35 s)

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
    # Ronda B2 del escalon 1 (25-sep, PRE): Jev lo dio por NO afirmado y se perdio la actividad
    # -> el bot no llego a dar el enlace (regresion real de v5; ver u3-4-diseno.md, "Ronda B2").
    ("act", "Hola, buenos días. Deca del centro de buceo. Me recomendaron a ustedes para bucear en Cartagena. Yo voy a estar entre el 5 y el 7 por allá. Entonces quería ver si tienen alguna salida programada. Yo soy open y me gustaría salir un día y tal. No sé qué tienen. Muchas gracias.", True),
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


# ── u3-5 (25-sep, Alvaro): tres preguntas CANDIDATAS, aun NO en el codigo ────────────────────────
# Los 2 errores reales que sobreviven a u3-4 v5 (`is_certified` en "in case I decided to do PADI
# Open Water", `group_size` en "is it possible for my son...") y la nacionalidad de u3-5 ("costo
# para colombianos" -> colombiano) son la misma familia que la puerta ya arregla para lugar y
# actividad: un dato nombrado DENTRO de una pregunta. Misma solucion, una pregunta mas a Jev en la
# misma llamada (coste 0), calibrada ANTES de tocar el codigo (leccion de v4).
#
# Casos REALES del golden: turnos con pregunta en los que `off` o v5 fijan el campo, etiquetados a
# mano ("¿lo dice ESTE mensaje?"), mas mensajes del golden con el dato dicho de verdad. Medido
# (N=2, umbral 0,7):
#   v1 ejemplos COPIADOS de los casos ........ cert 12/15, grp 12/12, nac 12/12 | nuevos: cert 13/15, grp 13/13
#   v2 ejemplos que NO copian el banco ....... cert 14/15, grp 12/12, nac 11/12 | nuevos: cert 14/15, grp 13/13
#   v3 = v2 + "respuesta corta" + "comprar un curso" (la de abajo)
#                                              cert 15/15, grp 12/12, nac 12/12 | nuevos: cert 14/15, grp 13/13
# Honestidad sobre los "nuevos": no se copio ninguna frase suya en las redacciones, pero las reglas
# de v2 se escribieron DESPUES de leerlos. No son una prueba ciega; esa es el replay del golden.
# Lo que falla ("Buzos certificados", 0,66): dos palabras que sin la pregunta del bot delante son
# ambiguas (producto o estado). No es turno con pregunta, asi que la puerta nunca lo veria.
# Ojo: Jev baila mas de ±0,03 en los casos frontera ("quiero bucear certificado": 0,79 y 0,67).
#
# Cuando pasen al codigo (`jev_router`), este bloque debe leerlas de alli, como hace `main` con
# las de lugar y actividad.
U35_CANDIDATAS = {
    "cert": (
        'The customer tells us whether THEY, or the people who will dive with them, already hold a '
        "diving certification. Stating a level counts ('I'm Open Water certified', 'mi esposa es "
        "Advanced'), and so does saying that someone has never dived, that they want to get certified "
        'or are buying or booking a beginner course, that they are partway through a course '
        '(e-learning, referral), or that they need a refresher. A short answer of a few words that '
        'states it counts too. It is FALSE when a course or level is only mentioned as a hypothesis '
        "('if I ever decided to get certified'), when they only ask whether something would be "
        'possible for someone, or when they ask about dives, prices or options without saying '
        "anyone's level."
    ),
    "grp": (
        'The customer tells us HOW MANY people will take part, or who is coming: a number of people, '
        "'just me', 'my wife and I', a family, a list of names. A plan counts ('we'll probably book "
        "it for three'). It is FALSE when the numbers in the message count dives, days, nights or "
        "packages rather than people, when 'solo' means 'only' ('solo la mañana'), or when they ask "
        'about one single person without saying who is coming.'
    ),
    "nac": (
        "The customer tells us their nationality or where they come from ('somos de Medellín', 'I'm "
        "from Canada', 'we are Mexican'). Saying that they are, or are not, Colombian counts, even in "
        "a few words. It is FALSE when 'Colombian' only appears in what they ask about: prices or "
        'rates for Colombians, or whether a price is in pesos or in dollars.'
    ),
}

CASOS_U35 = [
    ('cert', 'Hi, I plan on being in Cartagena and do scuba diving on April 21 and 22. I have open water, advanced open water and deep diver certs. Please advise which dives you recommend', True),
    ('cert', "Hello, I just want to tell you, I just make a reservation for me and [NOMBRE] for diving with you on Monday 11th of May. Him is gonna be like a, I don't know how you tell that in English, but it's like his first time he want to like discover diving if he will like it or no. And me, I am advanced and we just make both reservations. I just want to ask you if you receive it. Thank you.", True),
    ('cert', 'Hi There,\nI am looking to book 2 dives and snorkeling sessions for the following people.\n2 diving sessions - All PADI certified for open water.\n2 adults (ages 42, 19)\n1 youth (age 17)\nSnorkeling\n1 Adult (Age 43)\n2 kids (Ages 14, 10)\nCan you provide information and total price please', True),
    ('cert', 'Busco el seguinte:\nVamos en família a Cartagena. 1 buzo avanzado y 2 para bautismo', True),
    ('cert', 'Hola!! Te contacto desde Argentina.  Estaremos visitando Cartagena y queria coordinar inmersiones en Isla del Rosario.  Somos una pareja Advanced O.W.', True),
    ('cert', 'quiero bucear certificado', True),
    ('cert', 'Hi. We want to complete our PADI open water: we have referrals and e-learning certificates. We would also like a refresher first. How does the 2 day open water referral course cost plus a mini course the day before. 2 persons. Thanks', True),
    ('cert', "Hi, I'm interested in taking PADI Open Water Diver certification course.", True),
    ('cert', "Hi, I'm trying to checkout to take PADI Open Water Diver certification course but the discount of 10% is not showing up. what is the code?", True),
    ('cert', 'Buceo para principiantes', True),
    ('cert', 'Hi,\nMy understanding is that the transportation to rosario is included, in case I decided to do PADI Open Water Diver certification course., correct?', False),
    ('cert', 'do you have an option for 2 dives and 1 night dive so I do one day of diving instead of two?', False),
    ('cert', 'Queria saber los valores de dos buceos o del pack de 5 buceos en 2 dias', False),
    ('cert', 'Mil gracias por la info. Oye, quiero hacerte una pregunta. Estuve consultando con otra agencia, um principalmente para mirar como los lugares y demás, pero pues no conozco. Entonces quería preguntarte si existe como alguna diferencia entre estos lugares al que ustedes van y el que te compartí en la foto.', False),
    ('cert', 'Hi. Is it possible for my son [NOMBRE] a PADi certificat ?', False),
    ('grp', 'Cuál es la tarifa especial para Colombianos? Mi pareja y yo somos de Bogotá', True),
    ('grp', 'Hello, I just want to tell you, I just make a reservation for me and [NOMBRE] for diving with you on Monday 11th of May. And me, I am advanced and we just make both reservations. I just want to ask you if you receive it.', True),
    ('grp', 'Hola!\nMe gustaria tener mas informacion acerca de los cursos de buceo en Cartagena (especificamente en Islas del Rosario)\nSomos dos personas y es la pirmera vez que vamos hacer buceo y sobretodo no tenemos mucho tiempo.\nComo se hace para reservar ?', True),
    ('grp', 'Busco el seguinte:\nVamos en família a Cartagena. 1 buzo avanzado y 2 para bautismo', True),
    ('grp', 'Hola!! Te contacto desde Argentina.  Estaremos visitando Cartagena y queria coordinar inmersiones en Isla del Rosario.  Somos una pareja Advanced O.W.', True),
    ('grp', 'Seguramente tomaremos el paquete de 5 buceos para 2 personas con el traslado saliendo desde cartagena, niche en cocoliso, buceo nuevamente  .\nAqui esta mi duda ,\nSi nos quedamos una segunda noche en cocoliso,\nPodremos regresar con ustedes con el regreso del dia siguiente ?', True),
    ('grp', 'Hi. We want to complete our PADI open water: we have referrals and e-learning certificates. We would also like a refresher first. How does the 2 day open water referral course cost plus a mini course the day before. 2 persons. Thanks', True),
    ('grp', 'nos gusta, somos 2 personas y queremos el de saliendo de cartagena, además somos colombianos', True),
    ('grp', 'Hi. Is it possible for my son [NOMBRE] a PADi certificat ?', False),
    ('grp', 'Queria saber los valores de dos buceos o del pack de 5 buceos en 2 dias', False),
    ('grp', 'hola, cuanto cuesta el paquete de 5 inmersiones?', False),
    ('grp', 'do you have an option for 2 dives and 1 night dive so I do one day of diving instead of two?', False),
    ('nac', 'no soy colombiano', True),
    ('nac', 'not colombian', True),
    ('nac', 'Hola!! Te contacto desde Argentina.  Estaremos visitando Cartagena y queria coordinar inmersiones en Isla del Rosario.  Somos una pareja Advanced O.W.', True),
    ('nac', 'nos gusta, somos 2 personas y queremos el de saliendo de cartagena, además somos colombianos', True),
    ('nac', 'Cuál es la tarifa especial para Colombianos? Mi pareja y yo somos de Bogotá', True),
    ('nac', 'Ese es el precio para ciudadanos colombianos? somos de Bogotá', True),
    ('nac', 'Buenos días. Estoy interesada en el curso básico de buceo. Cuál es el costo para colombianos?', False),
    ('nac', 'Estoy interesada en el curso básico de buceo. Según la página tienen un precio especial para colombianos. Me podrían dar el costo por favor', False),
    ('nac', 'Estoy interesada en el curso básico de buceo. Me podrían dar el costo para colombianos por favor', False),
    ('nac', 'Buenos días. Quiero hacer el paquete de 5 buceos. Cuál es el costo para colombianos por favor?', False),
    ('nac', 'Gracias - y en pesos? Para colombianos?', False),
    ('nac', 'Amigo el precio que está allí es en dólares o pesos colombianos', False),
]

# Reales del golden que NO se usaron para escribir ninguna frase de las redacciones (ver arriba).
# Los dos ultimos salen de las regresiones de la ronda B2 de u3-4 (25-sep, PRE): el certificado
# afirmado dentro de una pregunta que se perdio, y el "¿lo cambio?" fantasma de "listo, como pago".
NUEVOS_U35 = [
    ("cert", "Gracias - yo complete el curso básico el 3 de abril 2025. Tengo que hacer algo especial?", True),
    ("cert", "listo, como pago", False),
    ('cert', 'quiero bucear, ya soy certificado', True),
    ('cert', 'Quiero bucear y tengo el open water', True),
    ('cert', 'Un solo buzo avanzado', True),
    ('cert', 'Buzos certificados', True),
    ('cert', 'certified diver', True),
    ('cert', 'somos buzos certificados', True),
    ('cert', 'Hola! Como estan? Me llamo [NOMBRE] soy buza advanced', True),
    ('cert', 'I have my open water certificate and I’m still a beginner :)', True),
    ('cert', 'Hola quiero sacarme la certificación y estoy en cartagena', True),
    ('cert', 'Quiero hacer la certificación de buceo en agosto que tengo vacaciones.', True),
    ('cert', 'Sería buzo principiante y snorkeling', True),
    ('cert', 'Anything needs to be completed beforehand? I’m gonna need a little refresher.', True),
    ('cert', 'Y en el caso de tomar solo el buceo doble?', False),
    ('cert', 'cupo para snorkeling para dos personas el sábado?', False),
    ('cert', 'We are leaving tomorrow before noon', False),
    ('grp', 'voy solo', True),
    ('grp', 'solo yo', True),
    ('grp', "i'm certified, just me", True),
    ('grp', 'Un solo buzo avanzado', True),
    ('grp', 'Para dos personas', True),
    ('grp', 'cupo para snorkeling para dos personas el sábado?', True),
    ('grp', 'Hello! I have a question about the diving excursion. My husband and I are booked for April 13-14 and are staying in the Rosario islands that night.', True),
    ('grp', 'We are a family of 6 and 3 of us will dive and 3 will snorkeling', True),
    ('grp', 'Hi,\nI just booked a beginner mini diving experience online. I created accounts for my son ([NOMBRE], 17) and myself ([NOMBRE], 49).', True),
    ('grp', 'Y en el caso de tomar solo el buceo doble?', False),
    ('grp', 'Es decir en dos dias tendriamos el certificado haciendo nuestro curso en linea', False),
    ('grp', 'Anything needs to be completed beforehand? I’m gonna need a little refresher.', False),
    ('grp', 'We are leaving tomorrow before noon', False),
]


async def banco_u35() -> None:
    print(f"\n{'=' * 84}\nu3-5 — candidatas (aun no en el codigo)\n{'=' * 84}")
    tot: dict = {}
    async with httpx.AsyncClient() as cli:
        t0 = time.perf_counter()
        for cual, mensaje, esperado, nuevo in [(*c, False) for c in CASOS_U35] + [(*c, True) for c in NUEVOS_U35]:
            ps = [round(await _preguntar(cli, mensaje, U35_CANDIDATAS[cual]), 2) for _ in range(N)]
            ok = all((p >= jev_router.AFFIRMS_MIN) == esperado for p in ps)
            clave = f"{cual}{'*' if nuevo else ''}"
            bien, n = tot.get(clave, (0, 0))
            tot[clave] = (bien + ok, n + 1)
            print(f"  [{'OK ' if ok else 'MAL'}] {clave:<5} esperado={esperado!s:<5} p={ps}  {mensaje[:66]!r}")
    print("  --> " + "  ".join(f"{k}: {b}/{n}" for k, (b, n) in tot.items())
          + f"   (* = nuevos; {time.perf_counter() - t0:.0f} s, umbral {jev_router.AFFIRMS_MIN})")


if __name__ == "__main__":
    # Sin argumento: todo. `u34` = lugar y actividad (las del codigo); `u35` = las candidatas.
    que = sys.argv[1] if len(sys.argv) > 1 else "todo"
    if que in ("todo", "u34"):
        asyncio.run(main())
    if que in ("todo", "u35"):
        asyncio.run(banco_u35())
