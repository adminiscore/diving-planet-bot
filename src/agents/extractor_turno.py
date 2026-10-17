"""ex-4 (fase EX, 12-oct): el extractor "LLM primero" — entender el mensaje del cliente con UNA llamada.

Hoy el regex lee primero y manda, y las redes LLM solo rellenan huecos leyendo el historial entero como turnos de chat:
en el banco ex-0 eso inventa datos en el 22,8 % de los casos ("gracias" → buceo certificado; "Muchas gracias!" →
colombiano). Aquí, en cambio:

1. El modelo ve SOLO el mensaje del cliente, la última pregunta del bot (para entender respuestas cortas) y lo que ya
   sabemos; nunca el historial como turnos de chat.
2. Cada dato trae su CITA del mensaje del cliente, y el código comprueba que la cita está de verdad en el mensaje: sin
   cita verificable no hay dato (lo que el modelo saque del historial o del texto del bot no puede pasar).
3. Las pistas seguras (la lista cerrada de hoteles e islas del Rosario) van en el prompt; el regex no decide.

Si la llamada falla, devuelve {} y el turno sigue con lo de hoy (degradación). Medida: `scripts.run_extraction_eval
--banco ex0 --modo llm-primero`. Plan: docs/robustness/regex/plan-ex-entender-con-ia.md.
"""
from __future__ import annotations

import json
import logging
import re
import time

from openai import AsyncOpenAI

from src.config import settings
from src.domain import activities as dom
from src.llm_client import trace_openai
from src.utils.text import strip_accents

logger = logging.getLogger("uvicorn.error")

CAMPOS = ("activity", "is_certified", "group_size", "group_allocation", "location", "is_colombian",
          "last_dive_over_2_years")
# ex-8: la actividad que el cliente ELIGE sale del registro de actividades (fuente única; sin listas a mano). El
# refresher (es parte del buceo certificado tras más de 2 años) y el acompañante (no es una actividad para uno mismo)
# no se eligen aquí.
ACTIVIDADES = tuple(a for a in dom.activity_ids() if a not in ("refresher", "companion"))
# El reparto del grupo, con las actividades que se reparten de verdad entre personas.
ACTIVIDADES_REPARTO = ("certified_diving", "minicourse", "snorkel", "padi_open_water", "padi_open_water_referral",
                       "padi_advanced", "padi_rescue", "padi_divemaster", "padi_specialty")
# ex-7: más las personas del grupo que no han elegido actividad (decisión del owner, 15-sep: si solo se dice que no
# están certificadas, quedan "sin decidir" y el bot les recomienda opciones; `_take_undecided_members`).
CLAVES_REPARTO = (*ACTIVIDADES_REPARTO, "undecided")
# Hechos del turno que no son campos del estado: el grupo mezclado (paga en USD) y "quiere bucear" (con la
# certificación decide el buceo certificado, ver `extraer_turno`).
EXTRAS = ("mixed_nationality", "quiere_bucear")
# Respuestas cortas a la pregunta del bot ("no", "1", "sí"): la cita es el mensaje entero.
_CITA_MIN_PALABRAS_SOLAS = 1


def _dato(tipo: dict, descripcion: str) -> dict:
    return {
        "type": ["object", "null"],
        "description": descripcion + " null si el cliente no lo AFIRMA en su mensaje.",
        "properties": {"valor": tipo, "cita": {"type": "string",
                                                "description": "Las palabras EXACTAS del mensaje del cliente que lo dicen."}},
        "required": ["valor", "cita"],
        "additionalProperties": False,
    }


ESQUEMA = {
    "type": "object",
    "properties": {
        # Primero: el modelo lo decide antes de pensar en la actividad (con la certificación, ver `extraer_turno`).
        "quiere_bucear": _dato({"type": "boolean"},
                               "true si muestra que quiere bucear (de aquí en adelante): pide o quiere coordinar, reservar o agendar "
                               "inmersiones o buceos, pregunta sus precios o fechas, o contesta a una pregunta del bot "
                               "sobre su plan de buceo. No hace falta que diga qué actividad."),
        "activity": _dato({"type": "string", "enum": list(ACTIVIDADES)}, "La actividad que el cliente ELIGE para sí."),
        "is_certified": _dato({"type": "boolean"}, "Si quien escribe (o su grupo) YA es buzo certificado."),
        "group_size": _dato({"type": "integer"}, "Cuántas personas van en total en el plan."),
        "group_allocation": _dato({"type": "object",
                                   "properties": {a: {"type": ["integer", "null"]} for a in CLAVES_REPARTO},
                                   "required": list(CLAVES_REPARTO), "additionalProperties": False},
                                  "Cuántas personas hacen cada actividad, solo si el grupo se reparte entre VARIAS."),
        "location": _dato({"type": "string", "enum": ["cartagena", "island"]},
                          "Desde dónde SALE el cliente: 'cartagena' si sale de Cartagena; 'island' si ya está alojado "
                          "en las Islas del Rosario."),
        "is_colombian": _dato({"type": "boolean"}, "Si quien escribe es colombiano o residente en Colombia."),
        "last_dive_over_2_years": _dato({"type": "boolean"}, "Si su última inmersión fue hace MÁS de 2 años."),
        "mixed_nationality": _dato({"type": "boolean"},
                                   "true si el grupo mezcla colombianos (o residentes en Colombia) con extranjeros."),
        # G-10 (decisión de Gadea, 14-oct): en qué idioma está escrito el mensaje; si no es español ni inglés, el bot
        # contesta en inglés (conversational_core._otro_idioma_en_ingles).
        "idioma": {"type": "string",
                   "description": "Código ISO 639-1 del idioma PRINCIPAL en que está escrito el mensaje (es, en, pt, "
                                  "fr, de, it…). Unas palabras sueltas de otro idioma no lo cambian."},
    },
    "required": [*CAMPOS, *EXTRAS, "idioma"],
    "additionalProperties": False,
}

