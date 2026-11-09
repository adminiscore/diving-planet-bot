"""Los huecos de la reserva (CALN-8 (5), 5-nov): la pregunta de cada dato que falta, determinista y en los dos idiomas
(`ask_slot`, `_texto_de_la_pregunta`), con lo que la cambia: si ya se recomendó el minicurso o se preguntó la
certificación, la actividad que el cliente preguntó, el plan del Open Water y la confirmación del origen que se lee.

Movido tal cual desde `conversational_core.py`, que lo re-exporta. Ver `src/agents/nucleo/__init__.py`.
"""

from __future__ import annotations

from src.agents.conversational_core import (
    OTRA_COSA,
    SLOT_ACTIVITY,
    SLOT_AGES,
    SLOT_CERT_OR_COURSE,
    SLOT_CERTIFICATION,
    SLOT_COMPANION_ACTIVITY,
    SLOT_COMPANION_QTY,
    SLOT_CONFIRM_CORRECTION,
    SLOT_COURSE_LEVEL,
    SLOT_HOTEL,
    SLOT_LOCATION,
    SLOT_NATIONALITY,
    SLOT_QTY,
    SLOT_REFRESHER,
    SLOT_SAFETY,
    _companion_activity_options,
    _course_level_options,
    _describe_value,
    _known_field_values,
    _pregunta_si_tambien_bucea,
)
from src.agents.nucleo.plan import (
    _dias_del_plan,
    _plan_en_duda,
    _plan_is_single_day,
    _plan_needs_overnight,
    _pregunta_origen,
    _recommended_plan_intro,
)
from src.domain import activities as dom
from src.flows import cart_render
from src.flows.como_reserva import cuando_tenga_el_hotel, hotel_conocido
from src.flows.state import ConversationState
from src.utils.text import strip_accents

# ─── RESPONDER: redactor de slot (determinista, ES/EN, cierre a conversión) ───

def _minicurso_ya_recomendado(state: ConversationState) -> bool:
    """CAL-C1: si algún mensaje del bot ya trae la recomendación entera del minicurso."""
    marcas = ("te recomiendo el *minicurso*", "I'd recommend the *mini-course*")
    return any(m in (t.get("content") or "") for t in (state.history or []) if t.get("role") == "assistant"
               for m in marcas)


# LAT-0b: un trozo de cada forma de la pregunta de la certificación (`ask_slot`), en minúsculas y sin tildes.
_PREGUNTAS_DE_CERTIFICACION = {
    "es": ("me confirmas que tienes tu certificacion", "me confirmas que tienen su certificacion",
           "eres buzo certificado?", "son buzos certificados?"),
    "en": ("can you confirm you have your certification", "can you confirm you all have your certification",
           "are you a certified diver?", "are you certified divers?"),
}


def _certificacion_ya_preguntada(state: ConversationState) -> bool:
    """LAT-0b (26-oct, decisión de Gadea #2040): la certificación se pregunta UNA vez; si el cliente contesta otra cosa,
    no se insiste (mod-2: elegir el buceo certificado no la confirma). Cuenta la que el cliente VIO: un mensaje del bot
    que la trae, en el idioma de ahora (si pidió otro, no la entendió). Marcarla al prepararla no valía: hay turnos en
    que se prepara y sale otra pregunta (el origen), y entonces no se hacía nunca."""
    trozos = _PREGUNTAS_DE_CERTIFICACION.get(state.language, ())
    return any(trozo in strip_accents((t.get("content") or "").lower()) for t in (state.history or [])
               if t.get("role") == "assistant" for trozo in trozos)


# gen-8 (`actividad_de_la_pregunta`): productos genéricos ("un curso PADI", "una especialidad"): no hay uno que ofrecer.
_SIN_OFERTA_CONCRETA = ("padi_course", "padi_specialty")


def _ofrecer_la_actividad_preguntada(state: ConversationState) -> str | None:
    """gen-8: quien pregunta por UNA actividad sin elegirla recibe la oferta de esa, no el menú de 4 (textos-B). La
    elige el cliente: "sí" confirma la recomendación (`suggested_activity`, nucleo/routing)."""
    actividad = state.actividad_preguntada
    if not actividad or actividad in _SIN_OFERTA_CONCRETA:
        return None
    if not state.detected_activity and actividad in (state.detected_group_allocation or {}):
        # DEUDA-EXT (26-oct): es la actividad de los que se suman ("vienen dos amigos que quieren probar el minicurso"),
        # no una oferta para el grupo que aún no ha elegido la suya (banco-lat11 a4: se ofrecía el minicurso a 3 buzos).
        return None
    if state.suggested_activity and state.suggested_activity != actividad:
        return None
    lang = state.language
    state.suggested_activity = actividad
    nombre = dom.label(actividad, lang)
    state.quick_replies = [{"title": "✅ Sí, quiero reservar" if lang == "es" else "✅ Yes, let's book it",
                            "value": "sí" if lang == "es" else "yes"}]
    return (f"Si quieres, te ayudo a reservar: *{nombre}*. ¿Te animas? 🌊" if lang == "es" else
            f"If you'd like, I can help you book it: *{nombre}*. Shall we? 🌊")


