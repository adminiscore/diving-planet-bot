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

import asyncio
import json
import logging
import re
import time

from openai import AsyncOpenAI

from src.config import settings
from src.domain import activities as dom
from src.llm_client import crear_con_respaldo, trace_openai
from src.observability import pieza_llm
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
# HISTORY 0.31.18): añadir "gringo" a la lista sería un parche (mañana "soy paisa", "soy argentino").
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


# CAL-F (18-oct, flag `refresher_por_extractor`): si quiere o no el REFRESHER, con su cita. Solo se leía como respuesta
# a la pregunta del refresher; "espera, en realidad sí lo quiero, mejor prevenir" antes de esa pregunta se perdía, y el
# bot volvía a preguntar "¿Os interesa?" y nunca cerraba el plan con la salida y el refresher (refresher-rechaza-acepta,
# 3/3 en PRE). Con el flag apagado, ni el campo ni su regla.
CAMPO_REFRESHER = _dato({"type": "boolean"},
                        "true si quien escribe dice que SÍ quiere hacer el refresher (repaso) antes de bucear; false si "
                        "dice que NO lo quiere.")
REGLA_REFRESHER_ES = (
    "\n- refresher_interested: true si quien escribe dice que SÍ quiere el refresher (el repaso antes de bucear), false "
    "si dice que NO lo quiere. Si cambia de idea en el mensaje, vale lo último que decide. Preguntar por el refresher o "
    "por su precio NO es decidir."
)
REGLA_REFRESHER_EN = (
    "\n- refresher_interested: true if the writer says they DO want the refresher (the review before diving), false if "
    "they say they do NOT want it. If they change their mind in the message, the last decision counts. Asking about the "
    "refresher or its price is NOT deciding."
)


# ex-9b paso 6 (19-oct): los últimos datos de "entender al cliente" que decidía solo el regex pasan al extractor, cada
# uno con su flag (APAGADO = ni el campo ni su regla: la llamada es exactamente la de antes). Ver
# docs/robustness/regex/estudio-ex9-regex.md, fila 6 de "Orden propuesto".
#
# 1. `duracion_por_extractor`: los días que quiere BUCEAR y los días que ESTARÁ, por separado (decisión de Gadea,
#    19-oct: si dice cuántos días quiere bucear, manda eso; si solo dice cuánto estará, se recomienda con la estancia).
#    El regex (`_detect_duration`) leía cualquier "N días/meses" y "estoy embarazada de 4 meses", "llevo 3 días esperando
#    respuesta" o "estoy pensando en ir en unos meses" daban "varios días".
CAMPO_DIAS_DE_BUCEO = _dato({"type": "integer"},
                            "Cuántos días quiere BUCEAR (o hacer la actividad) quien escribe o su grupo.")
CAMPO_DIAS_DE_ESTANCIA = _dato({"type": "integer"},
                               "Cuántos días estará quien escribe en Cartagena o en las islas (su viaje o estancia).")
REGLA_DURACION_ES = (
    "\n- dias_de_buceo y dias_de_estancia: cuántos días quiere bucear (o hacer la actividad) y cuántos días estará en la "
    "zona, cada uno en su campo y en número de días (\"un día\" = 1, \"un fin de semana\" = 2, \"una semana\" = 7, \"del "
    "5 al 9\" = 5, \"solo hoy\" = 1). \"Estaré una semana pero solo quiero bucear un día\" = dias_de_estancia 7 y "
    "dias_de_buceo 1. Un plan o paquete que elige y que dice sus días (\"el de 3 días de buceo\") son sus días de buceo. "
    "Solo cuenta la duración de su viaje o de su plan: el tiempo que ya ha pasado, lo que falta para el viaje, el tiempo "
    "desde su última inmersión o cualquier otra duración que no sea la de su viaje o su plan NO lo son. Preguntar cuánto "
    "dura algo tampoco."
)
REGLA_DURACION_EN = (
    "\n- dias_de_buceo and dias_de_estancia: how many days they want to dive (or do the activity) and how many days they "
    "will be in the area, each in its own field and as a number of days (\"one day\" = 1, \"a weekend\" = 2, \"a week\" "
    "= 7, \"from the 5th to the 9th\" = 5, \"just today\" = 1). \"I'll be here a week but only want to dive one day\" = "
    "dias_de_estancia 7 and dias_de_buceo 1. A plan or package they choose that states its days (\"the 3-day dive "
    "one\") gives their diving days. Only the length of their trip or plan counts: time that has already passed, time "
    "until the trip, time since their last dive or any other duration that is not their trip or plan do NOT. Asking how "
    "long something lasts doesn't either."
)
# 2. `edades_por_extractor`: las edades con su cita. El regex (`_detect_ages`) solo valida la cifra (`edades_citadas`):
#    hoy las leía el regex y las completaba `fill_gaps` (que lee el historial y puede suponerlas).
CAMPO_EDADES = _dato({"type": "array", "items": {"type": "integer"}},
                     "Las edades, en años, de las personas que van (quien escribe o su grupo) que dice el mensaje.")
REGLA_EDADES_ES = (
    "\n- edades: las edades en años de las personas que van, quien escribe o su grupo (\"voy con mis hijos de 7 y 12\" "
    "= [7, 12]; \"tengo 35\" = [35]), también dentro de una pregunta sobre ellas (\"¿mi hija de 9 puede?\" = [9]). Una "
    "edad hipotética o de una regla (\"¿desde qué edad se puede bucear?\", \"¿un niño de 5 podría?\") no es de nadie del "
    "grupo; un tiempo (\"hace 6 años\", \"llevo 4 años sin bucear\") no es una edad."
)
REGLA_EDADES_EN = (
    "\n- edades: the ages in years of the people going, the writer or their group (\"I'm coming with my kids aged 7 "
    "and 12\" = [7, 12]; \"I'm 35\" = [35]), also inside a question about them (\"can my 9-year-old daughter do it?\" "
    "= [9]). A hypothetical age or a rule (\"from what age can you dive?\", \"could a 5-year-old?\") is nobody in the "
    "group; a time span (\"6 years ago\", \"I haven't dived in 4 years\") is not an age."
)
# 3. `plan_elegido_por_extractor`: si el mensaje ACEPTA lo que el bot acaba de proponer (decisión de Gadea, 19-oct:
#    "perfecto, ese me sirve" lo da por elegido y sigue la reserva; preguntar el precio NO es elegir). Lo leía
#    `_CONFIRMS_DESCRIBED_PACKAGE_RE` ("quiero este paquete"). El campo solo va cuando el bot acaba de proponer UN plan
#    (`plan_que_propone_el_bot`): es la única propuesta cuyo "sí" cambia algo que el extractor no lee ya.
CAMPO_ACEPTA = _dato({"type": "boolean"},
                     "true si el mensaje ACEPTA lo que el bot le acaba de proponer; false si lo rechaza.")