# 13-oct (Gonzalo, flag `nombre_por_extractor`): el NOMBRE con que se presenta quien escribe, con su cita. Lo leía una
# regex ("soy X" con una lista de palabras excluidas) y "yo soy gringo" saludaba "¡Hola, Gringo!" (hallazgo de ex-3,
# HISTORY 0.31.18): añadir "gringo" a la lista sería un parche (mañana "soy paisa", "soy argentino"). Con el flag
# apagado la llamada es exactamente la de antes (ni el campo ni su regla).
ESQUEMA_CON_NOMBRE = {
    **ESQUEMA,
    "properties": {**ESQUEMA["properties"],
                   "nombre": _dato({"type": "string"},
                                   "El nombre propio con que se presenta quien escribe.")},
    "required": [*ESQUEMA["required"], "nombre"],
}
# CAL-C3 (17-oct, flag `hotel_por_extractor`): el HOTEL donde se aloja, con su cita. Lo leía solo el regex con la lista
# cerrada de hoteles de las islas: "staying at Isla Mulata on Isla Grande" (cal-41) y "We will be staying at Bodegas de
# Santa Clara" (cal-67/68, un hotel de Cartagena) se perdían y el bot preguntaba "¿En qué hotel o isla te hospedas?".
# Sin lista: vale el nombre tal como lo escribe el cliente si está en su mensaje. Con el flag apagado, ni el campo ni
# su regla (la llamada es exactamente la de antes).
CAMPO_HOTEL = _dato({"type": "string"},
                    "El nombre del hotel, hostal o casa donde se aloja o se alojará quien escribe, tal como lo escribe.")
REGLA_HOTEL_ES = (
    "\n- hotel: el nombre del sitio donde se aloja o se alojará quien escribe (\"nos quedamos en el Hotel Caribe\", "
    "\"staying at Isla Mulata\"), tal como lo escribe. Preguntar por un hotel, recomendarlo o \"aún no lo sabemos\" NO es "
    "su hotel. El hotel no dice por sí solo desde dónde sale (location)."
)
REGLA_HOTEL_EN = (
    "\n- hotel: the name of the place where the writer stays or will stay (\"we're staying at Hotel Caribe\", \"staying at "
    "Isla Mulata\"), as they write it. Asking about a hotel, recommending one or \"we don't know yet\" is NOT their hotel. "
    "The hotel alone does not say where they depart from (location)."
)


def _esquema(con_nombre: bool, con_hotel: bool) -> dict:
    """El esquema de la llamada con los campos opcionales encendidos (sin ellos, el de siempre)."""
    if not con_hotel:
        return ESQUEMA_CON_NOMBRE if con_nombre else ESQUEMA
    base = ESQUEMA_CON_NOMBRE if con_nombre else ESQUEMA
    return {**base, "properties": {**base["properties"], "hotel": CAMPO_HOTEL}, "required": [*base["required"], "hotel"]}
# 13-oct (Gonzalo, flag `extractor_precio_elige`): la regla general ponía "¿cuánto cuesta el buceo certificado?" como
# ejemplo de algo que NO es un dato, y la de `activity` dice que preguntar el precio de un producto nombrado SÍ lo elige
# (decisión de Gadea 14/27-sep). Dos órdenes contrarias: de ahí la variación de ex-8 ("a veces no cuenta como
# elegido") y las repreguntas "¿buceo, minicurso, snorkel o curso?" de regateo-grupo-6 (rondas ex8-B2 y ex7-B). El
# ejemplo vale para la CERTIFICACIÓN (preguntar ese precio no dice que sea buzo), no para la actividad.
GENERAL_PRECIO_ES = ('Una pregunta ("¿puedo bucear embarazada?", "¿cuánto cuesta el buceo certificado?"), una hipótesis '
                     '("si decidiera hacer el curso…") o algo que nombra sin elegirlo no es un dato.')
GENERAL_PRECIO_ES_V2 = ('Una pregunta ("¿puedo bucear embarazada?") no dice que esté embarazada ni que vaya a bucear; '
                        'preguntar el precio de un producto ("¿cuánto cuesta el buceo certificado?") no dice que el '
                        'cliente sea buzo certificado, pero SÍ elige esa actividad (ver activity). Una hipótesis ("si '
                        'decidiera hacer el curso…") o algo que nombra sin elegirlo no es un dato.')
GENERAL_PRECIO_EN = ('A question ("can I dive pregnant?", "how much is certified diving?"), a hypothesis ("in case I '
                     'decided to do the course…") or something they mention without choosing it is not a fact.')
GENERAL_PRECIO_EN_V2 = ('A question ("can I dive pregnant?") does not say they are pregnant or will dive; asking the '
                        'price of a product ("how much is certified diving?") does not say the customer is a certified '
                        'diver, but it DOES choose that activity (see activity). A hypothesis ("in case I decided to do '
                        'the course…") or something they mention without choosing it is not a fact.')