def _ow_plan() -> tuple[dict, dict]:
    """La ficha y la fila de la tarifa del Open Water desde Cartagena (lat-deuda-u: sus días e inmersiones salen de ahí,
    no de un texto fijo)."""
    from src.flows.catalog import RAW_SERVICES, fila_de_la_tarifa  # lazy

    ficha = RAW_SERVICES[dom.service_ids("padi_open_water", "cartagena")[0]]
    return ficha, fila_de_la_tarifa(ficha["tarifa"])


def _ow_dias() -> int:
    return _ow_plan()[0]["duration_days"]


def _ow_inmersiones() -> int:
    return _ow_plan()[1]["num_dives"]


# ORIGEN-CONFIRMA (27-oct): la confirmación del origen que leyó el extractor y Jev, seguro, dijo que el mensaje no da.
_CONFIRMA_ORIGEN = {
    "island": {"es": "Entonces, ¿ya estarás en las *Islas del Rosario* (salida desde las islas)? 🌴",
               "en": "So, will you already be on the *Rosario Islands* (departing from the islands)? 🌴"},
    "cartagena": {"es": "Entonces, ¿saldrías *desde Cartagena* (Muelle de la Bodeguita)? 🚤",
                  "en": "So, would you leave *from Cartagena* (Muelle de la Bodeguita)? 🚤"},
}


def ask_slot(state: ConversationState, slot: str, *, reasking: bool = False) -> str:
    """La pregunta de la reserva por el slot que falta (`_texto_de_la_pregunta`). CALN-6 paso 1: se apunta en el turno,
    para que el compositor (`src/agents/compositor.py`) la ponga una vez y al final."""
    texto = _texto_de_la_pregunta(state, slot, reasking=reasking)
    if not isinstance(getattr(state, "_preguntas_del_turno", None), list):
        state._preguntas_del_turno = []
    state._preguntas_del_turno.append((slot, texto))
    return texto