REGLA_ACEPTA_ES = (
    "\n- acepta_propuesta: true si el mensaje acepta o elige lo que el bot le acaba de proponer en su último mensaje "
    "(\"perfecto, ese me sirve\", \"vamos con ese\", \"quiero ese paquete\"); false si lo rechaza (\"no, mejor otra "
    "cosa\"). Preguntar por la propuesta (su precio, qué incluye, cuándo es) o compararla con otra opción NO es "
    "aceptarla: null. La cita son las palabras del cliente."
)
REGLA_ACEPTA_EN = (
    "\n- acepta_propuesta: true if the message accepts or chooses what the bot has just proposed in its last message "
    "(\"perfect, that one works for me\", \"let's go with that\", \"I want that package\"); false if it rejects it "
    "(\"no, something else\"). Asking about the proposal (its price, what's included, when it is) or comparing it with "
    "another option is NOT accepting it: null. The quote is the customer's words."
)
# 4. `reparto_al_sumarse_alguien`: alguien que se SUMA a un grupo ya sabido. Con "No repitas lo que ya sabemos" y
#    "group_size solo si dice cuántas personas", el modelo dudaba si la persona era nueva o de las que ya iban: "mi
#    hermano también viene, él quiere hacer snorkel" sobre 2 buzos salía sin total ni reparto, o {buceo: 1, snorkel: 1}
#    (banco del paso 6). Solo va cuando ya sabemos el grupo (`sabido` con total o reparto).
REGLA_SUMARSE_ES = (
    "\n- Si ya sabemos el grupo y el mensaje dice que se SUMA alguien que no estaba contado (también viene, se apunta, "
    "se une, al final viene uno más…), esa persona es nueva: group_size = los que ya iban más los que se suman, aunque "
    "no lo diga con una cifra, y group_allocation = el reparto que ya sabemos más los nuevos con su actividad (undecided "
    "si no la dice; si hacen lo mismo que el grupo, súmalos a esa actividad). Si habla de alguien que ya venía o ya "
    "estaba contado, o solo dice lo que hará alguien sin decir que se suma, no es nueva: el total no cambia."
)
REGLA_SUMARSE_EN = (
    "\n- If we already know the group and the message says someone who was not counted JOINS (also coming, signing up, "
    "joining us, one more is coming in the end…), that person is new: group_size = those already going plus the new "
    "ones, even without a number, and group_allocation = the split we already know plus the new ones with their "
    "activity (undecided if not said; if they do the same as the group, add them to that activity). If it talks about "
    "someone who was already coming or already counted, or only says what someone will do without saying they join, "
    "they are not new: the total does not change."
)

# 5. `notas_rag_desde_estado`: dos hechos de OTRA persona del grupo que el RAG necesita para no equivocarse (el minicurso
#    no certifica; un certificado inactivo sigue siendo certificado y necesita el refresher). Los buscaba un regex por
#    todo el texto del cliente y las notas (`rutas/contexto_rag`); el extractor solo tenía los datos de quien escribe.
CAMPO_OTRO_SIN_CERTIFICAR = _dato({"type": "boolean"},
                                  "true si dice que OTRA persona del grupo (no quien escribe) NO es buzo certificado.")
CAMPO_OTRO_CERTIFICADO_INACTIVO = _dato({"type": "boolean"},
                                        "true si dice que OTRA persona del grupo (no quien escribe) SÍ es buzo "
                                        "certificado pero lleva tiempo sin bucear.")
REGLA_OTRAS_PERSONAS_ES = (
    "\n- otro_sin_certificar y otro_certificado_inactivo: solo de OTRA persona del grupo, nunca de quien escribe. "
    "otro_sin_certificar true si dice que alguien de su grupo no está certificado o nunca ha buceado (\"mi pareja nunca "
    "ha buceado\"). otro_certificado_inactivo true si dice que alguien de su grupo sí tiene certificación pero hace "
    "tiempo que no bucea (\"mi hermano es Open Water pero no bucea desde hace años\"). Lo que dice de sí mismo va en "
    "is_certified y last_dive_over_2_years."
)
REGLA_OTRAS_PERSONAS_EN = (
    "\n- otro_sin_certificar and otro_certificado_inactivo: only about ANOTHER person in the group, never the writer. "
    "otro_sin_certificar true if they say someone in their group is not certified or has never dived (\"my partner has "
    "never dived\"). otro_certificado_inactivo true if they say someone in their group is certified but hasn't dived in "
    "a long time (\"my brother is Open Water but hasn't dived in years\"). What they say about themselves goes in "
    "is_certified and last_dive_over_2_years."
)

# 6. gen-8 (`actividad_de_la_pregunta`): la actividad de la que el cliente PREGUNTA sin elegirla. La regla de activity
#    (decisión de Gadea: no se adivina) deja sin actividad a quien pregunta "en el minicurso, ¿el equipo está
#    incluido?" o "si hiciera el Open Water…", y el bot le pegaba detrás de la respuesta el menú de 4 actividades. No
#    cambia activity: es otro hecho, con su cita, para que el bot ofrezca esa actividad y la elija el cliente.
CAMPO_ACTIVIDAD_PREGUNTADA = _dato({"type": "string", "enum": list(ACTIVIDADES)},
                                   "La actividad concreta de la que pregunta o habla el mensaje, aunque no la elija.")
REGLA_ACTIVIDAD_PREGUNTADA_ES = (
    "\n- actividad_preguntada: la actividad concreta de la lista de la que pregunta o habla este mensaje aunque no la "
    "elija: una duda sobre ella (\"en el minicurso, ¿el equipo está incluido?\"), una hipótesis (\"si hiciera el "
    "Advanced…\") o su precio. null si no nombra ninguna concreta, si pregunta qué opciones hay o si compara varias. "
    "Si además la elige, va también en activity."
)
REGLA_ACTIVIDAD_PREGUNTADA_EN = (
    "\n- actividad_preguntada: the concrete activity from the list that this message asks or talks about even if it "
    "does not choose it: a doubt about it (\"is gear included in the mini course?\"), a hypothesis (\"if I did the "
    "Advanced…\") or its price. null if it names no concrete one, asks what options there are or compares several. If "
    "it also chooses it, it goes in activity too."
)