REGLA_NOMBRE_ES = (
    "\n- nombre: solo el nombre propio con que se presenta quien escribe (\"me llamo Ana\", \"soy Rocío\", \"I'm Tom\"). "
    "Una nacionalidad, un origen, una profesión o una descripción NO son nombres (\"soy gringo\", \"soy paisa\", "
    "\"soy argentina\", \"soy buzo\", \"soy principiante\", \"soy el papá de…\"). Si dudas, null."
)
REGLA_NOMBRE_EN = (
    "\n- nombre: only the proper first name the writer introduces themselves with (\"my name is Ana\", \"I'm Tom\", "
    "\"soy Rocío\"). A nationality, origin, job or description is NOT a name (\"I'm a gringo\", \"I'm Canadian\", "
    "\"I'm a diver\", \"I'm a beginner\", \"I'm the dad of…\"). If unsure, null."
)


def _actividades(lang: str) -> str:
    """Una línea por actividad elegible con su nombre del registro (fuente única). No se usa `for_whom`: el de
    certified_diving dice que es "la opción por DEFECTO cuando alguien pide bucear sin más", lo contrario de la regla de
    Gadea (14 y 27-sep: no suponer la actividad; recomendar). Corregirlo en el registro es de ex-9, cuando se retire el
    camino viejo que lo usa."""
    lineas = []
    for a in ACTIVIDADES:
        act = dom.by_id(a)
        nombre = (act.label.get(lang) or act.label["es"]) if act else a
        lineas.append(f"  · {a}: {nombre}")
    return "\n".join(lineas)


def _pistas_islas() -> str:
    from src.agents.rag_agent import (
        AMBIGUOUS_LOCATION_NAMES,  # lazy: lista cerrada de hoteles e islas del Rosario
    )

    return ", ".join(AMBIGUOUS_LOCATION_NAMES)


SISTEMA_ES = """Eres el lector de mensajes de Coral, la asistente de reservas de Diving Planet (buceo y snorkel en las Islas del Rosario, saliendo desde Cartagena o desde las propias islas). Lees UN mensaje del cliente y devuelves SOLO los datos de la reserva que el cliente AFIRMA en ese mensaje, cada uno con la cita exacta de sus palabras.

Reglas:
- Solo lo que el cliente afirma de sí mismo o de su grupo en ESTE mensaje. Una pregunta ("¿puedo bucear embarazada?", "¿cuánto cuesta el buceo certificado?"), una hipótesis ("si decidiera hacer el curso…") o algo que nombra sin elegirlo no es un dato.
- Lo que el cliente dice de OTRA persona ("él no es certificado") no cambia los datos de quien escribe; sí puede servir para el reparto del grupo.
- Lo que el cliente dice de OTRA persona que hace algo distinto ("él quiere hacer snorkel") va en group_allocation junto con lo que ya sabemos de quien escribe.
- Usa la pregunta que el bot acaba de hacer solo para entender una respuesta corta ("no" o "no, hace poco buceé" a "¿han pasado más de 2 años?" = last_dive_over_2_years false; "1" a "¿cuántas personas?" = group_size 1). Nunca saques datos del texto del bot.
- No repitas lo que ya sabemos salvo que el cliente lo cambie en este mensaje.
- activity: la que el cliente ELIGE para sí. Elige cuando nombra o describe una actividad o un producto concreto como lo que quiere hacer, reservar, ya tiene reservado o del que quiere saber el precio, o cuando contesta a la pregunta del bot quedándose con una de las opciones que le ofrece. Si el bot pregunta qué hará otra persona del grupo, su respuesta es la actividad de esa persona. NO elige cuando habla de bucear en general sin decir cuál ("quiero bucear", "me gustaría un día de buceo", "quiero bucear con mi amigo", "es mi primera vez", "nunca he buceado") ni cuando pregunta qué opciones hay o si algo es posible para él (el bot recomendará). Pedir apuntarse a una actividad que nombra, aunque sea preguntando ("¿hay sitio en el minicurso del sábado?"), sí la elige. Nunca pongas una que tú deducirías para recomendarle. certified_diving: nombra el buceo certificado ("bucear certificado") o un producto de buceo para certificados (fun dives, un plan o paquete de N buceos, N inmersiones); si solo dice que es buzo y que quiere bucear, NO lo pongas tú: el bot lo decide con quiere_bucear e is_certified. minicourse: nombra el minicurso o el bautismo, o quiere PROBAR el buceo o el buceo para principiantes. padi_open_water: sacarse la certificación, el curso básico o el Open Water. padi_open_water_referral: terminar aquí un Open Water empezado en otro centro (referido). padi_advanced: HACER el curso avanzado (si dice que YA es Advanced, eso es is_certified true, no este curso). padi_course / padi_specialty: un curso PADI o una especialidad sin decir cuál. Actividades posibles (id: nombre):
{actividades}
- location: desde dónde sale. Si dice que está, estará, va o viene a Cartagena ("estoy en Cartagena", "vamos a Cartagena", "bucear en Cartagena", "estaremos visitando Cartagena") y no dice que se aloja en las islas → cartagena. Alojado en las islas, en un hotel de las islas o "sin ir de Cartagena" → island (nombrar las islas como el sitio donde se bucea no basta). Llegar mañana sin decir dónde, o preguntar por un hotel, por el punto de encuentro ("¿dónde es el punto de encuentro en Cartagena?") o por de dónde sale la lancha NO es su ubicación. La cita de location tiene que nombrar el lugar (Cartagena, las islas, un hotel).
- is_certified: true solo si dice que tiene certificación o un nivel de buceo (buzo certificado, Open Water, Advanced…), él o su grupo; false si dice que no la tiene, que nunca ha buceado o que no tiene experiencia. Querer bucear no dice nada de la certificación.
- quiere_bucear: true si quiere bucear o hacer inmersiones (lo dice, pide buceos, sus precios o una fecha para bucear) o contesta a una pregunta del bot sobre su plan de buceo; no hace falta que diga qué actividad. Preguntar si algo es posible ("¿puedo bucear si…?") o contar buceos que ya hizo no es querer bucear.
- is_colombian: si dice que es colombiano, de una ciudad de Colombia o residente en Colombia (también si pide para sí el precio "para colombianos" o "en pesos por ser colombiano"). Nunca lo deduzcas del idioma en que escribe ni de su nombre. Si el grupo mezcla colombianos y extranjeros: mixed_nationality true e is_colombian null.
- group_size: solo si dice CUÁNTAS personas van ("voy solo", "solo yo" = 1; "somos 3" = 3; "mi pareja y yo", "con mi amigo", "con mi novia" = 2). Hablar en primera persona ("yo", "quiero") no dice el tamaño del grupo.
- group_allocation: cuántas personas hacen cada actividad cuando el grupo se reparte entre VARIAS, contando a quien escribe (con lo que ya sabemos de él). Si ya sabemos cuántos van y el cliente suma a alguien ("viene también uno que hace snorkel"), el reparto incluye a los que ya iban con su actividad. Usa undecided para las personas del grupo de las que el mensaje no dice qué harán, por ejemplo cuando solo dice que no están certificadas ("somos 3, uno no está certificado" = certified_diving 2, undecided 1); nunca conviertas un dato de certificación en minicourse o snorkel. Si un lado del grupo no tiene número ("yo buceo y mis amigos snorkel"), no pongas el reparto: el bot preguntará cuántos son.
- last_dive_over_2_years: true solo si su última inmersión fue hace MÁS de 2 años; "1,5 años", "el año pasado" o "hace poco" = false.
- idioma: el idioma en que está escrito la mayor parte del mensaje (código ISO 639-1). Unas palabras sueltas de otro idioma dentro de un mensaje en español siguen siendo "es"; nombrar un idioma ("mi amigo habla francés") no es escribir en él.
- Si los datos están en partes distintas del mensaje, la cita puede ser varios trozos literales separados por " … ".
- La cita debe ser texto copiado literalmente del mensaje del cliente.

Hoteles e islas del Rosario (si el cliente está alojado en uno, location = island): {islas}"""