def _texto_de_la_pregunta(state: ConversationState, slot: str, *, reasking: bool = False) -> str:
    """Pregunta natural por el slot que falta. Un solo mensaje, UNA pregunta,
    quick-replies solo donde el plan lo permite (ubicación / sí-no).

    `reasking=True` cuando el mismo slot se vuelve a preguntar porque el turno
    anterior no lo resolvió (aportó otro dato, o fue una pregunta de info): se
    omiten los preámbulos (p. ej. la recomendación del plan) para no repetir el
    mismo bloque entero — hallazgo del guion Rocío en vivo (2026-07-22)."""
    lang = state.language
    state.core_pending_slot = slot
    state.quick_replies = []

    if slot == SLOT_ACTIVITY and (oferta := _ofrecer_la_actividad_preguntada(state)):
        return oferta
    if (slot == SLOT_ACTIVITY and state.quiere_bucear
            and not state.suggested_activity and not state.detected_group_allocation):
        # CAL-C1 (16-oct; regla de Gadea 14/27-sep: recomendar según lo que se sabe). Quien ya dijo que quiere bucear
        # recibía el menú entero ("5 inmersiones", "Muchas gracias!", "no estamos certificados" → "¿Con cuál te
        # animas — buceo, minicurso, snorkel…?"; banco CAL, 10 casos). Sabiendo que quiere bucear, lo que falta es la
        # certificación: sin certificación se recomienda el minicurso (lo confirma el cliente); sin saberla, se pregunta.
        certificado = _known_field_values(state).get("is_certified")
        if certificado is False:
            state.suggested_activity = "minicourse"
        elif certificado is None and not _certificacion_ya_preguntada(state):
            return ask_slot(state, SLOT_CERTIFICATION, reasking=reasking)
    if (slot == SLOT_ACTIVITY and state.suggested_activity == "minicourse"
            and reasking and not _minicurso_ya_recomendado(state)):
        # La recomendación entera la primera vez que se hace (la corta "¿minicurso u Open Water?" no recomendaba:
        # cal-60, también cuando la recomendación se había apuntado en un turno anterior sin llegar a decirse).
        reasking = False

    if slot == SLOT_ACTIVITY and state.suggested_activity == "padi_open_water":
        # Quien pide un curso desde cero: se recomienda el Open Water y el minicurso queda como opcion.
        state.quick_replies = (
            [{"title": "✅ Sí, el Open Water", "value": "curso open water"},
             {"title": "🤿 Mejor el minicurso", "value": "minicurso"}]
            if lang == "es" else
            [{"title": "✅ Yes, Open Water", "value": "open water course"},
             {"title": "🤿 The mini-course instead", "value": "mini course"}]
        )
        if reasking:
            return (
                "¿Te animas con el *curso Open Water* o prefieres probar antes con el *minicurso*? 🌊"
                if lang == "es" else
                "Shall we go for the *Open Water course*, or would you rather try the *mini-course* first? 🌊"
            )
        return (
            f"Para certificarte desde cero, el curso es el *PADI Open Water*: {_ow_dias()} días en las Islas del "
            f"Rosario con teoría online, piscina y {_ow_inmersiones()} inmersiones. Si antes prefieres probar, está el "
            "*minicurso*, sin "
            "necesidad de experiencia. ¿Te animas con el Open Water? 🤿"
            if lang == "es" else
            f"To get certified from scratch, the course is the *PADI Open Water*: {_ow_dias()} days in the Rosario "
            f"Islands with online theory, pool and {_ow_inmersiones()} dives. If you'd rather try first, there's the "
            "*mini-course*, no "
            "experience needed. Shall we go for the Open Water? 🤿"
        )
    if slot == SLOT_ACTIVITY and state.suggested_activity == "minicourse":
        # u3-5: recomendar el minicurso a quien empieza, y que lo confirme el cliente (Gadea, 27-sep).
        state.quick_replies = (
            [{"title": "✅ Sí, el minicurso", "value": "minicurso"},
             {"title": "🎓 El curso Open Water", "value": "curso open water"}]
            if lang == "es" else
            [{"title": "✅ Yes, the mini-course", "value": "mini course"},
             {"title": "🎓 The Open Water course", "value": "open water course"}]
        )
        if reasking:
            # CAL-C1: la corta también recomienda (cal-60: "¿minicurso u Open Water?" no se leía como recomendación).
            return (
                "Para empezar, lo ideal es el *minicurso*: no hace falta experiencia ni certificación. ¿Te animas? "
                "(Si prefieres certificarte, está el *curso Open Water*.) 🤿"
                if lang == "es" else
                "To start, the *mini-course* is the ideal choice: no experience or certification needed. Shall we go "
                "for it? (If you'd rather get certified, there's the *Open Water course*.) 🤿"
            )
        return (
            "Para una primera vez te recomiendo el *minicurso*: teoría, práctica en aguas tranquilas y una "
            "inmersión en el mar con instructor, sin necesidad de experiencia. Si lo que buscas es "
            "certificarte, está el *curso PADI Open Water*. ¿Te animas con el minicurso? 🤿"
            if lang == "es" else
            "For a first time I'd recommend the *mini-course*: theory, practice in calm water and a sea dive "
            "with an instructor, no experience needed. If you want to get certified, there's the *PADI Open "
            "Water course*. Shall we go for the mini-course? 🤿"
        )
    if slot == SLOT_ACTIVITY and state.is_certified is True and state.acompanante_sin_certificar:
        # #3300 (2b): el buzo con alguien que no bucea (Guadalajara t2, jubilados t2) recibía «¿la salida de 2 inmersiones, un
        # paquete o un curso avanzado?», sin nada para quien no bucea: se pregunta por los dos.
        es = lang == "es"
        state.quick_replies = [
            {"title": ("🤿 Y minicurso" if es else "🤿 And mini-course"),
             "value": "2 inmersiones para mí y minicurso para quien no bucea" if es else "2 dives for me and the mini-course for my companion"},
            {"title": ("🐠 Y snorkel" if es else "🐠 And snorkeling"),
             "value": "2 inmersiones para mí y snorkel para quien no bucea" if es else "2 dives for me and snorkeling for my companion"},
            {"title": ("🚤 Y acompañante" if es else "🚤 And boat companion"),
             "value": "2 inmersiones para mí y de acompañante quien no bucea" if es else "2 dives for me and my companion just comes on the boat"},
        ]
        return ("¿Te animas con la *salida de 2 inmersiones* para ti y, para quien no bucea, el *minicurso*, el *snorkel* o ir de "
                "*acompañante* en la lancha? 🌊" if es else
                "Shall we go for the *2-dive trip* for you and, for your companion, the *mini-course*, *snorkeling* or just coming "
                "along on the *boat*? 🌊")
    if slot == SLOT_ACTIVITY and state.is_certified is True:
        # 14-oct (ronda flujo1-B3): a quien ya dijo que es buzo certificado se le ofrecía el menú entero (minicurso,
        # snorkel…) y el juez lo marcaba como repregunta. Regla de Gadea (14/27-sep): recomendar según el contexto, y
        # que elija el cliente: para un certificado, la salida de 2 inmersiones, los paquetes o un curso avanzado.
        state.quick_replies = (
            [{"title": "🤿 Salida de 2 inmersiones", "value": "buceo certificado"},
             {"title": "📅 Paquete de varios días", "value": "paquete de buceos"},
             {"title": "🎓 Curso avanzado", "value": "curso advanced"}]
            if lang == "es" else
            [{"title": "🤿 2-dive trip", "value": "certified diving"},
             {"title": "📅 Multi-day package", "value": "dive package"},
             {"title": "🎓 Advanced course", "value": "advanced course"}]
        )
        if reasking:
            return (
                "¿Te animas con la *salida de 2 inmersiones*, un *paquete de varios días* o un *curso avanzado*? 🌊"
                if lang == "es" else
                "Shall we go for the *2-dive trip*, a *multi-day package* or an *advanced course*? 🌊"
            )
        return (
            "Como ya eres buzo certificado, te propongo la *salida de 2 inmersiones* en las Islas del Rosario; si "
            "quieres más días, hay *paquetes de varias inmersiones*, y si buscas subir de nivel, el *curso Advanced* "
            "o una especialidad. ¿Cuál te interesa? 🤿"
            if lang == "es" else
            "Since you're already a certified diver, I'd suggest the *2-dive trip* in the Rosario Islands; for more "
            "days there are *multi-dive packages*, and to level up, the *Advanced course* or a specialty. Which one "
            "interests you? 🤿"
        )
    if (slot == SLOT_ACTIVITY and state.is_certified is False
            and not state.suggested_activity):
        # 18-oct (ronda mod-F): el simétrico de `recomendar_a_certificados`. A quien sabemos que NO es certificado y no
        # ha elegido ("Sería buzo principiante y snorkeling": el extractor no elige actividad en un mensaje ambiguo) se
        # le repetía el menú entero, con "buceo" (solo para certificados) incluido. Regla de Gadea: recomendar según lo
        # que se sabe y que elija el cliente, sin adivinar la actividad.
        state.quick_replies = (
            [{"title": "🤿 Minicurso", "value": "minicurso"},
             {"title": "🐠 Snorkel", "value": "snorkel"},
             {"title": "🎓 Curso Open Water", "value": "curso open water"}]
            if lang == "es" else
            [{"title": "🤿 Mini-course", "value": "mini course"},
             {"title": "🐠 Snorkeling", "value": "snorkeling"},
             {"title": "🎓 Open Water course", "value": "open water course"}]
        )
        if reasking:
            return (
                "¿Te animas con el *minicurso*, el *snorkel* o el *curso Open Water*? 🌊"
                if lang == "es" else
                "Shall we go for the *mini-course*, *snorkeling* or the *Open Water course*? 🌊"
            )
        return (
            "Sin certificación, para bucear lo ideal es el *minicurso*: no hace falta experiencia y vas con un "
            "instructor. Si prefieres disfrutar el arrecife desde la superficie, está el *snorkel*, y si quieres "
            "certificarte, el *curso PADI Open Water*. ¿Cuál te interesa? 🤿"
            if lang == "es" else
            "Without a certification, the *mini-course* is the ideal way to dive: no experience needed and you go "
            "with an instructor. To enjoy the reef from the surface there's *snorkeling*, and to get certified, the "
            "*PADI Open Water course*. Which one interests you? 🤿"
        )
    if slot == SLOT_ACTIVITY:
        # `reasking=True`: se re-ancla la actividad tras una respuesta de info
        # (RAG). Repetir el bloque entero de 4 bullets que ya se mostró al
        # abrir es ruido — una línea que reofrece las opciones basta (fallo en
        # vivo 2026-07-24: el menú completo se pegaba tras cada recomendación).
        if reasking:
            return (
                "¿Con cuál te animas — *buceo*, *minicurso*, *snorkel* o un *curso PADI*? 🌊"
                if lang == "es" else
                "Which one are you leaning toward — *diving*, a *mini-course*, "
                "*snorkeling* or a *PADI course*? 🌊"
            )
        return (
            "Cuéntame, ¿qué te gustaría vivir con nosotros? 🤿\n"
            "• *Buceo* en las Islas del Rosario, si ya eres buzo certificado\n"
            "• *Minicurso* para probar el buceo por primera vez (¡no necesitas experiencia!)\n"
            "• *Snorkel* para disfrutar el arrecife desde la superficie, ideal en familia\n"
            "• *Cursos PADI* completos, del Open Water en adelante\n"
            "Dime qué te llama la atención y lo armamos juntos. 🌊"
            if lang == "es" else
            "Tell me, what would you like to experience with us? 🤿\n"
            "• *Diving* in the Rosario Islands, if you're already certified\n"
            "• A beginner *mini-course* to try diving for the first time (no experience needed!)\n"
            "• *Snorkeling* to enjoy the reef from the surface, great for families\n"
            "• Full *PADI courses*, from Open Water up\n"
            "Tell me what catches your eye and we'll put it together. 🌊"
        )
    if slot == SLOT_CERT_OR_COURSE:
        state.quick_replies = (
            [{"title": "✅ Ya la tenemos", "value": "already_certified"},
             {"title": "🎓 Queremos sacarla", "value": "wants_course"}]
            if lang == "es" else
            [{"title": "✅ We already have it", "value": "already_certified"},
             {"title": "🎓 We want to get it", "value": "wants_course"}]
        )
        level = state.cert_or_course_level
        name = dom.label(level, lang) if level else None
        if lang == "es":
            what = f"el *{name}*" if name else "esa certificación"
            return f"Para recomendarte bien: ¿ya tienen {what} o quieren sacarla con el curso? 🤿"
        what = f"the *{name}*" if name else "that certification"
        return f"So I can recommend the right plan: do you already hold {what}, or do you want to get it with the course? 🤿"
    if slot == SLOT_COURSE_LEVEL:
        options = _course_level_options(state)
        current = dom.by_id(state.detected_activity) if state.detected_activity else None
        is_specialty = bool(current and current.family == "specialty")
        state.quick_replies = [{"title": dom.label(o, lang), "value": o} for o in options]
        lines = []
        for option in options:
            pitch = dom.text(option, "pitch", lang)
            lines.append(f"• *{dom.label(option, lang)}*" + (f" — {pitch}" if pitch else ""))
        if lang == "es":
            head = "¿Qué especialidad te interesa? 🐠" if is_specialty else "¿Qué curso te interesa? 🎓"
        else:
            head = "Which specialty are you interested in? 🐠" if is_specialty else "Which course are you interested in? 🎓"
        return head + "\n" + "\n".join(lines)
    if slot == SLOT_CERTIFICATION:
        plural = (state.detected_group_size or 1) > 1
        if state.detected_activity == "certified_diving":
            # LAT-0b (26-oct, decisión de Gadea #2040): ya eligió el buceo certificado; la pregunta es para confirmarlo
            # (mod-2), no para recomendar: «¿Eres buzo certificado?» sonaba a no haberle escuchado.
            if lang == "es":
                return ("Para la salida de buceo certificado, ¿me confirmas que "
                        + ("tienen su certificación (Open Water o superior)? El día les pedirán el carné."
                           if plural else "tienes tu certificación (Open Water o superior)? El día te pedirán el carné."))
            return ("For the certified-diving trip, can you confirm "
                    + ("you all have your certification (Open Water or higher)? You'll be asked for your cards on the day."
                       if plural else "you have your certification (Open Water or higher)? You'll be asked for your card on the day."))
        if lang == "es":
            q = ("¿Son buzos certificados?" if plural
                 else "¿Eres buzo certificado?")
            return (f"¡Genial! Para recomendarte el plan perfecto: {q} "
                    + "(Y si no, ¡tranqui! El minicurso es ideal para empezar. 🤿)")
        q = "Are you certified divers?" if plural else "Are you a certified diver?"
        return (f"Great! So I can recommend the perfect plan: {q} "
                "(And if not, no worries — the mini-course is the ideal way to start. 🤿)")
    if slot == SLOT_LOCATION:
        state.quick_replies = (
            [{"title": "🚤 Desde Cartagena", "value": "cartagena"},
             {"title": "🏝️ Ya en las islas", "value": "isla"}]
            if lang == "es" else
            [{"title": "🚤 From Cartagena", "value": "cartagena"},
             {"title": "🏝️ Already on the islands", "value": "island"}]
        )
        if _plan_en_duda(state):
            # CAL-F (flag `origen_neutro_con_dos_planes`): duda entre dos planes; ninguno se afirma (ver `_plan_en_duda`).
            return _pregunta_origen(lang)
        if _plan_needs_overnight(state):
            # Politica `courses_overnight_requirement` / paquetes de varios dias: hay que dormir en
            # las islas; ofrecer "ida y vuelta el mismo dia" contradecia la referencia (ronda A).
            # CAL-D (17-oct, cal-74): los días EXACTOS de la ficha del plan ("dura 2 días"); "varios
            # días" solo cuando aún no se sabe qué plan es (un paquete sin concretar: de 2 a 4 días).
            dias = _dias_del_plan(state)
            return (
                f"¿Desde dónde saldrías? Este plan dura {(f'{dias} día' if dias == 1 else f'{dias} días') if dias else 'varios días'} y hay "
                "que *dormir en las islas* (el alojamiento no está incluido): puedes salir *desde Cartagena* "
                "el primer día o, si ya estás *en las islas*, coordinamos la recogida en tu hotel."
                if lang == "es" else
                f"Where would you be departing from? This plan takes {(f'{dias} day' if dias == 1 else f'{dias} days') if dias else 'several days'} "
                "and you need to *stay on the islands* (accommodation is not included): you can leave *from "
                "Cartagena* on the first day or, if you're already *on the islands*, we arrange pickup at your "
                "hotel."
            )
        if not _plan_is_single_day(state):
            # Paso 6 (ronda B): con la actividad sin concretar ("curso básico" -> curso PADI generico)
            # se ofrecia "ida y vuelta el mismo dia" a un Open Water. Solo se afirma si se sabe.
            return _pregunta_origen(lang)
        if (getattr(state, "_senales_router", None) or {}).get("asks_question"):
            # CALN (27-oct, g21 del banco de grupos): «¿y si en vez de un día buceamos 2 días?» recibía «ida y vuelta el
            # mismo día» con el plan de un día del estado. Si el cliente está preguntando, el plan puede cambiar: no se
            # afirma su duración.
            return _pregunta_origen(lang)
        return _pregunta_origen(lang, mismo_dia=True)
    if slot == SLOT_HOTEL:
        if state.hotel and not hotel_conocido(state):
            return cuando_tenga_el_hotel(state)  # CALN-35: ya ha dicho que no lo tiene
        return (
            "¿En qué hotel te vas a alojar? Lo necesito para reservar y coordinar la recogida."
            if lang == "es" else
            "Which hotel are you staying at? I need it to book and arrange pickup."
        )
    if slot == SLOT_SAFETY:
        state.quick_replies = (
            [{"title": "✅ Sí", "value": "si"}, {"title": "❌ No", "value": "no"}]
            if lang == "es" else
            [{"title": "✅ Yes", "value": "yes"}, {"title": "❌ No", "value": "no"}]
        )
        plural = (state.detected_group_size or 1) > 1
        plan_intro = "" if reasking else _recommended_plan_intro(state)
        if lang == "es":
            q = ("¿Ha pasado *más de 2 años* desde la última inmersión de alguno del grupo?"
                 if plural else "¿Han pasado *más de 2 años* desde tu última inmersión?")
        else:
            q = ("Has it been *more than 2 years* since any diver in the group last dived?"
                 if plural else "Has it been *more than 2 years* since your last dive?")
        return f"{plan_intro}{q}"
    if slot == SLOT_REFRESHER:
        state.quick_replies = (
            [{"title": "✅ Sí", "value": "si"}, {"title": "❌ No", "value": "no"}]
            if lang == "es" else
            [{"title": "✅ Yes", "value": "yes"}, {"title": "❌ No", "value": "no"}]
        )
        # Se cobra (owner 2026-09-14): precio por persona desde el catalogo.
        price = cart_render.refresher_price_text(state, una_moneda=True)  # G3-07a
        # gen-7 (20-oct): lo que dice la base del refresher (ficha `refresher:minicourse` y `medical_restrictions`): se
        # reserva como el Minicurso de Buceo y usa el formulario médico de curso, aunque sea buzo certificado.
        plural = (state.detected_group_size or 1) > 1
        return (
            "El *refresher* es un repaso con instructor antes de volver a bucear: se reserva como *Minicurso de "
            f"Buceo* y cuesta *{price}* por persona que lo necesite. Lleva el formulario médico de curso (aunque "
            "estén certificados, el enlace llega con la reserva). "
            + ("¿Les interesa?" if plural else "¿Te interesa?")
            if lang == "es" else
            "The *refresher* is an instructor-led review before diving again: it is booked as the *Dive Mini "
            f"Course* and costs *{price}* per person who needs it. It uses the course medical form (even for "
            "certified divers; the link comes with the booking). Are you interested?"
        )
    if slot == SLOT_CONFIRM_CORRECTION and state.pending_correction:
        known = _known_field_values(state)
        origen = state.pending_correction.get("location")
        if len(state.pending_correction) == 1 and origen in _CONFIRMA_ORIGEN and known.get("location") is None:
            # ORIGEN-CONFIRMA: no había origen; se confirma lo que leyó el extractor (ver `_poner_ubicacion`).
            state.quick_replies = (
                [{"title": "✅ Sí", "value": "sí"}, {"title": "No", "value": "no"}]
                if lang == "es" else
                [{"title": "✅ Yes", "value": "yes"}, {"title": "No", "value": "no"}]
            )
            return _CONFIRMA_ORIGEN[origen]["es" if lang == "es" else "en"]
        lines = "\n".join(
            f"• {_describe_value(field, known.get(field), lang)} → *{_describe_value(field, value, lang)}*"
            for field, value in state.pending_correction.items()
        )
        state.quick_replies = (
            [{"title": "✅ Sí, cámbialo", "value": "sí"}, {"title": "↩️ No, como estaba", "value": "no"}]
            if lang == "es" else
            [{"title": "✅ Yes, change it", "value": "yes"}, {"title": "↩️ No, keep it", "value": "no"}]
        )
        return (
            f"Solo para confirmar, ¿lo cambio?\n{lines}"
            if lang == "es" else
            f"Just to confirm, should I change it?\n{lines}"
        )
    if slot == SLOT_QTY and state.pending_companion_in_group:
        pending = state.pending_companion_in_group
        total = state.detected_group_size or 0
        more = total + pending["qty"]
        label = dom.text(pending["activity"], "recall", lang, default=pending["activity"])
        state.quick_replies = (
            [{"title": f"Seguimos siendo {total}", "value": str(total)},
             {"title": f"Somos {more}", "value": str(more)}]
            if lang == "es" else
            [{"title": f"Still {total}", "value": str(total)},
             {"title": f"We're {more}", "value": str(more)}]
        )
        return (
            f"¡Anotado, *{label}*! Para cuadrar el precio: ¿seguís siendo *{total}* en total "
            "o se suma alguien más? 😊"
            if lang == "es" else
            f"Got it, *{label}*! To get the price right: are you still *{total}* in total, "
            "or is someone else joining? 😊"
        )
    if slot == SLOT_QTY:
        # CALN-18: a quien solo habla de sí mismo no se le da por hecho un grupo (ni que vaya solo: lo dice él). Y «Así te paso el
        # precio exacto» ya no se sostiene: el precio es por persona y no damos totales (decisión de Gadea, 9-oct).
        from src.agents.jev_router import HABLA_DE_SI  # lazy

        if (getattr(state, "_senales_router", None) or {}).get(HABLA_DE_SI):
            return ("¿Para cuántas personas sería: solo para ti o van más? 😊" if lang == "es" else
                    "How many people would this be for: just you, or more? 😊")
        return "¿Y para cuántas personas armamos el plan? 😊" if lang == "es" else "And how many people should I plan for? 😊"
    if slot == SLOT_COMPANION_QTY:
        act = state.pending_companion_activity
        label = dom.text(act, "recall", "es" if lang == "es" else "en", default=act or "")
        return (
            f"¿Cuántos serían para {label}? Así les cuento el plan exacto. 😊"
            if lang == "es" else
            f"How many people would that be for {label}? That way I can give you the exact plan. 😊"
        )
    if slot == SLOT_COMPANION_ACTIVITY:
        if _pregunta_si_tambien_bucea(state):
            varios = (state.pending_undecided_qty or 1) > 1
            state.quick_replies = [
                {"title": (f"Sí, también bucea{'n' if varios else ''}" if lang == "es" else "Yes, diving too"),
                 "value": "certified_diving"},
                {"title": "No, otra cosa" if lang == "es" else "No, something else", "value": OTRA_COSA},
            ]
            return (
                ("¿Los demás también van a bucear? 🤿" if varios else "¿La otra persona también va a bucear? 🤿")
                if lang == "es" else
                ("Are the others diving too? 🤿" if varios else "Is the other person diving too? 🤿")
            )
        # Dos pasos, mismo slot pendiente: sin saber si se quedan uno o varios días
        # no se puede recomendar bien (el Open Water necesita varios), así que se
        # pregunta primero, como la nacionalidad o la ubicación. Con ese dato, se
        # recomiendan las opciones y el cliente elige.
        if state.detected_duration is None:
            state.quick_replies = (
                [{"title": "☀️ Un día", "value": "single_day"},
                 {"title": "🏝️ Varios días", "value": "multi_day"}]
                if lang == "es" else
                [{"title": "☀️ One day", "value": "single_day"},
                 {"title": "🏝️ Several days", "value": "multi_day"}]
            )
            if state.pending_undecided_qty:
                # CALN-2 (27-oct, tanda de precios q1 t2): quien no ha elegido puede ser un buzo certificado («uno es buzo
                # certificado y los otros dos queremos snorkel»); la pregunta no supone que sea quien no lo está.
                varios = state.pending_undecided_qty > 1
                return (
                    f"Para recomendar lo que mejor le{'s' if varios else ''} encaje a quien{'es' if varios else ''} "
                    f"aún no ha{'n' if varios else ''} elegido: ¿van a estar *un solo día* o *varios días*? 🌊"
                    if lang == "es" else
                    f"So I can recommend what suits {'those who haven' if varios else 'the one who hasn'}'t chosen yet: "
                    "will you be here for *one day* or *several days*? 🌊"
                )
            return (
                "¡Qué bien que venga alguien más! 🌊 Para recomendarle lo que mejor le "
                "encaje: ¿van a estar *un solo día* o *varios días*?"
                if lang == "es" else
                "Great that someone else is coming! 🌊 So I can recommend what suits "
                "them best: will you be here for *one day* or *several days*?"
            )
        options = _companion_activity_options(state)
        state.quick_replies = [{"title": dom.label(o, lang), "value": o} for o in options]
        lines = []
        for option in options:
            pitch = dom.text(option, "pitch", lang)
            lines.append(f"• *{dom.label(option, lang)}*" + (f" — {pitch}" if pitch else ""))
        if state.pending_undecided_qty:
            plural = state.pending_undecided_qty > 1
            head = (
                ("Para quienes aún no han elegido te recomiendo estas opciones. ¿Cuál les apetece más? 🐠"
                 if plural else
                 "Para quien aún no ha elegido te recomiendo estas opciones. ¿Cuál le apetece más? 🐠")
                if lang == "es" else
                ("For those who haven't chosen yet I'd recommend these options. Which one do they like best? 🐠"
                 if plural else
                 "For the one who hasn't chosen yet I'd recommend these options. Which one do they like best? 🐠")
            )
        else:
            head = (
                "Para tu acompañante te recomiendo estas opciones. ¿Cuál le apetece más? 🐠"
                if lang == "es" else
                "For your companion I'd recommend these options. Which one do they like best? 🐠"
            )
        return head + "\n" + "\n".join(lines)
    if slot == SLOT_AGES:
        return (
            "Me comentaste que van menores — ¿qué edades tienen? Así les preparo "
            "la actividad adecuada (snorkel, Bubble Makers o minicurso según la edad)."
            if lang == "es" else
            "You mentioned minors are coming — what are their ages? That way I can "
            "set up the right activity (snorkel, Bubble Makers or mini-course by age)."
        )
    if slot == SLOT_NATIONALITY:
        state.quick_replies = (
            [{"title": "🇨🇴 Sí", "value": "si"}, {"title": "🌎 No", "value": "no"}]
            if lang == "es" else
            [{"title": "🇨🇴 Yes", "value": "yes"}, {"title": "🌎 No", "value": "no"}]
        )
        # Singular/plural como en certificación y seguridad — en vivo salía
        # siempre en plural ("¿sois colombianos?") a quien viajaba solo.
        plural = (state.detected_group_size or 1) > 1
        # gen-4: "residente" se contestaba "sí, vivo aquí"; lo que cuenta es la nacionalidad o la cédula de extranjería
        # (policies.json, colombian_pricing). Sin género supuesto (SIN_GENERO_SUPUESTO).
        pregunta = (
            ("¿son de nacionalidad colombiana o tienen cédula de extranjería?" if plural
             else "¿eres de nacionalidad colombiana o tienes cédula de extranjería?")
            if lang == "es" else
            # Sin "resident" (Gonzalo, #852): "resident" se contestaba "I live here", el fallo de gen-4.
            # Sin explicar, «cédula de extranjería» quedaba en español en una respuesta en inglés (ronda gen14-B,
            # reserva-ingles idioma); decisión de Gadea (#1078): una explicación corta y sin «residents».
            ("are you Colombian nationals, or do you have a Colombian *cédula de extranjería* (Colombia's ID card "
             "for foreigners)?" if plural else
             "are you a Colombian national, or do you have a Colombian *cédula de extranjería* (Colombia's ID card "
             "for foreigners)?")
        )
        # La nacionalidad va la última (`next_missing_slot`), y con CALN-43 P11 las que ya salieron 2 veces no vuelven detrás.
        cabeza = ("Última cosa para darte el precio correcto:" if lang == "es"
                  else "One last thing so I can give you the right price:")
        return f"{cabeza} {pregunta}"
    raise ValueError(f"unknown slot {slot!r}")