# arq-1j (22-oct, flag `varias_actividades`): TODAS las actividades por las que pregunta el mensaje. Con una sola
# (`actividad_preguntada`), «¿cuánto pagamos un buzo y un acompañante?» o «¿qué incluyen el snorkel y el minicurso?»
# quedaban sin actividad (la regla pide null si compara varias) y contestaba el RAG sin los hechos del código: ~8-10
# fallos del G10 nº 2. El acompañante entra porque tiene precio y lo que incluye, aunque no sea una actividad elegible.
CAMPO_ACTIVIDADES_PREGUNTADAS = _dato({"type": "array", "items": {"type": "string",
                                                                  "enum": [*ACTIVIDADES, "companion"]}},
                                      "Todas las actividades concretas por las que pregunta el mensaje.")
REGLA_ACTIVIDADES_PREGUNTADAS_ES = (
    "\n- actividades_preguntadas: TODAS las actividades concretas de la lista por las que pregunta este mensaje (su "
    "precio, qué incluyen, sus requisitos…), aunque no elija ninguna; companion es el acompañante que va en la lancha "
    "sin bucear. «¿Cuánto cuestan el snorkel y el minicurso?» → [snorkel, minicourse]. null si no nombra ninguna "
    "concreta."
)
REGLA_ACTIVIDADES_PREGUNTADAS_EN = (
    "\n- actividades_preguntadas: ALL the concrete activities from the list that this message asks about (their price, "
    "what they include, their requirements…), even if it chooses none; companion is the companion who rides the boat "
    "without diving. \"How much are snorkeling and the mini course?\" → [snorkel, minicourse]. null if it names no "
    "concrete one."
)


# arq-1t (22-oct, flag `paquete_varios_dias`): «¿cuánto vale el paquete de varios días?» no dejaba nada en el estado
# (dias_de_buceo solo con cifra) y el «¿qué incluye?» siguiente recibía lo de la salida de un día (G10 nº 4, g10-041).
CAMPO_PAQUETE_VARIOS_DIAS = _dato({"type": "boolean"},
                                  "Pide un paquete o plan de VARIOS días de buceo sin decir cuántos días ni inmersiones.")
REGLA_PAQUETE_VARIOS_DIAS_ES = (
    "\n- paquete_varios_dias: true si pide o pregunta por un paquete o plan de VARIOS días de buceo sin decir cuántos "
    "días ni cuántas inmersiones («el paquete de varios días», «un plan de varios días buceando»). null si dice el número "
    "de días o de inmersiones, o si habla de un solo día."
)
REGLA_PAQUETE_VARIOS_DIAS_EN = (
    "\n- paquete_varios_dias: true if they ask for or about a package or plan of SEVERAL days of diving without saying "
    "how many days or dives (\"the multi-day package\", \"a plan diving over several days\"). null if they give the "
    "number of days or dives, or talk about a single day."
)


def campos_paso6(history: list[dict] | None) -> dict:
    """Los campos nuevos del paso 6 que van en ESTA llamada, según sus flags: {campo: (esquema, regla_es, regla_en)}.
    Vacío con los flags apagados (la llamada de siempre). `acepta_propuesta` solo si el bot acaba de proponer un plan."""
    campos: dict = {}
    if settings.duracion_por_extractor:
        campos["dias_de_buceo"] = (CAMPO_DIAS_DE_BUCEO, REGLA_DURACION_ES, REGLA_DURACION_EN)
        campos["dias_de_estancia"] = (CAMPO_DIAS_DE_ESTANCIA, "", "")
    if settings.edades_por_extractor:
        campos["edades"] = (CAMPO_EDADES, REGLA_EDADES_ES, REGLA_EDADES_EN)
    if settings.plan_elegido_por_extractor and plan_que_propone_el_bot(history) is not None:
        campos["acepta_propuesta"] = (CAMPO_ACEPTA, REGLA_ACEPTA_ES, REGLA_ACEPTA_EN)
    if settings.notas_rag_desde_estado:
        campos["otro_sin_certificar"] = (CAMPO_OTRO_SIN_CERTIFICAR, REGLA_OTRAS_PERSONAS_ES, REGLA_OTRAS_PERSONAS_EN)
        campos["otro_certificado_inactivo"] = (CAMPO_OTRO_CERTIFICADO_INACTIVO, "", "")
    if settings.actividad_de_la_pregunta:
        campos["actividad_preguntada"] = (CAMPO_ACTIVIDAD_PREGUNTADA, REGLA_ACTIVIDAD_PREGUNTADA_ES,
                                          REGLA_ACTIVIDAD_PREGUNTADA_EN)
    if settings.varias_actividades:
        campos["actividades_preguntadas"] = (CAMPO_ACTIVIDADES_PREGUNTADAS, REGLA_ACTIVIDADES_PREGUNTADAS_ES,
                                             REGLA_ACTIVIDADES_PREGUNTADAS_EN)
    if settings.paquete_varios_dias:
        campos["paquete_varios_dias"] = (CAMPO_PAQUETE_VARIOS_DIAS, REGLA_PAQUETE_VARIOS_DIAS_ES,
                                         REGLA_PAQUETE_VARIOS_DIAS_EN)
    return campos


def plan_que_propone_el_bot(history: list[dict] | None) -> int | None:
    """El paquete de varios días (nº de inmersiones del catálogo) que describe el ÚLTIMO mensaje del bot, si describe
    uno solo; None si no describe ninguno o compara varios ("este paquete" no diría cuál). Lee el texto del BOT (formato
    nuestro, no el del cliente), con la misma lectura de cifras que el detector y el RAG (`dive_counts_in`). La usan el
    extractor (si pregunta `acepta_propuesta`) y `nucleo/routing` (el paquete confirmado)."""
    from src.agents.intent_detector import dive_counts_in  # lazy

    ultimo = next((h.get("content", "") for h in reversed(history or []) if h.get("role") == "assistant"), "")
    multi_dia = [n for n in dive_counts_in(ultimo) if dom.dive_packages()[n][0] > 1]
    return multi_dia[0] if len(multi_dia) == 1 else None