SISTEMA_EN = """You read messages for Coral, the booking assistant of Diving Planet (diving and snorkeling in the Rosario Islands, departing from Cartagena or from the islands). You read ONE customer message and return ONLY the booking facts the customer STATES in that message, each with the exact quote of their words.

Rules:
- Only what the customer states about themselves or their group in THIS message. A question ("can I dive pregnant?", "how much is certified diving?"), a hypothesis ("in case I decided to do the course…") or something they mention without choosing it is not a fact.
- What the customer says about ANOTHER person ("he isn't certified") does not change the writer's facts; it may count for the group split.
- What the customer says about ANOTHER person doing something different ("he wants to snorkel") goes into group_allocation together with what we already know about the writer.
- Use the bot's last question only to understand a short answer ("no" or "no, I dove recently" to "has it been more than 2 years?" = last_dive_over_2_years false; "1" to "how many people?" = group_size 1). Never take facts from the bot's text.
- Do not repeat what we already know unless the customer changes it in this message.
- activity: the one the customer CHOOSES for themselves. They choose when they name or describe a concrete activity or product as what they want to do, book, have already booked or want the price of, or when they answer the bot's question by taking one of the options it offers. If the bot asks what another person in the group will do, the answer is that person's activity. They do NOT choose when they talk about diving in general without saying which ("I want to dive", "I'd like a day of diving", "I want to dive with my friend", "it's my first time", "I've never dived") or when they ask what options there are or whether something is possible for them (the bot will recommend). Asking to join an activity they name, even as a question ("is there room in Saturday's mini course?"), does choose it. Never put one you would infer to recommend. certified_diving: they name certified diving or a product for certified divers (fun dives, a plan or package of N dives, N dives); if they only say they are a diver and want to dive, do NOT put it yourself: the bot decides it from quiere_bucear and is_certified. minicourse: they name the mini course or discover scuba, or want to TRY diving or beginner diving. padi_open_water: getting certified, the basic course or the Open Water. padi_open_water_referral: finishing here an Open Water started at another center (referral). padi_advanced: TAKING the advanced course (if they say they ARE Advanced, that is is_certified true, not this course). padi_course / padi_specialty: a PADI course or a specialty without saying which. Possible activities (id: name):
{actividades}
- location: where they depart from. If they say they are, will be, are going to or are visiting Cartagena ("I'm in Cartagena", "we'll be in Cartagena", "diving in Cartagena") and do not say they stay on the islands → cartagena. Staying on the islands or at an island hotel → island (naming the islands as the place where you dive is not enough). Arriving tomorrow without saying where, or asking about a hotel, the meeting point ("where is the meeting point in Cartagena?") or where the boat leaves from is NOT their location. The location quote must name the place (Cartagena, the islands, a hotel).
- is_certified: true only if they say they have a certification or a diving level (certified diver, Open Water, Advanced…), themselves or their group; false if they say they don't have one, have never dived or have no experience. Wanting to dive says nothing about certification.
- quiere_bucear: true if they want to dive or do dives (they say so, ask for dives, their prices or a date to dive) or answer a bot question about their diving plan; they need not say which activity. Asking whether something is possible ("can I dive if…?") or telling about dives already done is not wanting to dive.
- is_colombian: if they say they are Colombian, from a Colombian city or a resident of Colombia (also if they ask for themselves the price "for Colombians"). Never infer it from the language they write in or from their name. If the group mixes Colombians and foreigners: mixed_nationality true and is_colombian null.
- group_size: only if they say HOW MANY people go ("just me" = 1; "we are 3" = 3; "my partner and I", "with my friend", "with my girlfriend" = 2). Speaking in first person ("I", "I want") does not give the group size.
- group_allocation: how many people do each activity when the group splits across SEVERAL, counting the writer (with what we already know about them). If we already know how many are going and the customer adds someone ("one more is coming to snorkel"), the split includes those already going with their activity. Use undecided for people in the group whose activity the message does not say, e.g. when it only says they are not certified ("we are 3, one is not certified" = certified_diving 2, undecided 1); never turn a certification fact into minicourse or snorkel. If one side of the group has no number ("I dive and my friends snorkel"), leave the split out: the bot will ask how many.
- last_dive_over_2_years: true only if their last dive was MORE than 2 years ago; "1.5 years", "last year" or "recently" = false.
- idioma: the language most of the message is written in (ISO 639-1 code). A few loose words of another language inside a Spanish message are still "es"; naming a language ("my friend speaks French") is not writing in it.
- If the facts are in different parts of the message, the quote may be several literal pieces separated by " … ".
- The quote must be text copied literally from the customer's message.

Rosario hotels and islands (if the customer is staying at one, location = island): {islas}"""


