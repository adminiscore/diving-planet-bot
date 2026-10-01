"""Banco de calibración de la pregunta de Jev `shares_open_fact` (rag-5, puerta del extractor de notas).

La puerta solo SALTA el extractor de notas cuando Jev está seguro de que el mensaje no cuenta nada del cliente
que haya que apuntar (p < NOTES_SKIP_MAX). Lo que importa, por este orden:
1. ningún positivo por debajo del umbral (se perdería una lesión, una alergia, una ocasión...);
2. cuántos negativos quedan por debajo: cada uno es una nota basura que ya no entra (y una llamada menos).

- POSITIVOS_DISENO: los ejemplos de los tests del extractor y de la batería del enrutador. Con estos (y la
  definición de `src/prompts/memory.py`) se redactó la pregunta.
- POSITIVOS_CIEGOS: casos REALES que no se usaron para redactarla: chats de WhatsApp anonimizados
  (`real-episodes.json`) y las notas buenas que Gonzalo leyó a mano en los rehechos de rag-5.
- NEGATIVOS: los rehechos de rag-5 cuya nota nueva era la pregunta del cliente, inventada o un dato de reserva
  (`docs/robustness/rag-5/por-que-se-rehace-notas-reales.json`), y mensajes normales de la batería del enrutador.
- DUDOSOS: se enseñan, pero no cuentan (ni el extractor ni una persona tendrían claro si apuntar algo).

Nada del examen oculto.

    python -m scripts.sonda_notas
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

POSITIVOS_DISENO = [
    "estoy embarazadita, puedo bucear?",
    "soy epiléptica",
    "tengo una condición cardiaca",
    "perdí una pierna en un accidente, puedo bucear?",
    "soy sordomuda",
    "tengo una lesión medular",
    "Hola, somos 4, mi padre tiene la rodilla operada así que mejor evitar planes muy físicos. Queremos bucear 2 días",
    "Somos 3 personas y uno tiene asma leve.",
    "Soy vegetariana, ¿qué hay para comer?",
    "Tengo alergia al marisco, ¿hay problema?",
    "con mi pareja, tenemos un presupuesto ajustado",
    "hola, quiero hacer buceo con mi pareja, tenemos un presupuesto inferior a 300 € y disponemos de 4 dias, que teneis?",
    "hola, es nuestra luna de miel y queremos bucear desde cartagena",
    "somos pareja, es nuestro aniversario y viajamos con un bebé",
    "mi madre va en silla de ruedas, puede hacer snorkel?",
    "my friend uses a wheelchair",
    "Hola, somos 8, 3 con open water y 2 advanced, presupuesto 2000, uno es vegetariano y otro celiaco, ¿qué nos "
    "recomiendan y cuánto sale?",
]
POSITIVOS_CIEGOS = [
    "Hola entre a su pagina web y me gustaria hacer un dia de buceo el dia de mis cumpleaños el 11 de Mayo, me "
    "gustaria saber qué precio tiene y si hay q reservar con anterioridad. Soy principiante y no se nadar.  Gracias",
    "Hola, estoy llenando el formulario y marque que tomo medicación ocasional para dormir ( no diaria). El sistema "
    "me pide evaluación medica. Para el Discover Dive del 11 de mayo es obligatorio o puedo hacerle igual?",
    "I was able to complete my PADI reactivate course on board a royal Caribbean cruise that I am on now.  My wife "
    "seemed to be very nervous and had mask problems and could not complete her skills test on the boat.   We "
    "snorkeled in Roatan yesterday and swam in Costa Maya today. I am a competitive masters swimmer and swim 12k "
    "per week.  She is a fit 5’6 115 lb active and in shape lady..  we want to look into completing her reactivate "
    "course and dive when we are there.  We will be staying at Bodegas de Santa Clara. June 6-13",
    "Es decir en dos dias tendriamos el certificado haciendo nuestro curso en linea . La persona que me acompana no "
    "habla ni ingles ni espanol pero yo seria la \"interprete\" hay incoveniente con eso ?",
    "Y para transferência tiene descuento? Tengo cuenta local",
    "Cuál es el proceso? Te diría que reagendemos, pero no tengo claro si vuelvo este año o no",
    "Pucha en realidad me parece un poco caro, quedaria en 160 dolares?",
]
NEGATIVOS = [
    # rehechos de rag-5: la nota nueva era la pregunta, inventada o un dato de reserva
    "how much would that be",
    "ah los lunes estan cerrados, y el martes?",
    "y tienen algo para mas dias, como un paquete?",
    "y si somos un grupo grande, bajan el precio",
    "El curso que te he pedido cuánto tiempo dura ?",
    "Estoy interesada en el curso básico de buceo. Me podrían dar el costo para colombianos por favor",
    "Gracias - yo complete el curso básico el 3 de abril 2025. Tengo que hacer algo especial?",
    "Ustedes cotizan los hoteles san pedro y cocoliso",
    "Uno de los buceos puede ser en wreck?",
    "Va quiero comprar sin ir de cartagena",
    "Mi madre puede acompañarme en el buceo y se quedar en la isla de apoyo?",
    "Oye, par de preguntas. Si quisiera también me puedo hospedar con ustedes? Estoy pensando en ir en unos meses de nuevo",
    "Great. We will book diving with you on the website and will book our hotel on the island . Hope you are "
    "operating on Easter Sunday? We want to dive on April 5 and 6. How do we book/pay for the $50 refresher course?",
    "Price?  Can you help me with this information?",
    "Does isla grande count acceptable is it part of the roasirio island^",
    "Anything needs to be completed beforehand? I’m gonna need a little refresher.",
    "incluye el almuerzo?",
    "so, if I understood correctly, booking just for one night will be enough, right?",
    "2 full days course, right?",
    "also- I saw pictures and videos are not included...?",
    "but will have a photographer taking pictures during the divings?",
    "What if I decide to stay one day longer in rosario, can you provide de transfer back to cartagena?",
    "Cuál es la tarifa especial para Colombianos? Mi pareja y yo somos de Bogotá",
    "Ese es el precio para ciudadanos colombianos? somos de Bogotá",
    "Hi. Is it possible for my son [NOMBRE] a PADi certificat ?",
    "So [NOMBRE] can go directly to Diving Planet to start the Open Water part?",
    "Yes … I’ll let to you the form transfer to Dive Planet … but I need of infos of dive center",
    "And full [NOMBRE] infos to fill the form transfer to complete the certification in Cartagena",
    "I was seeing your 5 dive plan - and wanted to see whats the price for stay and dives",
    "do you have an option for 2 dives and 1 night dive so I do one day of diving instead of two?",
    "or 2 day dives?",
    "Solicitud tarifas 2026 - Tucaya Colombia - Diving Planet",
    "So should I book 2  separately? One for diving and one for snorkeling",
    "Is there a discount code?",
    "Its been more than 1.5 years since last dive. So is there additional cost for refresher?",
    "pero i ria en el la lancha solo el no hay como pagar para acompañarlo aun que no vallamos a sumergirnos",
    # mensajes normales de la batería del enrutador
    "¿cuál es la política de cancelación?",
    "¿qué pasa si llueve ese día?",
    "puedo pagar con tarjeta?",
    "quiero bucear mañana, cuánto cuesta?",
    "si, tengo el AOWD, además tengo 3 amigos que quieren hacer alguna actividad",
    "gracias",
    "desde cartagena",
    "no soy colombiano",
]
DUDOSOS = [
    "pueden hacer snorkel los dos o el pequeno esta muy chico?",
    "uy que caro, tienen algun descuento",
    "Hola para residentes en colombia (3 años) no aplica el desc colombia o?",
    "Amazing thank you! We’re thinking about extending our stay on the Rosario islands. Would it be possible to get "
    "dropped back off there after diving on the 14th?",
    "Looking for recommendations for hotels for a solo backpacker is Isla Grande part of rosario island?",
    "Sorry again, do you have a more detailed schedule ?\nFor instance, what time does the course finish on the first "
    "day?\nBecause I wanted to know if I will have time to enjoy the hotel as well.",
    "Porque quiero saber si me puedo alojar allí directamente o en la misma isla para no tener que quedarme en "
    "Cartagena. (soy Cartagenera por cierto)",
    "Mi vuelo es mañana y con lo del cierre me tocó cancelar",
]
N = 2


async def main() -> None:
    q = jev_router._SHARES_OPEN_FACT_Q["instructions"]
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient() as cli:
        async def una(m):
            async with sem:
                return await _preguntar(cli, m, q)

        async def runs(m):
            return await asyncio.gather(*(una(m) for _ in range(N)))

        grupos = {"POS-diseño": POSITIVOS_DISENO, "POS-ciego": POSITIVOS_CIEGOS, "NEG": NEGATIVOS, "DUDOSO": DUDOSOS}
        res = {g: await asyncio.gather(*(runs(m) for m in msgs)) for g, msgs in grupos.items()}
    t = jev_router.NOTES_SKIP_MAX
    for g, msgs in grupos.items():
        # conservador: un positivo se pierde si ALGUNA repetición cae bajo el umbral (min); un negativo solo
        # se ahorra si TODAS caen (max)
        clave = min if g.startswith("POS") else max
        for m, vals in sorted(zip(msgs, res[g]), key=lambda x: clave(x[1])):
            print(f"{g:10s} {clave(vals):.2f} [{' '.join(f'{v:.2f}' for v in vals)}]  {m[:100]!r}")
        print()
    for g in ("POS-diseño", "POS-ciego"):
        print(f"{g}: perdidos por debajo de {t}: {sum(min(v) < t for v in res[g])}/{len(res[g])}")
    print(f"NEG: ahorrados por debajo de {t}: {sum(max(v) < t for v in res['NEG'])}/{len(res['NEG'])}")
    for umbral in (0.1, 0.2, 0.3, 0.4, 0.5):
        perd = sum(min(v) < umbral for g in ("POS-diseño", "POS-ciego") for v in res[g])
        ahor = sum(max(v) < umbral for v in res["NEG"])
        print(f"  umbral {umbral}: positivos perdidos {perd}, negativos ahorrados {ahor}/{len(res['NEG'])}")


if __name__ == "__main__":
    asyncio.run(main())