def edades_citadas(edades, cita: str) -> list[int]:
    """Las edades del extractor cuya cifra está en su cita (en dígitos o en palabra, "nueve"): el regex solo valida la
    cifra, no decide. Entre 1 y 99, sin repetir, en orden."""
    from src.utils.number_words import number_words  # lazy

    palabras = number_words(1, 19)
    tokens = _norm(cita)
    validas = []
    for edad in edades if isinstance(edades, list) else []:
        if not isinstance(edad, int) or isinstance(edad, bool) or not 1 <= edad <= 99:
            continue
        if str(edad) in tokens or any(palabras.get(t) == edad for t in tokens):
            validas.append(edad)
    return list(dict.fromkeys(validas))


# ex-9b (19-oct, flag `reparto_en_pares`): con los campos del paso 6 la llamada a Haiku fallaba SIEMPRE (Anthropic: "The
# compiled grammar is too large"; ronda ex9b-4, 92 de 92): el reparto, un objeto con un entero opcional por actividad
# (10), era la parte que más gramática pedía. Como lista de pares {actividad, personas} caben todos los campos; nada más
# leer se convierte al diccionario de siempre (`_reparto_de_pares`), así que el resto del código no cambia.
_REPARTO_EN_PARES = _dato(
    {"type": "array", "items": {"type": "object",
                                "properties": {"actividad": {"type": "string", "enum": list(CLAVES_REPARTO)},
                                               "personas": {"type": "integer"}},
                                "required": ["actividad", "personas"], "additionalProperties": False}},
    "Cuántas personas hacen cada actividad (una entrada por actividad), solo si el grupo se reparte entre VARIAS.")


# Cuánto más que a la llamada principal se espera a la del paso 6 (ver `extraer_turno`).
PASO6_ESPERA_MAX = 1.5


def _reparto_de_pares(valor):
    """La lista de pares del reparto -> {actividad: personas} (sumando si una actividad sale dos veces)."""
    if not isinstance(valor, list):
        return valor
    reparto: dict = {}
    for par in valor:
        act, n = (par or {}).get("actividad"), (par or {}).get("personas")
        if act in CLAVES_REPARTO and isinstance(n, int) and not isinstance(n, bool) and n > 0:
            reparto[act] = reparto.get(act, 0) + n
    return reparto


def _esquema(con_hotel: bool, con_refresher: bool = False, precio_no_elige: bool = False,
             paso6: dict | None = None) -> dict:
    """El esquema de la llamada con los campos opcionales encendidos (sin ellos, el de siempre)."""
    base = ESQUEMA_CON_NOMBRE
    if precio_no_elige:  # mod-2: ver `_PRECIO_NO_ELIGE`
        import copy

        base = copy.deepcopy(base)
        qb = base["properties"]["quiere_bucear"]
        qb["description"] = qb["description"].replace(_QUIERE_BUCEAR_PRECIO, _QUIERE_BUCEAR_SIN_PRECIO)
    if settings.reparto_en_pares:
        base = {**base, "properties": {**base["properties"], "group_allocation": _REPARTO_EN_PARES}}
    if not (con_hotel or con_refresher or paso6):
        return base
    extra = {**({"hotel": CAMPO_HOTEL} if con_hotel else {}),
             **({"refresher_interested": CAMPO_REFRESHER} if con_refresher else {}),
             **{campo: esquema for campo, (esquema, _es, _en) in (paso6 or {}).items()}}
    return {**base, "properties": {**base["properties"], **extra}, "required": [*base["required"], *extra]}
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
# mod-2 (18-oct, decisión de Gadea: "no se adivina nada que el cliente no haya dicho"; flag `precio_no_elige`):
# preguntar el precio de un producto es una DUDA: no elige la actividad, no dice que quiera bucear ni que sea buzo
# certificado. Revoca la del 14/27-sep (`extractor_precio_elige`). Apagar ese flag no bastaba: volvía el texto de antes,
# que chocaba con la regla de `activity` ("…o del que quiere saber el precio") y el modelo dejaba de elegir también lo
# que sí elige ("quiero bucear certificado", "trying to checkout to take PADI Open Water"; banco ex0 109 → 101). Las
# cuatro frases que hablan del precio cambian a la vez, para que digan lo mismo.
GENERAL_PRECIO_ES_V3 = ('Una pregunta ("¿puedo bucear embarazada?") no dice que esté embarazada ni que vaya a bucear; '
                        'preguntar el precio de un producto ("¿cuánto cuesta el buceo certificado?", "¿cuánto vale el '
                        'paquete de 5 inmersiones?") es una duda: no elige esa actividad ni dice que el cliente sea buzo '
                        'certificado. Una hipótesis ("si decidiera hacer el curso…") o algo que nombra sin elegirlo no es '
                        'un dato.')
GENERAL_PRECIO_EN_V3 = ('A question ("can I dive pregnant?") does not say they are pregnant or will dive; asking the '
                        'price of a product ("how much is certified diving?", "how much is the 5-dive package?") is a '
                        'doubt: it does not choose that activity nor say the customer is a certified diver. A hypothesis '
                        '("in case I decided to do the course…") or something they mention without choosing it is not a '
                        'fact.')