def _norm(texto: str) -> list[str]:
    return re.findall(r"\w+", strip_accents(texto or "").lower())


def _trozo_en(c: list[str], m: list[str]) -> bool:
    return any(m[i:i + len(c)] == c for i in range(len(m) - len(c) + 1))


def cita_verificable(cita: str, mensaje: str) -> bool:
    """La cita está de verdad en el mensaje del cliente: sus palabras, en orden y seguidas (ignorando mayúsculas,
    tildes y puntuación); puede venir en varios trozos separados por "…" o "...", y cada trozo tiene que estar. ex-7:
    también vale sin esos separadores si se parte en trozos literales del mensaje, en orden y de al menos 2 palabras
    (una lista en varias líneas: "2 adults (ages 42, 19) 1 youth (age 17) 1 Adult (Age 43)…" saltándose la línea
    "Snorkeling" se descartaba). Una cita vacía o que no aparece = el dato no sale del mensaje."""
    m = _norm(mensaje)
    trozos = [_norm(t) for t in re.split(r"…|\.\.\.", cita or "")]
    trozos = [t for t in trozos if t]
    if bool(trozos) and all(len(t) >= _CITA_MIN_PALABRAS_SOLAS and _trozo_en(t, m) for t in trozos):
        return True
    return bool(trozos) and all(_en_trozos_seguidos(t, m) for t in trozos)


_TROZO_MIN_PALABRAS = 2


def _en_trozos_seguidos(c: list[str], m: list[str]) -> bool:
    """¿Se parte la cita `c` en trozos seguidos del mensaje `m`, en orden, de al menos `_TROZO_MIN_PALABRAS` palabras?
    Voraz: en cada paso, el trozo más largo que empieza donde va la cita (palabras sueltas no cosen una cita)."""
    i = j = 0
    while i < len(c):
        mejor, desde = 0, -1
        for k in range(j, len(m)):
            largo = 0
            while i + largo < len(c) and k + largo < len(m) and m[k + largo] == c[i + largo]:
                largo += 1
            if largo > mejor:
                mejor, desde = largo, k
        if mejor < _TROZO_MIN_PALABRAS:
            return False
        i, j = i + mejor, desde + mejor
    return True


def _lugares() -> set[str]:
    """Palabras de lugar (lista cerrada): Cartagena, islas/hotel y los nombres de hoteles e islas del Rosario."""
    from src.agents.rag_agent import AMBIGUOUS_LOCATION_NAMES  # lazy

    palabras = {"cartagena", "isla", "islas", "island", "islands", "rosario", "hotel", "hostel", "hostal"}
    for nombre in AMBIGUOUS_LOCATION_NAMES:
        palabras.update(w for w in _norm(nombre) if len(w) > 3)
    return palabras


def nombra_un_lugar(cita: str) -> bool:
    """La cita de la ubicación nombra un lugar (como `ORIGEN_DEL_CLIENTE` de s4-28): "im getting in tmrw" no."""
    return bool(set(_norm(cita)) & _lugares())


def _contexto(mensaje: str, pregunta_bot: str | None, sabido: dict, lang: str) -> str:
    sabido_txt = json.dumps({k: v for k, v in (sabido or {}).items() if v not in (None, [], {})}, ensure_ascii=False)
    if lang == "es":
        return (f"Última pregunta del bot (solo para entender una respuesta corta): {pregunta_bot or '(ninguna)'}\n"
                f"Lo que ya sabemos: {sabido_txt}\n\nMENSAJE DEL CLIENTE:\n{mensaje}")
    return (f"Bot's last question (only to understand a short answer): {pregunta_bot or '(none)'}\n"
            f"What we already know: {sabido_txt}\n\nCUSTOMER MESSAGE:\n{mensaje}")


def ultima_pregunta_del_bot(history: list[dict] | None, max_chars: int = 300) -> str | None:
    """El final del último mensaje del bot (donde va su pregunta), para entender respuestas cortas."""
    for turno in reversed(history or []):
        if turno.get("role") == "assistant" and turno.get("content"):
            texto = re.sub(r"\s+", " ", turno["content"]).strip()
            return texto[-max_chars:]
    return None