_PRECIO_NO_ELIGE = (
    ("como lo que quiere hacer, reservar, ya tiene reservado o del que quiere saber el precio,",
     "como lo que quiere hacer, reservar o ya tiene reservado (preguntar solo su precio no lo elige),"),
    ("as what they want to do, book, have already booked or want the price of,",
     "as what they want to do, book or have already booked (only asking its price does not choose it),"),
    ("(lo dice, pide buceos, sus precios o una fecha para bucear)",
     "(lo dice, pide buceos o una fecha para bucear; preguntar solo un precio no)"),
    ("(they say so, ask for dives, their prices or a date to dive)",
     "(they say so, ask for dives or a date to dive; only asking a price does not)"),
)
# 19-oct (ronda mod-G, flag `certificado_solo_si_lo_dice`): sin la regla del código "buceo certificado ⇒ certificado",
# el extractor no veía la certificación en lo que también la dice: «completé el curso básico» (paquete-5-buceos) o
# «I'm gonna need a little refresher» (el repaso es para quien YA está certificado). Con el flag, la regla de
# is_certified nombra esas formas de decirlo. Sigue sin deducirse de pedir buceos o fun dives (decisión de Gadea).
IS_CERTIFIED_HOY_ES = "- is_certified: true solo si dice que tiene certificación o un nivel de buceo (buzo certificado, Open Water, Advanced…), él o su grupo;"
IS_CERTIFIED_DICHO_ES = ("- is_certified: true solo si dice que tiene certificación o un nivel de buceo (buzo certificado, "
                         "Open Water, Advanced…), que ya terminó un curso de certificación («completé el curso básico», "
                         "«me certifiqué en…»), que tiene inmersiones registradas, que ha buceado hace poco («buceé hace "
                         "poco»: true aunque empiece por «no», que contestaba a otra cosa; decisión de Gadea 19-oct) o que "
                         "necesita un refresher (el repaso es para quien ya está certificado), él o su grupo;")
IS_CERTIFIED_HOY_EN = "- is_certified: true only if they say they have a certification or a diving level (certified diver, Open Water, Advanced…), themselves or their group;"
IS_CERTIFIED_DICHO_EN = ("- is_certified: true only if they say they have a certification or a diving level (certified diver, "
                         "Open Water, Advanced…), that they already finished a certification course (\"I completed the basic "
                         "course\", \"I got certified in…\"), that they have logged dives, that they dived recently (\"I "
                         "dived recently\": true even if it starts with \"no\", which was answering something else) or that "
                         "they need a refresher (a refresher is for someone already certified), themselves or their group;")
_QUIERE_BUCEAR_PRECIO = "pregunta sus precios o fechas,"
_QUIERE_BUCEAR_SIN_PRECIO = "pregunta sus fechas (preguntar solo un precio no),"


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


# G3-06: los lugares que NO son las islas aunque lo parezcan (decisión de Gadea, 18-oct; aviso solo-operamos-en-rosario).
_FUERA_DE_ROSARIO = ("baru", "playa blanca")


def _solo_baru(cita: str) -> bool:
    """¿La cita nombra Barú o Playa Blanca y ninguna isla del Rosario (las de `_pistas_islas`, o "rosario")?"""
    texto = strip_accents((cita or "").lower())
    if not any(lugar in texto for lugar in _FUERA_DE_ROSARIO):
        return False
    islas = [strip_accents(n.lower()) for n in _pistas_islas().split(", ")]
    return "rosario" not in texto and not any(isla and isla in texto for isla in islas)


# gen-15 (21-oct, flag `hoteles_de_la_base`): los hoteles de las islas que da la base del negocio
# (data/knowledge_base/policies.json, other_island_hotels: la base en Majagua y Cocoliso, y otros con acceso marítimo).
# La lista de hoteles del bot (rag_agent.AMBIGUOUS_LOCATION_NAMES) no tenía Mulata, Rosario de Mar ni Eco Hotel Las
# Palmeras, y «we booked 2 nights at Mulata» o «vamos a estar en Las Palmeras» no salían como «ya en las islas» (banco
# docs/robustness/gen/banco_gen15_hoteles.py). tests/test_gen15_hoteles_de_la_base.py vigila que sigan en la base.
HOTELES_DE_LA_BASE = ("San Pedro de Majagua", "Cocoliso", "Ubuntu", "Secreto", "Mulata", "Rosario de Mar",
                      "Eco Hotel Las Palmeras")


def _nombres_de_lugar() -> list[str]:
    from src.agents.rag_agent import (
        AMBIGUOUS_LOCATION_NAMES,  # lazy: lista cerrada de hoteles e islas del Rosario
    )

    nombres = list(AMBIGUOUS_LOCATION_NAMES)
    if settings.hoteles_de_la_base:
        nombres += [h for h in HOTELES_DE_LA_BASE if not any(h.lower() in n.lower() for n in nombres)]
    return nombres


def _pistas_islas() -> str:
    return ", ".join(_nombres_de_lugar())


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
    palabras = {"cartagena", "isla", "islas", "island", "islands", "rosario", "hotel", "hostel", "hostal"}
    if settings.baru_sale_de_cartagena:
        palabras.update({"baru", "blanca"})  # gen-6: "estamos en Barú" dice desde dónde sale (Cartagena)
    for nombre in _nombres_de_lugar():
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


def actividad_principal_del_reparto(reparto: dict | None) -> str | None:
    """La actividad principal que dice un reparto del grupo (regla de negocio de CAL-F, 18-oct): el buceo certificado si
    alguien lo hace y, si no, la parte más grande del grupo. Las personas sin decidir no cuentan. None si nadie del
    reparto tiene actividad. La usan la contradicción actividad/reparto del extractor (aquí abajo) y la actividad
    principal de un grupo repartido sin actividad elegida (ex-9b paso 3, `nucleo/extractor._poner_actividad`)."""
    decididas = {k: v for k, v in (reparto or {}).items() if k != "undecided" and v}
    if not decididas:
        return None
    return "certified_diving" if "certified_diving" in decididas else max(decididas, key=decididas.get)


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
    if settings.precio_no_elige:
        # mod-2 (decisión de Gadea, 18-oct): preguntar el precio no elige ni certifica; manda sobre `extractor_precio_elige`.
        sistema = sistema.replace(GENERAL_PRECIO_ES, GENERAL_PRECIO_ES_V3).replace(GENERAL_PRECIO_EN, GENERAL_PRECIO_EN_V3)
        for antes, despues in _PRECIO_NO_ELIGE:
            sistema = sistema.replace(antes, despues)
    else:
        sistema = sistema.replace(GENERAL_PRECIO_ES, GENERAL_PRECIO_ES_V2).replace(GENERAL_PRECIO_EN, GENERAL_PRECIO_EN_V2)
    if settings.certificado_solo_si_lo_dice:
        # 19-oct: sin la regla del código, que is_certified vea todas las formas de decirlo (ver IS_CERTIFIED_DICHO_*).
        sistema = sistema.replace(IS_CERTIFIED_HOY_ES, IS_CERTIFIED_DICHO_ES).replace(IS_CERTIFIED_HOY_EN, IS_CERTIFIED_DICHO_EN)
    # EX-EXTRACTOR-1: la regla de la ubicación con la negación primero (ver UBICACION_NEGACION_*).
    sistema = sistema.replace(UBICACION_HOY_ES, UBICACION_NEGACION_ES).replace(UBICACION_HOY_EN, UBICACION_NEGACION_EN)
    # EX-EST-2: extraer también lo ya sabido (ver TODO_LO_DICHO_*).
    sistema = sistema.replace(TODO_LO_DICHO_HOY_ES, TODO_LO_DICHO_ES).replace(TODO_LO_DICHO_HOY_EN, TODO_LO_DICHO_EN)
    sistema = sistema.replace(GRUPO_HOY_ES, GRUPO_NUMERO_ES).replace(GRUPO_HOY_EN, GRUPO_NUMERO_EN)
    sistema = sistema.replace(ACTIVIDAD_EJEMPLOS_HOY_ES, ACTIVIDAD_EJEMPLOS_ES).replace(
        ACTIVIDAD_EJEMPLOS_HOY_EN, ACTIVIDAD_EJEMPLOS_EN)
    sistema = sistema.replace(RESIDENTE_HOY_ES, RESIDENTE_ES).replace(RESIDENTE_HOY_EN, RESIDENTE_EN)
    sistema = sistema.replace(ELIGE_HOY_ES, ELIGE_ES).replace(ELIGE_HOY_EN, ELIGE_EN)
    sistema += REGLA_NOMBRE_ES if lang == "es" else REGLA_NOMBRE_EN
    con_hotel = settings.hotel_por_extractor
    if settings.sin_cedula_extranjero:
        # CAL-C (17-oct, decisión de Álvaro): sin cédula colombiana → no es colombiano (paga en USD). Ver SIN_CEDULA_*.
        sistema = sistema.replace(SIN_CEDULA_HOY_ES, SIN_CEDULA_ES).replace(SIN_CEDULA_HOY_EN, SIN_CEDULA_EN)
        if settings.cedula_de_extranjeria_manda:
            # arq-1r: el extranjero CON cédula de extranjería es residente (ver `_CEDULA_DE_EXTRANJERIA_MANDA`).
            for antes, despues in _CEDULA_DE_EXTRANJERIA_MANDA:
                sistema = sistema.replace(antes, despues)
    if settings.vivir_no_es_residir:
        # gen-4: vivir en Colombia no es ser residente (ver `_VIVIR_NO_ES_RESIDIR`).
        for antes, despues in _VIVIR_NO_ES_RESIDIR:
            sistema = sistema.replace(antes, despues)
        if settings.gentilicio_es_colombiano:
            # gen-14: la ciudad o el gentilicio sí dicen la nacionalidad; alojarse o viajar no (ver la constante).
            for antes, despues in _GENTILICIO_ES_COLOMBIANO:
                sistema = sistema.replace(antes, despues)
            if settings.el_verbo_no_la_ciudad:
                # arq-1f: pares con la misma ciudad, para que decida el verbo (ver `_EL_VERBO_NO_LA_CIUDAD`).
                for antes, despues in _EL_VERBO_NO_LA_CIUDAD:
                    sistema = sistema.replace(antes, despues)
    if settings.baru_sale_de_cartagena:
        # gen-6: alojarse en Barú o Playa Blanca es salir desde Cartagena (ver `_BARU_SALE_DE_CARTAGENA`).
        for antes, despues in _BARU_SALE_DE_CARTAGENA:
            sistema = sistema.replace(antes, despues)
    if con_hotel:
        sistema += REGLA_HOTEL_ES if lang == "es" else REGLA_HOTEL_EN
    # Solo cuando el refresher importa (ya se sabe que lleva más de 2 años sin bucear): con el campo en todas las
    # llamadas, el banco ex0 bajaba de 99,5 a 96,5 % estable y volvía "paquete de 5 inmersiones" → certificado.
    con_refresher = settings.refresher_por_extractor and (sabido or {}).get("last_dive_over_2_years") is True
    if con_refresher:
        sistema += REGLA_REFRESHER_ES if lang == "es" else REGLA_REFRESHER_EN
    # ex-9b paso 6: los campos nuevos con su regla (ninguno con los flags apagados).
    paso6 = campos_paso6(history)
    # ex-9b (19-oct, decisión de Gadea, flag `paso6_en_llamada_aparte`): con dos o más campos del paso 6 el esquema
    # estricto no cabía en Haiku ("compiled grammar is too large": ronda ex9b-4, 92 de 92 llamadas al respaldo).
    # Con el flag, la llamada de siempre sale con su esquema de siempre y los campos del paso 6 van en OTRA llamada,
    # a la vez (mismo texto + sus reglas: el principio del prompt sale de la caché). Se juntan al leer.
    aparte = bool(paso6) and settings.paso6_en_llamada_aparte
    sistema_paso6 = sistema
    for _esq, regla_es, regla_en in paso6.values():
        sistema_paso6 += regla_es if lang == "es" else regla_en
    if not aparte:
        sistema = sistema_paso6
    if settings.reparto_al_sumarse_alguien and ((sabido or {}).get("group_size") or (sabido or {}).get("group_allocation")):
        sistema += REGLA_SUMARSE_ES if lang == "es" else REGLA_SUMARSE_EN
    modelo = modelo or settings.extractor_turno_model
    t0 = time.perf_counter()
    usuario = _contexto(mensaje, ultima_pregunta_del_bot(history), sabido or {}, lang)

    async def _pedir(sist: str, esquema: dict, pieza: str):
        # 18-oct (mod-2): con `extractor_respaldo_modelo`, si el extractor no contesta en `extractor_respaldo_segundos`
        # la misma petición va al respaldo y gana la primera (ronda mod-F: la cola de Haiku por OpenRouter, 4-5 s en
        # 2 de 47 turnos). Vacío = la llamada de siempre. r6-1: sale etiquetada en [TURN_METRICS] como `pieza`.
        with pieza_llm(pieza):
            return await crear_con_respaldo(
                client, respaldo=settings.extractor_respaldo_modelo, segundos=settings.extractor_respaldo_segundos,
                pieza=pieza,
                model=modelo,
                messages=[{"role": "system", "content": sist}, {"role": "user", "content": usuario}],
                response_format={"type": "json_schema",
                                 "json_schema": {"name": "datos_del_turno", "strict": True, "schema": esquema}},
                temperature=0.0,
                # EX-EST-1 (14-oct): con los campos nuevos (idioma, nombre, quiere_bucear...) 400 cortaba el JSON (2 de
                # cada 1.000 llamadas en el banco: "Unterminated string" -> el turno caía al camino viejo).
                max_tokens=700,
            )

    datos_paso6: dict = {}
    try:
        client = client or trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
        esquema = _esquema(con_hotel, con_refresher, settings.precio_no_elige, None if aparte else paso6)
        if aparte:
            esquema_paso6 = {"type": "object", "properties": {c: e for c, (e, _es, _en) in paso6.items()},
                             "required": list(paso6), "additionalProperties": False}
            t6 = asyncio.ensure_future(_pedir(sistema_paso6, esquema_paso6, "extractor_paso6"))
            try:
                resp = await _pedir(sistema, esquema, "extractor")
            except BaseException:
                t6.cancel()
                raise
            # Ronda ex9b-6: el respaldo de esta llamada tardó 6-8 s en 3 turnos y el turno lo esperaba. Como mucho se la
            # espera `PASO6_ESPERA_MAX` s más que a la principal; si no llega, el turno sigue sin sus campos (el bot los
            # pregunta si hacen falta, como cuando el extractor falla).
            try:
                resp6 = await asyncio.wait_for(t6, timeout=PASO6_ESPERA_MAX)
                datos_paso6 = json.loads(resp6.choices[0].message.content or "{}")
            except Exception as exc6:  # noqa: BLE001 — sin los campos del paso 6 en este turno
                logger.warning(f"[LLM_EXTRACTOR] la llamada del paso 6 no llegó o falló ({exc6!r}): sin sus campos")
        else:
            resp = await _pedir(sistema, esquema, "extractor")
        datos = {**json.loads(resp.choices[0].message.content or "{}"), **datos_paso6}
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
    for campo in (*CAMPOS, *EXTRAS, "nombre", *(("hotel",) if con_hotel else ()),
                  *(("refresher_interested",) if con_refresher else ()), *paso6):
        d = datos.get(campo)
        if not isinstance(d, dict) or d.get("valor") in (None, "", [], {}):
            continue
        valor, cita = d["valor"], d.get("cita") or ""
        if campo == "group_allocation":
            valor = {k: v for k, v in (_reparto_de_pares(valor) or {}).items() if v}
            if len(valor) < 2:  # un reparto de una sola actividad no es un reparto
                continue
        if campo in ("dias_de_buceo", "dias_de_estancia") and not (
                isinstance(valor, int) and not isinstance(valor, bool) and 1 <= valor <= 366):
            descartes[campo] = f"no es un número de días: {valor!r}"
            continue
        if campo == "edades":
            # ex-9b paso 6: la cifra de cada edad tiene que estar en la cita (el regex valida, no decide).
            valor = edades_citadas(valor, cita)
            if not valor:
                descartes[campo] = f"ninguna edad está en la cita: {d['valor']!r} / {cita!r}"
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
        if campo == "location" and valor == "island" and settings.baru_no_es_rosario and _solo_baru(cita):
            # G3-06 (decisión de Gadea): Barú y Playa Blanca no son las islas ("estamos en el hotel las islas, en
            # baru" salía island). El lugar queda sin saber y lo contesta la base (aviso solo-operamos-en-rosario).
            if settings.baru_sale_de_cartagena:
                # gen-6: quien se aloja en Barú sale desde Cartagena (policies.json); sin saberlo, se repreguntaba.
                salida[campo] = "cartagena"
                continue
            descartes[campo] = f"Barú no es Islas del Rosario: {cita!r}"
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
    # CAL-F (`refresher_por_extractor`): el refresher es el repaso ANTES de bucear (parte del buceo certificado tras más
    # de 2 años): quien dice que lo quiere, quiere bucear ("en realidad sí lo quiero, mejor prevenir").
    quiere = quiere or salida.get("refresher_interested") is True
    certificado = salida.get("is_certified", sabido.get("is_certified"))
    if quiere and certificado is True and not salida.get("activity") and not sabido.get("activity"):
        salida["activity"] = "certified_diving"
    reparto, actividad = salida.get("group_allocation"), salida.get("activity")
    if settings.actividad_del_reparto and isinstance(reparto, dict) and actividad and actividad not in reparto:
        # CAL-F (18-oct, grupo-mixto-precio-cop-total 2/3): "1 buzo avanzado y 2 para bautismo" daba el reparto
        # {certified_diving: 1, minicourse: 2} (bien) y la actividad padi_advanced: el bot cotizaba el Curso Avanzado.
        # Si la actividad no es de nadie del reparto, se contradicen; manda el reparto.
        nueva = actividad_principal_del_reparto(reparto)
        if nueva:
            logger.info(f"[EXTRACT][CAL-F] activity={actividad!r} no está en el reparto {reparto}: {nueva!r}")
            salida["activity"] = nueva
    # Regla del catálogo: el buceo certificado (nombrado: fun dives, paquetes de buceos) exige certificación.
    # mod-2 (18-oct, decisión de Gadea, flag `certificado_solo_si_lo_dice`): que el cliente elija el buceo certificado NO
    # dice que lo esté ("fun dives"): tiene que confirmarlo; con el flag, la regla no lo deduce.
    if (not settings.certificado_solo_si_lo_dice and salida.get("activity") == "certified_diving"
            and "is_certified" not in salida and certificado is not True):
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