async def extraer_turno(mensaje: str, *, history: list[dict] | None = None, sabido: dict | None = None,
                        lang: str = "es", modelo: str | None = None, client: AsyncOpenAI | None = None) -> dict | None:
    """{campo: valor} con SOLO los datos que el cliente afirma en `mensaje` y cuya cita se verifica en él; None si la
    llamada falló (el turno sigue con lo de hoy). Los atributos `ultimo_*` de la función son solo para la medida y
    el log (globales: no usarlos para decidir, hay turnos a la vez)."""
    extraer_turno.ultimo_motivo = {}
    if not mensaje or not mensaje.strip():
        return {}
    sistema = (SISTEMA_ES if lang == "es" else SISTEMA_EN).replace("{islas}", _pistas_islas()).replace(
        "{actividades}", _actividades(lang))
    if settings.extractor_precio_elige:
        sistema = sistema.replace(GENERAL_PRECIO_ES, GENERAL_PRECIO_ES_V2).replace(GENERAL_PRECIO_EN, GENERAL_PRECIO_EN_V2)
    if settings.extractor_aclaraciones:
        # EX-EXTRACTOR-1: la regla de la ubicación con la negación primero (ver UBICACION_NEGACION_*).
        sistema = sistema.replace(UBICACION_HOY_ES, UBICACION_NEGACION_ES).replace(UBICACION_HOY_EN, UBICACION_NEGACION_EN)
    if settings.extractor_todo_lo_dicho:
        # EX-EST-2: extraer también lo ya sabido (ver TODO_LO_DICHO_*).
        sistema = sistema.replace(TODO_LO_DICHO_HOY_ES, TODO_LO_DICHO_ES).replace(TODO_LO_DICHO_HOY_EN, TODO_LO_DICHO_EN)
        sistema = sistema.replace(GRUPO_HOY_ES, GRUPO_NUMERO_ES).replace(GRUPO_HOY_EN, GRUPO_NUMERO_EN)
        sistema = sistema.replace(ACTIVIDAD_EJEMPLOS_HOY_ES, ACTIVIDAD_EJEMPLOS_ES).replace(
            ACTIVIDAD_EJEMPLOS_HOY_EN, ACTIVIDAD_EJEMPLOS_EN)
        sistema = sistema.replace(RESIDENTE_HOY_ES, RESIDENTE_ES).replace(RESIDENTE_HOY_EN, RESIDENTE_EN)
        sistema = sistema.replace(ELIGE_HOY_ES, ELIGE_ES).replace(ELIGE_HOY_EN, ELIGE_EN)
    con_nombre = settings.nombre_por_extractor
    if con_nombre:
        sistema += REGLA_NOMBRE_ES if lang == "es" else REGLA_NOMBRE_EN
    con_hotel = settings.hotel_por_extractor
    if settings.sin_cedula_extranjero:
        # CAL-C (17-oct, decisión de Álvaro): sin cédula colombiana → no es colombiano (paga en USD). Ver SIN_CEDULA_*.
        sistema = sistema.replace(SIN_CEDULA_HOY_ES, SIN_CEDULA_ES).replace(SIN_CEDULA_HOY_EN, SIN_CEDULA_EN)
    if con_hotel:
        sistema += REGLA_HOTEL_ES if lang == "es" else REGLA_HOTEL_EN
    modelo = modelo or settings.extractor_turno_model
    t0 = time.perf_counter()
    try:
        client = client or trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        resp = await client.chat.completions.create(
            model=modelo,
            messages=[{"role": "system", "content": sistema},
                      {"role": "user", "content": _contexto(mensaje, ultima_pregunta_del_bot(history), sabido or {}, lang)}],
            response_format={"type": "json_schema",
                             "json_schema": {"name": "datos_del_turno", "strict": True,
                                             "schema": _esquema(con_nombre, con_hotel)}},
            temperature=0.0,
            # EX-EST-1 (14-oct): con los campos nuevos (idioma, nombre, quiere_bucear...) 400 cortaba el JSON (2 de
            # cada 1.000 llamadas en el banco: "Unterminated string" -> el turno caía al camino viejo).
            max_tokens=700,
        )
        datos = json.loads(resp.choices[0].message.content or "{}")
        uso = getattr(resp, "usage", None)
        detalle = getattr(uso, "prompt_tokens_details", None)
        extraer_turno.ultimo_uso = {"entrada": getattr(uso, "prompt_tokens", 0) or 0,
                                    "cache": getattr(detalle, "cached_tokens", 0) or 0,
                                    "salida": getattr(uso, "completion_tokens", 0) or 0}
    except Exception as exc:  # noqa: BLE001 — nunca romper el turno: se sigue con lo de hoy
        logger.warning(f"[LLM_EXTRACTOR][DEGRADED] extractor_turno: {exc}")
        return None
    extraer_turno.ultimo_segundos = time.perf_counter() - t0
    salida, descartes = {}, {}
    for campo in (*CAMPOS, *EXTRAS, *(("nombre",) if con_nombre else ()), *(("hotel",) if con_hotel else ())):
        d = datos.get(campo)
        if not isinstance(d, dict) or d.get("valor") in (None, "", [], {}):
            continue
        valor, cita = d["valor"], d.get("cita") or ""
        if campo == "group_allocation":
            valor = {k: v for k, v in valor.items() if v}
            if len(valor) < 2:  # un reparto de una sola actividad no es un reparto
                continue
        if not cita_verificable(cita, mensaje):
            if (campo == "activity" and settings.extractor_cita_del_cliente and history
                    and cita_verificable(cita, ultima_pregunta_del_bot(history) or "")):
                # CAL-C2: aceptar lo que propone el bot ("nos gusta" tras "te propongo la salida de 2 inmersiones") se
                # citaba con el texto del BOT 2 de 3 veces y se descartaba. Solo la actividad, y solo si la cita está
                # en la última pregunta del bot (la opción existe; que la acepta lo decide el modelo, como hoy). No se
                # toca el prompt: cambiarlo movía otros campos (banco ex0 5 → 8 inventos; el tío certificado de cal-17
                # perdía la certificación 3 de 4 con "reservar o apartar un cupo es querer bucear").
                salida[campo] = valor
                logger.info(f"[EXTRACT][CAL-C2] actividad citada de la propuesta del bot: {cita!r}")
                continue
            descartes[campo] = f"cita no está en el mensaje: {cita!r}"
            continue
        if campo == "location" and not nombra_un_lugar(cita):
            descartes[campo] = f"la cita no nombra un lugar: {cita!r}"
            continue
        if campo == "hotel" and not (isinstance(valor, str) and cita_verificable(valor, mensaje)):
            descartes[campo] = f"el nombre del hotel no está en el mensaje: {valor!r}"
            continue
        salida[campo] = valor
    # Regla del negocio (ex-8): un buzo certificado (lo dice ahora o ya se sabe) que quiere bucear y no elige otra cosa
    # hace buceo certificado. La decide el código con dos hechos que el cliente afirma; el modelo, cuando la deducía,
    # razonaba al revés ("bucear" ≈ "buceo certificado" → inventaba también la certificación).
    sabido = sabido or {}
    quiere = salida.get("quiere_bucear") is True or sabido.get("quiere_bucear") is True
    certificado = salida.get("is_certified", sabido.get("is_certified"))
    if quiere and certificado is True and not salida.get("activity") and not sabido.get("activity"):
        salida["activity"] = "certified_diving"
    # Regla del catálogo: el buceo certificado (nombrado: fun dives, paquetes de buceos) exige certificación.
    if salida.get("activity") == "certified_diving" and "is_certified" not in salida and certificado is not True:
        salida["is_certified"] = True
    idioma = datos.get("idioma")
    if isinstance(idioma, str) and idioma.strip():
        salida["idioma"] = idioma.strip().lower()[:2]
    extraer_turno.ultimo_motivo = descartes
    if descartes:
        logger.info(f"[EXTRACT][EX4] descartado sin cita verificable: {descartes}")
    return salida