# gen-4 (21-oct, flag `vivir_no_es_residir`): "de una ciudad de Colombia" y "residente" se leían como VIVIR allí ("I live
# in Bogotá", "estoy viviendo en Colombia por trabajo", "sí, vivo aquí" a "¿eres colombiano o residente?" → true, COP).
# La regla del negocio (policies.json, colombian_pricing): COP para los colombianos, vivan donde vivan, y los
# residentes, que es tener cédula de extranjería. Nacer allí no da la nacionalidad sola (Gadea, 21-oct): null.
# gen-6 (21-oct, flag `baru_sale_de_cartagena`): "estamos hospedados en Barú" no daba origen (G3-06: Barú no es las
# islas, y tampoco era nada) y el bot volvía a preguntar desde dónde sale (banco gen-6 2/2). La política
# (policies.json): quien se aloja en Barú o Playa Blanca sale desde Cartagena (Muelle de la Bodeguita).
_BARU_SALE_DE_CARTAGENA = (
    ("La cita de location tiene que nombrar el lugar (Cartagena, las islas, un hotel).",
     "Alojado en Barú o en Playa Blanca (no son las islas: allí no recogemos, y desde allí se sale desde Cartagena) → "
     "cartagena. La cita de location tiene que nombrar el lugar (Cartagena, las islas, Barú, un hotel)."),
    ("The location quote must name the place (Cartagena, the islands, a hotel).",
     "Staying in Barú or Playa Blanca (they are not the islands: we do not pick up there, and from there they set out "
     "from Cartagena) → cartagena. The location quote must name the place (Cartagena, the islands, Barú, a hotel)."),
)

_VIVIR_NO_ES_RESIDIR = (
    # Solo se AÑADE una frase: reescribir la definición de residente (21-oct, primeras versiones) hacía que un extranjero
    # con cédula de extranjería pasara a false (banco 0/15); la regla de siempre los lee bien (40/40).
    ("Nunca lo deduzcas del idioma en que escribe ni de su nombre.",
     "Nunca lo deduzcas del idioma en que escribe ni de su nombre. true si dice que es colombiano, viva donde viva "
     "(también fuera del país), o que tiene cédula de extranjería, aunque sea de otra nacionalidad. Solo vivir, "
     "trabajar, estar o haber nacido en Colombia, o ser expat, sin decir más, es null."),
    ("Never infer it from the language they write in or from their name.",
     "Never infer it from the language they write in or from their name. True if they say they are Colombian, wherever "
     "they live (also abroad), or that they have a cédula de extranjería, even if they are a foreign national. Only "
     "living, working, staying or having been born in Colombia, or being an expat, with nothing more, is null."),
)

# gen-14 (21-oct, flag `gentilicio_es_colombiano`): con «estar» en la lista de lo que no dice la nacionalidad, «Somos de
# Cali y ya estamos alojados en Isla Grande» bajaba a null (de 2/3 a 1/3 colombiano) y «soy paisa» nunca contaba (0/3):
# el bot cotizaba en USD a colombianos (causa (a) de moneda en G10/G9, Coral #999). Decir de qué ciudad o región de
# Colombia es (o su gentilicio) dice que es colombiano; alojarse o viajar no dice nada. Se aplica tras
# `_VIVIR_NO_ES_RESIDIR`.
_GENTILICIO_ES_COLOMBIANO = (
    ("Solo vivir, trabajar, estar o haber nacido en Colombia, o ser expat, sin decir más, es null.",
     "Solo vivir, trabajar o haber nacido en Colombia, o ser expat, sin decir más, es null («vivo en Medellín», «I live "
     "in Bogotá»). Ser DE una ciudad o región de Colombia, dicho como su origen o con su gentilicio («somos de "
     "Barranquilla», «soy costeña», «rolo»), sí es ser colombiano: true, aunque además cuente dónde se aloja. Alojarse o "
     "estar de viaje en un sitio no dice nada de la nacionalidad."),
    ("Only living, working, staying or having been born in Colombia, or being an expat, with nothing more, is null.",
     "Only living, working or having been born in Colombia, or being an expat, with nothing more, is null (\"I live in "
     "Bogotá\", \"vivo en Medellín\"). Being FROM a Colombian city or region, said as their origin or with its demonym "
     "(\"we're from Barranquilla\", \"I'm costeña\", \"rolo\"), does make them Colombian: true, even if they also say "
     "where they are staying. Staying or travelling somewhere says nothing about nationality."),
)

# arq-1f (22-oct, flag `el_verbo_no_la_ciudad`, decisión de Gadea: «soy de Medellín» es colombiano). Los ejemplos de
# gen-14 ponían Medellín en el lado null («vivo en Medellín») y Barranquilla en el true («somos de Barranquilla»), y el
# modelo aprendió la ciudad en vez del verbo: «Soy de Medellín, ¿cuánto cuesta el Open Water?» salía null 2 de 2 y «vivo
# en Barranquilla» true 3 de 3 (banco gen-4, 22-oct). Pares con la MISMA ciudad en los dos lados. Sustituye la frase de
# `_GENTILICIO_ES_COLOMBIANO` (se aplica detrás).
_EL_VERBO_NO_LA_CIUDAD = (
    (_GENTILICIO_ES_COLOMBIANO[0][1],
     "Solo vivir, trabajar o haber nacido en Colombia, o ser expat, sin decir más, es null. Ser DE una ciudad o región de "
     "Colombia, dicho como su origen o con su gentilicio, sí es ser colombiano: true, aunque además cuente dónde se aloja "
     "o dónde vive. Lo que decide es el verbo, no la ciudad: «vivo en Medellín» es null y «soy de Medellín» es true; «I "
     "live in Bogotá» es null y «I'm from Bogotá» es true; «soy paisa», «soy costeña» o «rolo» son true. Alojarse o "
     "estar de viaje en un sitio no dice nada de la nacionalidad."),
    (_GENTILICIO_ES_COLOMBIANO[1][1],
     "Only living, working or having been born in Colombia, or being an expat, with nothing more, is null. Being FROM a "
     "Colombian city or region, said as their origin or with its demonym, does make them Colombian: true, even if they "
     "also say where they are staying or living. The verb decides, not the city: \"I live in Bogotá\" is null and \"I'm "
     "from Bogotá\" is true; \"vivo en Medellín\" is null and \"soy de Medellín\" is true; \"paisa\", \"costeña\" or "
     "\"rolo\" are true. Staying or travelling somewhere says nothing about nationality."),
)

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

# arq-1r (22-oct, flag `cedula_de_extranjeria_manda`): «extranjero o turista: false» chocaba con la cédula de extranjería,
# que es justo la de los extranjeros residentes (paga en COP, decisión de Álvaro del 17-oct). Con historial
# («living in Bogotá»), «I have a cédula de extranjería» salía false 2 de 9 lecturas (G10 nº 4, g10-047). Una frase.
_CEDULA_DE_EXTRANJERIA_MANDA = (
    ("o que es extranjero o turista: false.",
     "o que es extranjero o turista: false, salvo que diga que tiene cédula de extranjería (entonces true)."),
    ("or that they are a foreigner or tourist: false.",
     "or that they are a foreigner or tourist: false, unless they say they have a cédula de extranjería (then true)."),
)