extraer_turno.ultimo_motivo = {}
extraer_turno.ultimo_segundos = 0.0
extraer_turno.ultimo_uso = {}


# EX-EXTRACTOR-1 (flag `extractor_aclaraciones`, 14-oct). Ronda g10-A/B: "Va quiero comprar sin ir de cartagena" se leía
# como cartagena (la regla "va a Cartagena" ganaba a la negación, 0/10). Primera versión (ronda flujo1-B): un bloque de
# aclaraciones al final del prompt arreglaba la negación pero movía otros campos ("quiero bucear certificado" sin
# actividad 4/10; "¿puedo bucear embarazada?" como querer bucear 6/10). La que se queda: la MISMA regla de la ubicación
# con la negación primero. Medido con 10 llamadas: "sin ir de Cartagena" 0 -> 10/10, "quiero bucear certificado"
# 10/10, embarazada sin querer bucear 8/10 (base 10/10), "estoy en Cartagena" y "no queremos ir a las islas" iguales.
UBICACION_HOY_ES = "- location: desde dónde sale. Si dice que está"
UBICACION_NEGACION_ES = (
    "- location: desde dónde sale. Primero, una NEGACIÓN invierte el lugar: \"sin ir de Cartagena\", \"sin salir de "
    "Cartagena\" o \"no vamos a Cartagena\" quiere decir que NO sale de Cartagena (si está en las islas → island; si no "
    "lo dice, null). Si no hay negación y dice que está"
)
UBICACION_HOY_EN = "- location: where they depart from. If they say they are"
UBICACION_NEGACION_EN = (
    "- location: where they depart from. First, a NEGATION inverts the place: \"without going from Cartagena\", "
    "\"without leaving Cartagena\" or \"we're not going to Cartagena\" means they do NOT depart from Cartagena (if they "
    "are on the islands → island; if they don't say, null). If there is no negation and they say they are"
)


# EX-EST-2 (flag `extractor_todo_lo_dicho`, 14-oct). Ronda est3-B, `semana-santa-solo-avanzado-islas`: "Un solo buzo
# avanzado" con la actividad ya sabida no daba el grupo (0/10 con "Lo que ya sabemos: activity"; 10/10 sin ello): la
# regla "no repitas lo que ya sabemos" hacía que el modelo saltara la frase entera, y el bot preguntaba "¿cuántas
# personas?" tres veces. La misma regla explica las citas sacadas del bloque "Lo que ya sabemos" (descartadas). El
# código ya compara cada dato con lo guardado (igual = nada cambia; distinto = se confirma), así que se extrae todo.
TODO_LO_DICHO_HOY_ES = "- No repitas lo que ya sabemos salvo que el cliente lo cambie en este mensaje."
TODO_LO_DICHO_ES = (
    "- No repitas lo que ya sabemos salvo que el cliente lo cambie en este mensaje. La cita es siempre del mensaje del "
    "cliente, nunca del texto del bot ni de \"Lo que ya sabemos\"."
)
TODO_LO_DICHO_HOY_EN = "- Do not repeat what we already know unless the customer changes it in this message."
TODO_LO_DICHO_EN = (
    "- Do not repeat what we already know unless the customer changes it in this message. The quote always comes from "
    "the customer's message, never from the bot's text or from \"What we already know\"."
)

# El mismo flag: la regla del grupo con la clase general "número + personas" (en est3-B, "Un solo buzo avanzado" con la
# actividad sabida: el modelo dudaba si "un solo buzo" es una persona; 1/10).
GRUPO_HOY_ES = '("voy solo", "solo yo" = 1; "somos 3" = 3; "mi pareja y yo", "con mi amigo", "con mi novia" = 2)'
GRUPO_NUMERO_ES = ('("voy solo", "solo yo", "un solo buzo" = 1; "somos 3", "3 buzos" = 3; "mi pareja y yo", "con mi amigo", '
                   '"con mi novia", "dos adultos" = 2)')
GRUPO_HOY_EN = '("just me" = 1; "we are 3" = 3; "my partner and I", "with my friend", "with my girlfriend" = 2)'
GRUPO_NUMERO_EN = ('("just me", "a single diver" = 1; "we are 3", "3 divers" = 3; "my partner and I", "with my friend", '
                   '"with my girlfriend", "two adults" = 2)')

# El mismo flag: el ejemplo "quiero bucear con mi amigo" de la regla de actividad (NO elige actividad) hacía que el
# modelo tampoco diera el grupo; con cualquier otro cambio del prompt, "con mi amigo" = 2 caía de 8/10 a 0/10.
ACTIVIDAD_EJEMPLOS_HOY_ES = '"quiero bucear con mi amigo", "es mi primera vez", "nunca he buceado")'
ACTIVIDAD_EJEMPLOS_ES = ('"quiero bucear con mi amigo", "es mi primera vez", "nunca he buceado"; esos mensajes sí pueden '
                         'dar otros datos: "con mi amigo" dice group_size 2)')
ACTIVIDAD_EJEMPLOS_HOY_EN = "\"I want to dive with my friend\", \"it's my first time\", \"I've never dived\")"
ACTIVIDAD_EJEMPLOS_EN = ("\"I want to dive with my friend\", \"it's my first time\", \"I've never dived\"; those messages can "
                         "still give other data: \"with my friend\" gives group_size 2)")

# El mismo flag: la cédula de extranjería es un documento de RESIDENTE en Colombia (paga en COP, política
# colombian_pricing). "Yo tengo extrangeria" a "¿eres colombiano o residente?" daba is_colombian false 8/8 y el bot
# cotizaba en USD (est3-B, certificado-fecha-precio-cop-descuento-transferencia). Dentro de la definición de residente.
RESIDENTE_HOY_ES = "- is_colombian: si dice que es colombiano, de una ciudad de Colombia o residente en Colombia ("
RESIDENTE_ES = ("- is_colombian: si dice que es colombiano, de una ciudad de Colombia o residente en Colombia (tener "
                "cédula de extranjería es ser residente; ")
RESIDENTE_HOY_EN = "- is_colombian: if they say they are Colombian, from a Colombian city or a resident of Colombia ("
RESIDENTE_EN = ("- is_colombian: if they say they are Colombian, from a Colombian city or a resident of Colombia (having a "
                "cédula de extranjería means being a resident; ")

# El mismo flag: aceptar la opción que propone el bot es elegirla (est3-B, pareja-certificados: "nos gusta, somos 2…"
# tras "te propongo la salida de 2 inmersiones" citaba el texto del bot y se descartaba; el bot repetía el menú).
ELIGE_HOY_ES = "o cuando contesta a la pregunta del bot quedándose con una de las opciones que le ofrece."
ELIGE_ES = ("o cuando contesta a la pregunta del bot quedándose con una de las opciones que le ofrece o aceptando la que "
            "le propone (\"nos gusta\", \"esa\", \"la primera\": el valor es esa opción y la cita, su respuesta).")
ELIGE_HOY_EN = "or when they answer the bot's question by taking one of the options it offers."
ELIGE_EN = ("or when they answer the bot's question by taking one of the options it offers or accepting the one it "
            "proposes (\"we like it\", \"that one\", \"the first one\": the value is that option and the quote, their answer).")

# CAL-C (17-oct, flag `sin_cedula_extranjero`, DECISIÓN DE ÁLVARO): "que no tenga cedula" (cal-32, para pagar) no
# guardaba is_colombian=False, así que la regla de moneda no saltaba y el bot nunca decía que paga en USD. La regla
# decía cuándo ES colombiano y no cuándo NO lo es. Decisión del owner: sin cédula colombiana (ni de extranjería), o
# extranjero/turista, = no colombiano → USD.
# Va al FINAL de la regla: en medio movía otros campos del banco ex0 (estables 98 → 95,5 %, inventos peor pasada 4 → 8).
SIN_CEDULA_HOY_ES = "mixed_nationality true e is_colombian null."
SIN_CEDULA_ES = ("mixed_nationality true e is_colombian null. Si dice que no tiene cédula colombiana (ni de extranjería) o "
                 "que es extranjero o turista: false.")
SIN_CEDULA_HOY_EN = "mixed_nationality true and is_colombian null."
SIN_CEDULA_EN = ("mixed_nationality true and is_colombian null. If they say they have no Colombian ID (cédula, nor a "
                 "cédula de extranjería) or that they are a foreigner or tourist: false.")
