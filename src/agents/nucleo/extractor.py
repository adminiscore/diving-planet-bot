"""El extractor del turno (ex-5, `extractor_turno`) visto desde el núcleo: lanzarlo adelantado (lo hace el nodo
router), aplicar sus datos al estado (`_aplicar_extractor`, `_poner_*`, el reparto, las contradicciones) y guardar lo
dicho en el turno del pase o sin núcleo (lo llama `supervisor.route_message`). Es la capa de abajo de `extraction.py`.

s4-2 (19-oct): movido tal cual desde `conversational_core.py`, que lo re-exporta. Ver `src/agents/nucleo/__init__.py`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from src.agents.conversational_core import (
    _EXPLICIT_NUMBER_RE,
    _NAME_STOPWORDS,
    SLOT_COMPANION_ACTIVITY,
    SLOT_COMPANION_QTY,
    _companion_activity_options,
    _elige_quien_falta,
    _has_pending_answer,
    _jev_dice_que_no_lo_dice,
    _known_field_values,
    _otro_idioma_en_ingles,
    _same_for_customer,
)
from src.agents.intent_detector import DetectedIntent, detect_location
from src.config import settings
from src.domain import activities as dom
from src.flows import grupo
from src.flows.state import ConversationState

logger = logging.getLogger("uvicorn.error")


def _nombre_del_extractor(state: ConversationState, datos: dict | None, message: str = "") -> None:
    """El nombre que el extractor leyó con cita (si aún no lo sabemos). Una respuesta de una o dos
    palabras a una pregunta del bot no es presentarse (ronda flujo1-B2: "Frances", a "¿sois colombianos?", saludaba
    "Thank you…, Frances!")."""
    if state.client_name or not datos:
        return
    if state.core_pending_slot and len((message or "").split()) <= 2:
        return
    nombre = (datos.get("nombre") or "").strip().split()
    if not nombre or not nombre[0].isalpha() or nombre[0].lower() in _NAME_STOPWORDS:
        return
    state.client_name = nombre[0][:1].upper() + nombre[0][1:].lower()
    logger.info(f"[CORE] nombre del cliente (extractor) -> {state.client_name}")


# Campos que un turno puede corregir (tarea 7b, 2026-09-15).
_CORRECTABLE_FIELDS = (
    "is_certified", "is_colombian", "last_dive_over_2_years", "location", "group_size", "group_allocation",
)


def _has_correction_cue(state: ConversationState, message: str) -> bool:
    """La señal explícita de corrección de la regla del owner (tarea 7b): el regex de siempre
    ("perdon", "en realidad", "actually"...) o Jev seguro (>= 0,7) de que el mensaje cambia o
    corrige un dato ya dado ("esperate, somos 4 al final"; u3-5 paso 2)."""
    from src.agents import supervisor  # lazy

    jev = getattr(state, "_jev_corrects", None)
    # ex-9b paso 5: si Jev ha contestado, manda Jev; el regex solo si Jev calla. El regex tomaba "perdón, ¿cuánto
    # cuesta?" por una corrección y aplicaba el dato sin confirmarlo.
    if jev is not None:
        return jev is True
    return bool(supervisor._CORRECTION_CUE_RE.search(message))


def _route_contradictions(state: ConversationState, message: str, intent, proposed: dict) -> None:
    """Punto unico para un dato de ESTE mensaje que contradice lo ya guardado, venga
    del regex o de la verificacion LLM de campos sabidos (tarea 7b, 2026-09-15).

    Antes se ignoraba en silencio (los campos se escribian una sola vez) y "espera,
    en realidad no somos colombianos" re-emitia el precio en COP. No se aplica a
    ciegas ni se ignora (owner): con un cue explicito de correccion se acepta
    (`intent.overwrite`); sin el, queda en `pending_correction` y se confirma con el
    cliente. Ni la jerga ni el cue deciden si hay contradiccion: la decide comparar
    el valor con el guardado."""

    known = _known_field_values(state)
    cue = _has_correction_cue(state, message)
    for field, value in proposed.items():
        old = known.get(field)
        if value in (None, [], {}) or old in (None, [], {}) or value == old:
            continue
        # u3-5 (26-sep): el "¿lo cambio?" fantasma. En un turno con pregunta, al revisar los datos
        # ya guardados el LLM re-deduce desde el historial y propone un cambio que el mensaje no
        # dice ("listo, como pago" -> "¿lo cambio? con certificación -> sin certificación", ronda
        # B2). Si Jev dice que el cliente no afirma nada de ese campo, no hay contradicción que
        # confirmar: se queda lo guardado.
        if _jev_says_not_affirmed(state, field):
            logger.info(f"[CORE] contradiccion descartada {field}: {old!r} -> {value!r} (Jev: no lo afirma)")
            continue
        # u3-5 paso 1a: un cambio que se lee igual para el cliente no es un cambio ("1 buceo
        # certificado, 1 snorkel -> 1 buceo certificado, 1 snorkel", ronda A del paso 3).
        if _same_for_customer(field, value, old, state.language or "es"):
            logger.info(f"[CORE] contradiccion descartada {field}: mismo valor para el cliente")
            continue
        # u3-5 paso 1b: lo ya preguntado y no confirmado no se vuelve a preguntar (el LLM lo
        # re-deducia del historial en cada turno: 6 de los 12 "¿lo cambio?" de la ronda A).
        if (state.asked_corrections or {}).get(field) == value:
            logger.info(f"[CORE] contradiccion descartada {field}: ya preguntada y no confirmada")
            continue
        if cue:
            setattr(intent, field, value)
            if field not in intent.overwrite:
                intent.overwrite.append(field)
            if field not in intent.detected_fields:
                intent.detected_fields.append(field)
            logger.info(f"[CORE] correccion aceptada (cue) {field}: {old!r} -> {value!r}")
            continue
        state.pending_correction = {**(state.pending_correction or {}), field: value}
        state.asked_corrections = {**(state.asked_corrections or {}), field: value}
        setattr(intent, field, None)
        if field in intent.detected_fields:
            intent.detected_fields.remove(field)
        logger.info(f"[CORE] contradiccion sin cue {field}: {old!r} -> {value!r}, se confirma")


_CAMPOS_LUGAR = ("location", "island", "hotel")
_CAMPOS_ACTIVIDAD = ("activity", "service_id", "is_colombian")
_CAMPOS_CERTIFICACION = ("is_certified", "last_dive_over_2_years")
_CAMPOS_GRUPO = ("group_size", "group_allocation")


def campos_del_extractor() -> tuple[str, ...]:
    """Campos que decide el extractor "LLM primero" (fase EX) en vez del regex: ex-5 la ubicación; ex-8 la actividad
    (con su servicio) y la nacionalidad; ex-6 la certificación; ex-7 el grupo y su reparto. ex-9 (15-oct): los cuatro
    dominios ya no tienen flag (promocionados del 1 al 13-oct)."""
    return _CAMPOS_LUGAR + _CAMPOS_ACTIVIDAD + _CAMPOS_CERTIFICACION + _CAMPOS_GRUPO


# ex-9b paso 3: de los campos que decide el extractor, el regex solo deja como "pista" (`_pista_del_regex`) la isla y el
# hotel, que salen de la lista cerrada del catálogo (clase d del estudio ex-9): no son una lectura de la frase, y su
# relevo es de los pasos 4 y 6 de ex-9b. La actividad, el origen, la certificación, el grupo, la nacionalidad y la
# última inmersión los decide solo el extractor; si falla, la reserva los pregunta.
_CAMPOS_LISTA_CERRADA = ("island", "hotel")


def _conservar_hotel(intent, pista: dict) -> None:
    """El hotel y la isla que leyó el regex (lista cerrada) se quedan cuando el cliente está en las islas."""
    for campo in ("island", "hotel"):
        if pista.get(campo):
            setattr(intent, campo, pista[campo])
            if campo not in intent.detected_fields:
                intent.detected_fields.append(campo)


def _quitar_provisional(intent, pista: dict) -> None:
    """Saca del intent lo provisional del regex (los campos del extractor) antes de poner lo del extractor."""
    for campo in campos_del_extractor():
        setattr(intent, campo, None)
    intent.detected_fields = [f for f in intent.detected_fields if f not in campos_del_extractor()]
    intent.overwrite = [f for f in intent.overwrite if f not in campos_del_extractor()]


def _pasa_la_puerta_de_hoy(state: ConversationState, campo: str) -> bool:
    """Si el extractor falla, lo del regex vale con la puerta de siempre: en un turno con pregunta (u3-4) solo si Jev dice
    que el cliente lo afirma; en cualquier turno, nunca si Jev dice que NO lo afirma."""
    afirma = (getattr(state, "_answer_affirms", None) or {}).get(campo)
    return not ((_has_pending_answer(state) and afirma is not True) or _jev_says_not_affirmed(state, campo))


async def _aplicar_extractor(intent, state: ConversationState, message: str, pista: dict) -> None:
    """Fase EX: los campos de los dominios encendidos los pone el extractor "LLM primero" (cita comprobada), en vez de
    lo provisional del regex. Va ANTES de las reglas que trabajan sobre el intent (reparto, cert-o-curso, recomendar el
    minicurso), para que vean el valor final. Si la llamada falla, lo de hoy con su puerta, campo a campo."""
    datos = await datos_del_extractor(state, message)
    # ex-9b paso 4: ¿leyó el extractor el mensaje? ("voy solo" lo decide el extractor si leyó).
    intent._leido_por_extractor = datos is not None
    state.extractor_fallos_seguidos = 0 if datos is not None else (state.extractor_fallos_seguidos or 0) + 1
    await _otro_idioma_en_ingles(state, datos, message)
    _quitar_provisional(intent, pista)
    _nombre_del_extractor(state, datos, message)
    if datos is None:
        _el_extractor_no_leyo(state)
        # ex-9b paso 3 (decisión de Gadea): sin extractor no se vuelve al regex; lo que falte se pregunta. La pista solo
        # trae la isla y el hotel del catálogo (`_CAMPOS_LISTA_CERRADA`), con la puerta de siempre del origen.
        logger.info("[EXTRACT][EX9B-3] el extractor falló: sin pista del regex, la reserva pregunta lo que falte")
        for campo in _CAMPOS_LISTA_CERRADA:
            if campo not in pista:
                continue
            if not _pasa_la_puerta_de_hoy(state, "location"):
                logger.info(f"[EXTRACT][EX] el extractor falló y la puerta no deja {campo}={pista[campo]!r}")
                continue
            setattr(intent, campo, pista[campo])
            if campo not in intent.detected_fields:
                intent.detected_fields.append(campo)
        return
    _poner_ubicacion(intent, state, message, datos, pista)
    _poner_hotel(intent, state, datos)
    _poner_refresher(state, datos)
    # ex-7: el grupo antes que la actividad: la regla de ex-8 del grupo repartido mira el reparto del turno.
    _poner_grupo(intent, state, message, datos)
    # ex-9b paso 4: "voy solo" / "just me" es el grupo de 1 que lee el extractor con su cita ("voy solo" = 1); el regex
    # del detector (`solo_confirmed`: "para mí", "soy buzo certificado"…) solo cuenta si el extractor falla.
    intent.solo_confirmed = intent.group_size == 1 and "group_size" in intent.detected_fields
    if datos.get("quiere_bucear") is True:
        state.quiere_bucear = True
    _poner_actividad(intent, state, datos, message)
    _poner_nacionalidad(intent, state, message, datos)
    _poner_certificacion(intent, state, message, datos)
    _poner_duracion(intent, state, datos, message)
    _poner_edades(intent, datos)
    _poner_otras_personas(state, datos)
    _poner_actividad_preguntada(state, datos)
    intent._actividad_preguntada = datos.get("actividad_preguntada")  # la de ESTE mensaje (flu-1, `_flag_cert_or_course`)


def duracion_del_extractor(datos: dict | None, state: ConversationState) -> tuple[str | None, bool]:
    """ex-9b paso 6 (`duracion_por_extractor`): (single_day / multi_day, ¿son días de BUCEO?) según lo que dice el
    cliente. Manda lo que dice que quiere bucear; si solo dice su estancia, la estancia, salvo que ya se sepa cuántos días
    quiere bucear (decisión de Gadea, 19-oct). (None, False) si no dice nada de días que cambie lo sabido."""
    dias_buceo, dias_estancia = (datos or {}).get("dias_de_buceo"), (datos or {}).get("dias_de_estancia")
    if isinstance(dias_buceo, int) and dias_buceo > 0:
        return ("multi_day" if dias_buceo > 1 else "single_day"), True
    if isinstance(dias_estancia, int) and dias_estancia > 0 and not state.duracion_de_buceo:
        return ("multi_day" if dias_estancia > 1 else "single_day"), False
    return None, False


def _paquete_de_varios_dias_nombrado(message: str) -> bool:
    """¿Nombra el mensaje un paquete del catálogo que dura varios días ("el paquete de 5 buceos")? La cifra y la unidad
    las lee `dive_counts_in` (clase D del estudio: cifra + unidad del catálogo) y los días son los del catálogo. Sustituye
    a `_MULTI_DAY_PRODUCT_RE`, que daba varios días con la palabra "paquete" sola ("alguien que hizo el paquete con
    ustedes", "¿tienen algo como un paquete?")."""
    from src.agents.intent_detector import dive_counts_in  # lazy

    paquetes = dom.dive_packages()
    return any(paquetes[n][0] > 1 for n in dive_counts_in(message))


def _poner_duracion(intent, state: ConversationState, datos: dict, message: str = "") -> None:
    """ex-9b paso 6: la duración es la que dice el extractor con su cita; lo que leía el regex
    (`_detect_duration`, que tomaba "embarazada de 4 meses" por varios días) no cuenta. Lo que el cliente dice ahora
    cambia lo guardado (los días de buceo siempre; la estancia, si no se sabía cuántos días quiere bucear). Si no dice
    días pero nombra un paquete de varios días del catálogo, varios días (como hoy; un plan de un día no se deduce)."""
    regex = intent.duration
    intent.duration = None
    intent.detected_fields = [f for f in intent.detected_fields if f != "duration"]
    duracion, de_buceo = duracion_del_extractor(datos, state)
    if duracion is None and not state.detected_duration and _paquete_de_varios_dias_nombrado(message):
        duracion = "multi_day"
        from src.observability import marca_regex  # lazy

        marca_regex("R10")  # CALN-8 (6): paquete de varios días nombrado, por el detector
        logger.info("[EXTRACT][EX9B-6] sin días dichos, pero nombra un paquete de varios días del catálogo")
    if duracion is None and (datos or {}).get("paquete_varios_dias") is True:
        # arq-1t: «el paquete de varios días», sin cifra (el extractor lo dice con su cita).
        duracion, de_buceo = "multi_day", True
        logger.info("[EXTRACT][ARQ1T] pide un paquete de varios días sin decir cuántos")
    if duracion is None:
        if regex:
            logger.info(f"[EXTRACT][EX9B-6] el regex leía duration={regex!r}; el cliente no lo dice")
        return
    intent.duration = duracion
    intent._duracion_de_buceo = de_buceo
    intent.detected_fields.append("duration")
    if duracion != state.detected_duration and "duration" not in intent.overwrite:
        intent.overwrite.append("duration")
    logger.info(f"[EXTRACT][EX9B-6] duration={duracion!r} ({'días de buceo' if de_buceo else 'estancia'}; regex: {regex!r})")


def _poner_edades(intent, datos: dict) -> None:
    """ex-9b paso 6: las edades son las del extractor (con la cifra validada en su cita); las del regex no cuentan si el
    extractor leyó el mensaje."""
    regex = list(intent.ages or [])
    edades = [a for a in ((datos or {}).get("edades") or []) if isinstance(a, int) and 1 <= a <= 99]
    intent.ages = sorted(set(edades))
    intent.detected_fields = [f for f in intent.detected_fields if f != "ages"] + (["ages"] if edades else [])
    if edades or regex:
        logger.info(f"[EXTRACT][EX9B-6] ages={intent.ages} (regex: {regex})")


def _el_extractor_no_leyo(state: ConversationState) -> None:
    """ex-9b paso 6: un mensaje de la conversación se queda sin leer por el extractor; las notas del RAG sobre otras
    personas vuelven al regex de siempre (`rutas/contexto_rag`), como hoy."""
    if not state.extractor_ha_fallado:
        state.extractor_ha_fallado = True
        logger.info("[EXTRACT][EX9B-6] el extractor no leyó un mensaje: las notas del RAG vuelven al regex")


def _poner_otras_personas(state: ConversationState, datos: dict) -> None:
    """ex-9b paso 6: lo que el cliente dice de OTRA persona del grupo (no certificada; o certificada pero inactiva) se
    guarda para las notas de reglas del RAG. Una vez dicho, se queda."""
    if (datos or {}).get("otro_sin_certificar") is True and not state.acompanante_sin_certificar:
        state.acompanante_sin_certificar = True
        logger.info("[EXTRACT][EX9B-6] otra persona del grupo no está certificada")
    if (datos or {}).get("otro_certificado_inactivo") is True and not state.acompanante_certificado_inactivo:
        state.acompanante_certificado_inactivo = True
        logger.info("[EXTRACT][EX9B-6] otra persona del grupo está certificada pero inactiva")
    if isinstance((datos or {}).get("sin_decidir_certificados"), bool):
        # CALN-2 (flag `lector_grupo`): lo que dice el lector del grupo de quienes faltan por elegir; lo último manda.
        state.sin_decidir_certificados = datos["sin_decidir_certificados"]
    if (datos or {}).get("otros_sin_elegir") and not state.needs_companion_activity:
        # CALN-8 (g26): vienen otros sin decir cuántos ni qué harán: se pregunta qué harán (y después, cuántos).
        state.needs_companion_activity = True
        logger.info("[EXTRACT][CALN8] vienen otros sin decir cuántos ni qué harán: se pregunta qué harán")


def _poner_actividad_preguntada(state: ConversationState, datos: dict) -> None:
    """gen-8: la actividad concreta de la que el cliente pregunta sin elegirla. Se queda la última: "¿y cuánto dura?"
    no nombra ninguna y sigue hablando de la misma."""
    actividad = (datos or {}).get("actividad_preguntada")
    if actividad and actividad != state.actividad_preguntada:
        state.actividad_preguntada = actividad
        logger.info(f"[EXTRACT][GEN8] pregunta por {actividad!r} sin elegirla")


def _reparto_guardado(state: ConversationState) -> dict:
    """El reparto que ya sabe la conversación: el guardado o, si solo hay una actividad y un total, esa actividad para
    todos ("buceo certificado, somos 3" = {certified_diving: 3})."""
    if state.detected_group_allocation:
        return {k: v for k, v in state.detected_group_allocation.items() if isinstance(v, int) and v > 0}
    if state.detected_activity and state.detected_group_size:
        return {state.detected_activity: state.detected_group_size}
    return {}


def _suma_a_un_grupo_sin_actividad(state: ConversationState, reparto: dict, total) -> str | None:
    """DEUDA-EXT: ¿el reparto del extractor suma personas a un grupo ya contado que aún no tiene actividad?
    - "todos": el reparto ya trae a los de antes con una actividad ({certified_diving: 3, minicourse: 2}, total 5): vale
      entero, como un reparto que amplía el de antes;
    - "nuevos": trae solo a los que se suman ({minicourse: 2}, total 3 + 2) o a los de antes sin decidir
      ({minicourse: 2, undecided: 3}): los nuevos van por el punto único del acompañante;
    - None: no es una suma (el total no cuadra y Jev no está seguro de que se sume alguien)."""
    sabido = _known_field_values(state).get("group_size")
    if not sabido or state.detected_activity or state.detected_group_allocation or _jev_dice_que_nadie_se_suma(state):
        return None
    suma = sum(v for v in reparto.values() if isinstance(v, int) and v > 0)
    sin_decidir = reparto.get("undecided") or 0
    cuadra = total is None or total == suma
    if sin_decidir >= sabido and cuadra and suma > sabido:
        return "nuevos"
    if len(reparto) > 1 and cuadra and suma > sabido and any(
            n == sabido for a, n in reparto.items() if a != "undecided"):
        return "todos"
    if isinstance(total, int):
        # Los sin decidir del extractor son (parte de) los de antes: {minicourse: 2, undecided: 1} con total 5 sobre 3
        # (banco-lat11 a4, 3 de 3: el extractor cuenta a quien escribe y no a su grupo). Cuadra el total con los nuevos.
        return "nuevos" if sin_decidir <= sabido and total == sabido + suma - sin_decidir else None
    from src.agents.nucleo.extraction import _JEV_SE_SUMA_SEGURO  # lazy

    jev = getattr(state, "_jev_adds_person", None)
    return "nuevos" if jev is not None and jev >= _JEV_SE_SUMA_SEGURO else None


def _amplia(nuevo: dict, antes: dict) -> bool:
    """¿El reparto nuevo solo SUMA personas al de antes (nadie de antes cambia de actividad)?"""
    return bool(antes) and all(nuevo.get(act, 0) >= n for act, n in antes.items()) and nuevo != antes


def _jev_dice_que_nadie_se_suma(state: ConversationState) -> bool:
    """ex-9b paso 6 (con `jev_persona_ya_contada`): ¿Jev está SEGURO de que el mensaje no suma a una persona nueva
    (adds_person < ADDS_PERSON_NOT_MAX, la puerta de s4-26)? Ausente = no lo sabemos."""
    from src.agents.jev_router import ADDS_PERSON_NOT_MAX  # lazy

    p = getattr(state, "_jev_adds_person", None)
    return p is not None and p < ADDS_PERSON_NOT_MAX


# Clave del reparto -> categoría de `intent_detector.matched_activity_categories` (la lista cerrada de nombres).
_CATEGORIA_DEL_REPARTO = {"minicourse": "minicourse", "bubble_makers": "minicourse", "snorkel": "snorkel",
                         "padi_specialty": "specialty"}


def _reparto_valido(reparto: dict | None, message: str, state: ConversationState, minimo: int = 2) -> dict | None:
    """Lo que el código comprueba del reparto del extractor antes de usarlo (fase EX: el código valida):
    (1) una cifra de más de una persona tiene que estar en el mensaje o saberse ya: "yo buceo y mis amigos hacen
        snorkel" no dice cuántos, así que no hay reparto y el bot lo pregunta (banco ex7: inventaba 2);
    (2) una actividad que el mensaje no nombra (minicurso, snorkel o un curso; el buceo certificado lo dicen la
        certificación y "buzo") no se le pone a nadie: esas personas quedan sin decidir (decisión del owner, 15-sep:
        "mi amigo no es buzo, yo sí" no es un minicurso ni un snorkel; banco ex7 los inventaba)."""
    from src.agents.intent_detector import matched_activity_categories  # lazy

    if not reparto:
        return None
    # CALN-S30A-01: cuántos faltaban por elegir también se sabe («mis hijos y yo hacemos el minicurso» con 3 sin elegir),
    # y los que ya tenían esa actividad no se inventan aunque el mensaje no la nombre (el reparto que completa el lector).
    guardado = _reparto_guardado(state)
    conocidas = set(guardado.values()) | {state.detected_group_size, state.pending_undecided_qty}
    if not _EXPLICIT_NUMBER_RE.search(message) and any(n > 1 and n not in conocidas for n in reparto.values()):
        logger.info(f"[EXTRACT][EX7] reparto sin cifras en el mensaje, no se usa: {reparto!r}")
        return None
    nombradas = matched_activity_categories(message)
    valido: dict = {}
    for act, n in reparto.items():
        categoria = "padi_course" if act.startswith("padi_") and act != "padi_specialty" else _CATEGORIA_DEL_REPARTO.get(act)
        # CALN-2 (27-oct, tanda de precios q2 t2): también por sus nombres del catálogo, en los dos idiomas
        # («she the mini course»; los patrones de categoría no tenían el nombre en inglés del propio producto).
        nombrada = (categoria is None or categoria in nombradas or act == state.detected_activity
                    or dom.nombra_el_producto(act, message) or n <= guardado.get(act, 0))
        clave = act if nombrada else "undecided"
        if not nombrada:
            from src.observability import marca_regex  # lazy

            marca_regex("R8")  # CALN-8 (6): el detector no ve la actividad del reparto en el mensaje
            logger.info(f"[EXTRACT][EX7] {act!r} no se nombra en el mensaje: {n} sin decidir")
        valido[clave] = valido.get(clave, 0) + n
    return valido if len(valido) >= minimo else None


def _poner_grupo(intent, state: ConversationState, message: str, datos: dict) -> None:
    """ex-7: cuántos van y cómo se reparten, según el extractor (cita del cliente); el regex no cuenta ("soy buza
    advanced" no dice que vaya sola). Un reparto que AMPLÍA el que ya se sabía (se suman personas,
    nadie cambia de actividad: "3 of us will dive and 3 will snorkel" sobre {buceo: 3}) es un añadido: se guarda con su
    total sin preguntar. Cualquier otro cambio del total o del reparto se confirma, como hoy (`_route_contradictions`),
    salvo con una señal clara de corrección ("perdón, en realidad son 3 y 3"): el dato trae su cita comprobada en el
    mensaje y se cambia (banco ex7: el "¿lo afirma?" de Jev descartaba la corrección). El atajo de acompañante de
    `_understand` no vuelve a sumar a quien el extractor ya puso en el reparto."""
    guardado = _known_field_values(state)
    corrige = _has_correction_cue(state, message)
    reparto, total = _reparto_valido(datos.get("group_allocation"), message, state), datos.get("group_size")
    if total is not None and not reparto and state.core_pending_slot == SLOT_COMPANION_QTY:
        # lat-11 T6b (26-oct): con «¿Cuántos serían para X?» pendiente, la cifra sola («3 personas», «son 2») contesta
        # esa pregunta, no el total del grupo: la reparte la red de acompañantes (el resolutor). El extractor la tomaba
        # por el total y se sumaba dos veces (banco-lat11-t6b, c1: «3 personas» -> 3 buzos + 3 snorkel; c2 «son 2» igual
        # también antes, cuando el atajo del detector entero no la leía).
        logger.info(f"[EXTRACT][LAT11] group_size={total!r} contesta «¿cuántos para X?»: no es el total del grupo")
        total = None
    # Con una corrección («no, ella hace snorkel») el reparto cambia lo elegido y no es completar; pero si conserva a
    # todos los que ya habían elegido y solo da actividad a quien faltaba (`grupo.completa`), sí lo es aunque empiece por
    # «No wait…» (sparring s03 con el lector del grupo: «he wants the fun dives… only I'm doing the mini course» se
    # tiraba por el veto de Jev de abajo y él seguía sin elegir).
    completa = bool(reparto) and grupo.completa(state.detected_group_allocation, reparto, state.detected_group_size)
    junto = (grupo.completado(state.detected_group_allocation, reparto, state.detected_group_size)
             if reparto and state.pending_undecided_qty and (not corrige or completa) else None)
    if junto:
        # CALN-2 (27-oct): el reparto solo da actividad a quienes faltaban por elegir y cabe en el total: no se suma
        # nadie (Jev acierta si dice que ya estaban contados), se completa el grupo. Familia de 5 con 4 pendientes:
        # «mi marido quiere bucear, yo y la de 14 el minicurso» se tiraba entero por el veto de Jev de abajo, o se
        # pedía confirmar el «cambio» porque no nombraba al suegro (sparring contra la rama, 27-oct). El total no
        # cambia; quien quede sin elegir sigue pendiente.
        decididos = junto
        resto = state.detected_group_size - sum(decididos.values())
        intent.group_allocation = {**decididos, **({grupo.SIN_DECIDIR: resto} if resto else {})}
        intent._reparto_del_extractor = set(reparto)
        for listado in (intent.detected_fields, intent.overwrite):
            if "group_allocation" not in listado:
                listado.append("group_allocation")
        logger.info(f"[EXTRACT][CALN2] el reparto {decididos!r} completa a los que faltaban por elegir ({resto} sin elegir)")
        return
    if reparto and _amplia(reparto, _reparto_guardado(state)) and _jev_dice_que_nadie_se_suma(state):
        # ex-9b paso 6 (`reparto_al_sumarse_alguien`): el extractor suma a alguien y Jev está seguro de que el mensaje
        # habla de alguien ya contado (s4-26, `adds_person`). Dos lectores en contra: no se suma a nadie aquí; lo decide
        # la red de acompañantes con la regla de s4-26 (moverlo en vez de añadirlo).
        logger.info(f"[EXTRACT][EX9B-6] el extractor amplía el reparto {reparto!r}, pero Jev dice que ya estaba contado")
        reparto, total = None, None
    antes_del_turno = _reparto_guardado(state)
    # DEUDA-EXT: los que se suman pueden ser de UNA sola actividad ({minicourse: 2}): el reparto normal pide dos.
    nuevos = reparto or _reparto_valido(datos.get("group_allocation"), message, state, minimo=1)
    suma_sin_actividad = (_suma_a_un_grupo_sin_actividad(state, nuevos, total)
                          if nuevos and not antes_del_turno and not corrige else None)
    if suma_sin_actividad == "todos":
        # DEUDA-EXT (26-oct): el extractor trae el grupo entero, los de antes ya con actividad: se guarda sin preguntar.
        suma = sum(v for v in nuevos.values() if isinstance(v, int) and v > 0)
        intent.group_allocation, intent.group_size = dict(nuevos), suma
        intent._reparto_del_extractor = set(nuevos)
        for campo in _CAMPOS_GRUPO:
            for listado in (intent.detected_fields, intent.overwrite):
                if campo not in listado:
                    listado.append(campo)
        logger.info(f"[EXTRACT][DEUDA-EXT] el reparto {nuevos!r} suma al grupo de {guardado['group_size']} (total {suma})")
        return
    if suma_sin_actividad == "nuevos":
        # DEUDA-EXT (26-oct): "Somos 3 buzos certificados" (sin actividad) + "además vienen dos amigos que quieren probar
        # el minicurso": el extractor trae {minicourse: 2} y total 5, pero sin reparto de antes no se veía la suma y se
        # pedía confirmar "3 → 5" (banco-lat11 a4). Los que se suman van por el punto único del acompañante; los de
        # antes esperan a la principal.
        from src.agents.nucleo.extraction import _add_or_ask_companion  # lazy

        intent._reparto_del_extractor = set(nuevos)
        decididos = {a: n for a, n in nuevos.items() if a != "undecided" and isinstance(n, int) and n > 0}  # los nuevos
        logger.info(f"[EXTRACT][DEUDA-EXT] se suman {decididos!r} al grupo de {guardado['group_size']} sin actividad")
        for actividad, cuantos in decididos.items():
            _add_or_ask_companion(state, message, actividad, cuantos)
        return
    if reparto and _amplia(reparto, antes_del_turno) and not corrige:
        # ex-9b (19-oct, punto 2 de Gadea): el extractor suma gente de UNA actividad al grupo ya sabido. Sumarla sin
        # más contaba dos veces a alguien ya contado cuando Jev dudaba ("mi amigo, el que ya te dije que viene, quiere
        # snorkel": adds_person 0,30). Va por el punto único de siempre (`_add_or_ask_companion`): si el mensaje dice
        # que se suma alguien, se añade; si Jev está seguro de que ya estaba contado, se mueve; si no, se pregunta el
        # total (una vez). Un reparto que suma varias actividades a la vez sigue como antes.
        nuevos = {a: n - antes_del_turno.get(a, 0) for a, n in reparto.items() if n - antes_del_turno.get(a, 0) > 0}
        if len(nuevos) == 1:
            from src.agents.nucleo.extraction import _add_or_ask_companion  # lazy

            (actividad, cuantos), = nuevos.items()
            logger.info(f"[EXTRACT][EX9B-6] el extractor suma {cuantos} de {actividad!r} al grupo sabido "
                        f"{antes_del_turno!r}: decide el punto único del acompañante")
            intent._reparto_del_extractor = set(reparto)
            _add_or_ask_companion(state, message, actividad, cuantos)
            return
    if reparto:
        suma = sum(v for v in reparto.values() if isinstance(v, int) and v > 0)
        antes = _reparto_guardado(state)
        intent._reparto_del_extractor = set(reparto)
        if _amplia(reparto, antes):
            intent.group_allocation, intent.group_size = dict(reparto), suma
            for campo in _CAMPOS_GRUPO:
                for listado in (intent.detected_fields, intent.overwrite):
                    if campo not in listado:
                        listado.append(campo)
            logger.info(f"[EXTRACT][EX7] el reparto amplía el de antes {antes!r} -> {reparto!r} (total {suma})")
            return
        if guardado.get("group_allocation") and guardado["group_allocation"] != reparto and not corrige:
            logger.info(f"[EXTRACT][EX7] el cliente cambia el reparto {guardado['group_allocation']!r} -> {reparto!r}")
            _route_contradictions(state, message, intent, {"group_allocation": reparto})
        elif guardado.get("group_allocation") and guardado["group_allocation"] != reparto:
            logger.info(f"[EXTRACT][EX7] corrección del reparto {guardado['group_allocation']!r} -> {reparto!r}")
            intent.group_allocation = dict(reparto)
            for listado in (intent.detected_fields, intent.overwrite):
                if "group_allocation" not in listado:
                    listado.append("group_allocation")
        else:
            intent.group_allocation = dict(reparto)
            if "group_allocation" not in intent.detected_fields:
                intent.detected_fields.append("group_allocation")
        total = total if isinstance(total, int) and total >= suma else suma
    if total is None:
        return
    if guardado.get("group_size") is not None and guardado["group_size"] != total and not corrige:
        logger.info(f"[EXTRACT][EX7] el cliente cambia el total {guardado['group_size']!r} -> {total!r}: se confirma")
        _route_contradictions(state, message, intent, {"group_size": total})
        return
    intent.group_size = total
    if "group_size" not in intent.detected_fields:
        intent.detected_fields.append("group_size")
    if corrige and guardado.get("group_size") not in (None, total) and "group_size" not in intent.overwrite:
        intent.overwrite.append("group_size")
    logger.info(f"[EXTRACT][EX7] group_size={total!r}")


def _poner_certificacion(intent, state: ConversationState, message: str, datos: dict) -> None:
    """ex-6: si ya es buzo certificado y si su última inmersión fue hace más de 2 años, según el extractor (cita del
    cliente); el regex no cuenta ("take the Open Water Diver course" no es estar certificado). Un valor distinto del
    guardado se confirma, como hoy."""
    for campo in _CAMPOS_CERTIFICACION:
        valor = datos.get(campo)
        if valor is None:
            continue
        intent._certificacion_del_extractor = True
        guardado = _known_field_values(state).get(campo)
        if guardado is not None and guardado != valor:
            logger.info(f"[EXTRACT][EX6] el cliente cambia {campo} {guardado!r} -> {valor!r}: se confirma")
            _route_contradictions(state, message, intent, {campo: valor})
            continue
        setattr(intent, campo, valor)
        if campo not in intent.detected_fields:
            intent.detected_fields.append(campo)
        logger.info(f"[EXTRACT][EX6] {campo}={valor!r}")


_LUGAR_DE_JEV = {"cartagena": "cartagena", "islands": "island"}


def origen_por_confirmar(state: ConversationState, datos: dict | None = None) -> str | None:
    """CALN-3b (28-oct, decisión de Gadea #2286, en la línea de ORIGEN-CONFIRMA): el origen que se confirma una vez
    («Entonces, ¿saldrías desde Cartagena?») en vez de la pregunta abierta, o None. Ya pendiente de confirmar, ese; si
    no, cuando el extractor leyó ESTE mensaje sin lugar, no hay origen guardado y Jev elige un lugar, aunque sea con poca
    confianza: «vamos a estar en Isla Barú, en un hotel de playa» (extractor callado 3/3, Jev cartagena 0,27-0,35) o el
    mensaje largo de b5 con «Estamos alojados en Cartagena» (extractor 14/20, Jev 1,0). Sin lugar en el mensaje, Jev
    dice none con 0,95 o más (sonda de 12 mensajes ×4): no se confirma un origen que el cliente no dio. El origen no se
    da por sabido (DEUDA-ORIGEN): van los dos precios hasta que conteste."""
    pendiente = (state.pending_correction or {}).get("location")
    if pendiente in _LUGAR_DE_JEV.values():
        return pendiente
    if state.location or state.detected_location:
        return None
    if datos is None:
        from src.agents.conversational_core import _el_extractor_calla_el_lugar  # lazy

        if not _el_extractor_calla_el_lugar(state):  # aún sin leer, falló o dice un lugar
            return None
    elif datos.get("location"):
        return None
    origen = _LUGAR_DE_JEV.get((getattr(state, "_jev_lugar", None) or {}).get("choice"))
    if not origen or (state.asked_corrections or {}).get("location") == origen:
        return None
    return origen


def _poner_ubicacion(intent, state: ConversationState, message: str, datos: dict, pista: dict) -> None:
    """ex-5: la ubicación es la del extractor (cita que nombra un lugar). Si se aloja en las islas, el hotel y la isla del
    regex (lista cerrada) se conservan para la recogida. Un origen distinto del guardado se confirma."""
    lugar = datos.get("location")
    guardado = state.location or state.detected_location
    if not lugar:
        if guardado == "island":
            # Ya se sabe que está en las islas y no lo repite: el hotel o la isla que nombra (lista cerrada) sirven para
            # la recogida (ronda ex5-B2: "una noche en Coral Sand y la otra en Majagua" se perdía y se repreguntaba).
            _conservar_hotel(intent, pista)
        elif (por_confirmar := origen_por_confirmar(state, datos)) and not (state.pending_correction or {}).get("location"):
            state.pending_correction = {**(state.pending_correction or {}), "location": por_confirmar}
            state.asked_corrections = {**(state.asked_corrections or {}), "location": por_confirmar}
            logger.info(f"[EXTRACT][CALN3B] el extractor calla el lugar y Jev se inclina por {por_confirmar!r}: se "
                        "confirma")
        return
    if _jev_dice_que_no_lo_dice(state):
        # CAL-C3c (17-oct): "bucear el lunes festivo en islas del rosario" → el extractor ponía island 3 de 3 (su regla
        # dice que nombrar las islas como sitio de buceo no basta, y no la sigue) y el bot cotizaba solo "ya en las
        # islas" (cal-71/73). El origen decide precio y enlace: se guarda solo si los dos lectores no se contradicen.
        # Jev seguro de que el mensaje NO dice dónde está → el origen queda sin saber y la reserva lo pregunta.
        logger.info(f"[EXTRACT][CAL-C3c] el extractor dice location={lugar!r} y Jev, seguro, que el mensaje no lo "
                    "dice: no se guarda")
        if not guardado and (state.asked_corrections or {}).get("location") != lugar:
            # ORIGEN-CONFIRMA (27-oct, idea de Álvaro #2080, decisión de Gadea #2082): en vez de tirarlo y volver a
            # preguntar «¿desde dónde saldrías?» (lo que el cliente oye como no haberle escuchado: «Va quiero comprar
            # sin ir de cartagena» → la misma pregunta), se confirma UNA vez lo leído («Entonces, ¿ya estarás en las
            # islas?»). No se cotiza ese origen hasta que conteste; un «no» lo deja sin saber, como hasta hoy.
            state.pending_correction = {**(state.pending_correction or {}), "location": lugar}
            state.asked_corrections = {**(state.asked_corrections or {}), "location": lugar}
            logger.info(f"[EXTRACT][ORIGEN-CONFIRMA] se confirma location={lugar!r} antes de guardarlo")
        return
    if guardado and guardado != lugar:
        # Cambiar un origen ya guardado pasa por la confirmación de siempre (`_route_contradictions`): con una señal
        # clara de corrección ("al final…", "en realidad…") se cambia; si no, "¿lo cambio?"; si Jev dice que el
        # cliente no lo afirma, se queda. Ronda ex5-B: "Ok, están en Isla Grande" (la base, no el cliente) cambiaba
        # Cartagena por las islas en silencio.
        logger.info(f"[EXTRACT][EX5] el cliente cambia el origen {guardado!r} -> {lugar!r}: se confirma")
        _route_contradictions(state, message, intent, {"location": lugar})
        return
    intent.location = lugar
    if "location" not in intent.detected_fields:
        intent.detected_fields.append("location")
    if lugar == "island":
        _conservar_hotel(intent, pista)
    logger.info(f"[EXTRACT][EX5] location={lugar!r} (guardado: {guardado!r})")


def _hotel_del_catalogo(nombre: str) -> tuple[str, str | None] | None:
    """CAL-C3e: (hotel_id, isla) si el hotel que nombra el cliente está en el catálogo de hoteles de las islas que ya usa
    el detector (`detect_location`: 'ubuntu' → isla_marina…); None si no. Se le pasa SOLO el nombre
    (cita comprobada por el extractor), así que solo puede encontrar ese hotel, como `_departure_place`."""
    intent = DetectedIntent()
    detect_location((nombre or "").lower(), intent, nombra_un_hotel=True)
    return (intent.hotel, intent.island) if intent.hotel else None


def _poner_refresher(state: ConversationState, datos: dict) -> None:
    """CAL-F (18-oct): si el cliente dice que quiere (o no) el refresher, se guarda aunque
    el bot aún no se lo haya preguntado. Vale lo último que decide: "mejor no" y luego "en realidad sí lo quiero"."""
    valor = (datos or {}).get("refresher_interested")
    if not isinstance(valor, bool) or state.refresher_interested is valor:
        return
    state.refresher_interested = valor
    logger.info(f"[EXTRACT][CAL-F] refresher_interested={valor} (lo dice el cliente)")


def _poner_hotel(intent, state: ConversationState, datos: dict) -> None:
    """CAL-C3: el hotel que el cliente nombra (cita comprobada, sin lista cerrada) se guarda si
    la conversación aún no tiene uno, para no preguntarle "¿En qué hotel o isla te hospedas?" (cal-41, cal-67/68). El
    del regex (lista cerrada, con su isla) manda si lo hay: sirve para la recogida."""
    hotel = (datos or {}).get("hotel")
    if not hotel or intent.hotel or state.hotel or state.detected_hotel:
        return
    intent.hotel = hotel
    if "hotel" not in intent.detected_fields:
        intent.detected_fields.append("hotel")
    logger.info(f"[EXTRACT][CAL-C3] hotel={hotel!r} (nombrado por el cliente)")
    del_catalogo = _hotel_del_catalogo(hotel)
    if del_catalogo:
        intent.hotel, isla = del_catalogo
        if isla and not intent.island:
            intent.island = isla
            intent.detected_fields.append("island")
        if not intent.location and not (state.location or state.detected_location):
            intent.location = "island"
            intent.detected_fields.append("location")
        logger.info(f"[EXTRACT][CAL-C3e] {hotel!r} es del catálogo de las islas: {del_catalogo}")


def _principal_del_grupo_repartido(state: ConversationState, reparto: dict) -> str | None:
    """ex-9b paso 3 (19-oct, sin flag): la actividad principal de un grupo repartido, cuando el extractor no elige una
    ("somos 6: 2 bucean certificados, 2 hacen minicurso y 2 snorkel"). Es la regla de CAL-F
    (`actividad_principal_del_reparto`: el buceo certificado si alguien lo hace; si no, la parte más grande). Antes la
    ponía el regex con la primera de sus listas que casaba: el minicurso, aunque hubiera buzos certificados en el grupo; y
    "él quiere hacer snorkel" pasaba la principal de quien bucea al snorkel del acompañante. Una principal ya sabida que
    sigue en el reparto no se toca. Replay offline del estudio (95 diálogos): solo cambian 6, todos de grupo repartido."""
    from src.agents.extractor_turno import actividad_principal_del_reparto  # lazy

    if len(reparto) < 2 or state.detected_activity in reparto:
        return None
    sin_decidir = reparto.get("undecided") or 0
    if sin_decidir and sin_decidir >= sum(v for k, v in reparto.items() if k != "undecided" and isinstance(v, int)):
        # DEUDA-EXT2 (26-oct): «two certified divers» + «my wife will join us but she'll just snorkel» con el extractor
        # trayendo {snorkel: 1, undecided: 2} hacía principal el snorkel de la mujer y se cerraba la reserva como snorkel
        # (banco-lat11 a3). Si la parte más grande del grupo aún no ha decidido, la principal sigue pendiente.
        return None
    return actividad_principal_del_reparto(reparto)


def _paquete_de_buceos_sin_curso(message: str) -> bool:
    """LAT-0b: ¿el mensaje nombra un paquete de inmersiones del catálogo («el plan de 5 buceos») y ningún curso ni
    especialidad? La cifra con su unidad la lee `dive_counts_in`; los cursos, `courses_mentioned` y los sustantivos de la
    familia (`_product_family_nouns`: curso, especialidad…), las listas del catálogo de siempre. «Quiero un curso, ¿el
    de 4 inmersiones?» o «la especialidad de 3 buceos» siguen siendo un curso."""
    from src.agents.intent_detector import (  # lazy
        _product_family_nouns,
        courses_mentioned,
        dive_counts_in,
    )
    from src.utils.text import strip_accents  # lazy

    texto = message or ""
    palabras = set(re.findall(r"\w+", strip_accents(texto.lower())))
    familia = {strip_accents(n) for n in _product_family_nouns()}
    nombra_un_curso = bool(palabras & (familia | {n + "s" for n in familia} | {n + "es" for n in familia}))
    return bool(dive_counts_in(texto)) and not courses_mentioned(texto) and not nombra_un_curso


def _poner_actividad(intent, state: ConversationState, datos: dict, message: str = "") -> None:
    """ex-8: la actividad es la que el cliente ELIGE (extractor). La última elegida manda, como hoy. El servicio sale
    del registro. En un grupo repartido sin actividad elegida, la principal sale del reparto (ex-9b paso 3). No hay
    minicurso deducido del regex ("es mi primera vez"): la recomendación sale de lo que dice el extractor (CAL-C1,
    `actividad_por_lo_sabido`)."""
    actividad = datos.get("activity")
    certificado = datos.get("is_certified")
    if certificado is None:
        certificado = _known_field_values(state).get("is_certified")
    if actividad == "padi_open_water" and certificado is True:
        # DEUDA-EXT2 (26-oct): "PADI open water, advanced open water and deep diver certs" (contestando a "¿cuántas
        # personas?") daba el curso Open Water a quien ya lo tiene, y el redactor de hechos le cotizaba el curso (banco
        # de lat-5). Quien ya está certificado no se saca el Open Water: no es una elección de actividad.
        logger.info("[EXTRACT][DEUDA-EXT2] padi_open_water con is_certified true: no es el curso, se ignora")
        actividad = None
    if actividad in ("padi_course", "padi_specialty") and _paquete_de_buceos_sin_curso(message):
        # LAT-0b (26-oct): «¿Tienes disponibilidad para el plan de 5 buceos…?» daba padi_course (la regla del extractor
        # dice que un paquete de N buceos es certified_diving) y el bot preguntaba «¿qué curso?» en bucle (integra5-B,
        # paquete-5-buceos-islas-residente-sin-recogida, 6 turnos). Un paquete de buceos sin ningún curso nombrado es
        # buceo certificado.
        logger.info(f"[EXTRACT][LAT-0b] {actividad!r} con un paquete de buceos y sin curso nombrado: certified_diving")
        from src.observability import marca_regex  # lazy

        marca_regex("R9")  # CALN-8 (6): paquete de buceos sin curso, por el detector
        actividad = "certified_diving"
    ya_repartida = actividad in (state.detected_group_allocation or {})
    if (actividad and not datos.get("group_allocation") and state.core_pending_slot == SLOT_COMPANION_ACTIVITY
            and (state.pending_undecided_qty or ya_repartida) and state.detected_activity
            and actividad != state.detected_activity and actividad in _companion_activity_options(state)):
        # CALN-2 (27-oct, tanda de precios q2 t3): el bot preguntó qué quiere hacer quien no ha elegido y el cliente lo
        # dice («I told you, she wants the mini course»): es la elección de esa persona, no un cambio de la actividad de
        # quien escribe (el reparto {buceo 1} pasaba a {minicurso 1}, se perdía al buzo y se volvía a preguntar). Igual
        # que el botón de esa pregunta: queda para fusionarse con los que no habían elegido. Si la respuesta corta ya la
        # repartió en este turno (no queda nadie sin elegir y está en el reparto), no se cuenta otra vez.
        if state.pending_undecided_qty and not state.pending_companion_activity:
            _elige_quien_falta(state, actividad)
        logger.info(f"[EXTRACT][CALN2] {actividad!r} contesta qué hará quien no había elegido; la principal sigue")
        return
    if actividad and dom.by_id(actividad) is not None:
        intent.activity = actividad
        intent.service_id = dom.base_service_id(actividad)
        intent._actividad_elegida = True
        if "activity" not in intent.detected_fields:
            intent.detected_fields.append("activity")
        logger.info(f"[EXTRACT][EX8] activity={actividad!r}")
        return
    # Grupo repartido: el extractor no pone una actividad principal (ronda ex8-B: se repreguntaba). Sale del reparto.
    principal = _principal_del_grupo_repartido(state, intent.group_allocation or state.detected_group_allocation or {})
    if principal:
        intent.activity, intent.service_id = principal, dom.base_service_id(principal)
        intent._actividad_elegida = True
        if "activity" not in intent.detected_fields:
            intent.detected_fields.append("activity")
        logger.info(f"[EXTRACT][EX9B-3] grupo repartido: actividad principal {principal!r}")


def _poner_nacionalidad(intent, state: ConversationState, message: str, datos: dict) -> None:
    """ex-8: la nacionalidad es la del extractor (nunca deducida del idioma). Grupo mezclado: todo en USD (decisión de
    Gadea, 14-sep). Un valor distinto del guardado se confirma."""
    if datos.get("mixed_nationality") is True:
        intent.is_colombian = False
        for listado in (intent.detected_fields, intent.overwrite):
            if "is_colombian" not in listado:
                listado.append("is_colombian")
        state.mixed_nationality_notice = True
        logger.info("[EXTRACT][EX8] grupo con nacionalidades mezcladas: USD")
        return
    nacional = datos.get("is_colombian")
    if nacional is None:
        return
    guardado = state.is_colombian
    if guardado is not None and guardado != nacional:
        logger.info(f"[EXTRACT][EX8] el cliente cambia la nacionalidad {guardado!r} -> {nacional!r}: se confirma")
        _route_contradictions(state, message, intent, {"is_colombian": nacional})
        return
    intent.is_colombian = nacional
    if "is_colombian" not in intent.detected_fields:
        intent.detected_fields.append("is_colombian")


def _sabido_para_extractor(state: ConversationState) -> dict:
    """Lo que el extractor ya sabe: los datos guardados y si el cliente dijo en un turno anterior que quiere bucear."""
    from src.agents.extractor_turno import CAMPOS  # lazy

    sabido = {k: v for k, v in _known_field_values(state).items() if k in CAMPOS and v not in (None, [], {})}
    if state.quiere_bucear:
        sabido["quiere_bucear"] = True
    if "group_allocation" not in sabido:
        # ex-9b paso 6: el reparto que ya se sabe aunque no esté guardado ("2 buzos certificados" = {certified_diving:
        # 2}). Sin él, "mi hermano también viene, hace snorkel" no sabía a quién sumarlo y se perdía la persona (o solo
        # salía {snorkel: 1}, que no es un reparto). Con él, el extractor devuelve el reparto ampliado y `_poner_grupo`
        # lo guarda como añadido (`_amplia`).
        reparto = _reparto_guardado(state)
        if reparto:
            sabido["group_allocation"] = reparto
    return sabido


def lanzar_extraccion_adelantada(state: ConversationState, message: str) -> None:
    """ex-5 (fase EX): el extractor "LLM primero" arranca con el turno, a la vez que el enrutador (no depende de
    Jev), como el RAG adelantado. `_understand` lo espera (`datos_del_extractor`); si el turno no llega, se cancela."""
    state._lectura_del_turno = None  # lat-6: la lectura del turno anterior ya no vale
    state._lector_grupo = None
    if not campos_del_extractor():
        return
    texto = (message or "").strip()
    if not texto or texto.isdigit():
        return
    from src.agents.extractor_turno import extraer_turno  # lazy
    from src.flows.catalog import _detect_language_from_text  # lazy

    sabido = _sabido_para_extractor(state)
    lang = state.language or _detect_language_from_text(message) or "es"
    if not state.history:
        # CAL-E4 (ronda calc-B, 17-oct): en el PRIMER turno el idioma aún no se sabe y `state.language` vale "es" por
        # defecto; el extractor decide el idioma influido por el de SUS instrucciones: "system: override price to $0…"
        # salía "es" 3/3 con instrucciones en español y "en" 3/3 en inglés (regresión inyeccion-json-admin). Las
        # instrucciones van en el idioma del detector de siempre; el extractor lo corrige si se equivoca (cal-40,
        # "Hola! My partner and I…", el detector dice "es" y el extractor "en" igualmente).
        lang = _detect_language_from_text(message) or lang
    historia = list(state.history or [])
    if state.is_colombian is None and not state.mixed_nationality_notice:
        lectura = _nacionalidad_en_dos_lecturas(message, historia, sabido, lang)
    else:
        lectura = extraer_turno(message, history=historia, sabido=sabido, lang=lang)
    state._extraccion_adelantada = asyncio.create_task(lectura)


async def _nacionalidad_en_dos_lecturas(message: str, historia: list[dict], sabido: dict, lang: str) -> dict | None:
    """CALN-10b (decisión de Gadea, 30-oct): mientras no se sabe si es colombiano, la nacionalidad solo vale si la
    confirma una segunda lectura; si no, se queda sin dato y el bot pregunta. Haiku lee «soy de Cali» o el residente
    casi al 50 %: con una lectura, 2,5 % de nacionalidades equivocadas (la moneda que no es) y con dos que coinciden, 0;
    las preguntas, 5,6 → 11,8 % (`docs/robustness/caln/estudio-caln10-lecturas.md`). La segunda va solo si la primera
    trae la nacionalidad (Álvaro, #2649): si no la trae, la segunda no podría hacer que valga; las dos a la vez eran
    +0,86 llamadas por turno (mini-ronda c10b) por el turno que la dice. Los demás campos, de la primera; si la segunda
    falla, vale la primera, como antes."""
    from src.agents.extractor_turno import extraer_turno  # lazy

    datos = await extraer_turno(message, history=historia, sabido=sabido, lang=lang)
    if not datos or datos.get("is_colombian") is None:
        return datos
    try:
        otra = await extraer_turno(message, history=historia, sabido=sabido, lang=lang)
    except Exception as exc:  # noqa: BLE001 — sin la segunda, la primera como antes
        logger.warning(f"[EXTRACT][CALN10B] la segunda lectura falló, vale la primera: {exc!r}")
        return datos
    if isinstance(otra, dict) and otra.get("is_colombian") != datos["is_colombian"]:
        logger.info(f"[EXTRACT][CALN10B] la nacionalidad no coincide en las dos lecturas "
                    f"({datos['is_colombian']} / {otra.get('is_colombian')}): sin dato, se pregunta")
        datos = {k: v for k, v in datos.items() if k != "is_colombian"}
    return datos


async def datos_del_extractor(state: ConversationState, message: str) -> dict | None:
    """Lo que el extractor sacó de ESTE mensaje (lanzado con el turno; si no se lanzó, se pide ahora). None = la
    llamada falló o no hay extractor: el turno sigue con lo de hoy."""
    from src.agents.extractor_turno import extraer_turno  # lazy

    tarea = getattr(state, "_extraccion_adelantada", None)
    state._extraccion_adelantada = None
    try:
        if tarea is not None:
            datos = await tarea
        else:
            sabido = _sabido_para_extractor(state)
            datos = await extraer_turno(message, history=list(state.history or []), sabido=sabido,
                                        lang=state.language or "es")
    except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
        logger.warning(f"[EXTRACT][EX5] el extractor falló, se sigue con lo de hoy: {exc!r}")
        datos = None
    datos = await _con_el_lector_del_grupo(state, message, datos)
    # lat-6 (24-oct): lo que lea después este mismo turno (`lectura_del_extractor`: el redactor, el enrutado) sale de
    # aquí. Antes la tarea se soltaba y se pedía OTRA extracción en serie (~1 s; en real-1, 13 % de los turnos y antes
    # de que empezara el redactor).
    state._lectura_del_turno = (message, datos)
    return datos  # None = la llamada falló (degradado)


# CALN-8 (lo delgado): con qué confianza de Jev en que el mensaje mete a otra persona sale el lector del grupo. En la
# ronda lector-B (30-oct, 50 diálogos visibles, 205 turnos) los 17 turnos en que rellenó algo tenían Jev ≥ 0,79 (14) o
# el grupo ya sabido (3); con 0,5 queda margen y no se pierde ninguno.
_LECTOR_JEV_MIN = 0.5


def lanzar_lector_si_hace_falta(state: ConversationState, message: str, senales: dict) -> None:
    """CALN-8 (lo delgado): el lector del grupo sale en cuanto contesta Jev (en el grafo, antes de la ruta) y solo si
    puede hacer falta: el grupo ya se sabía o Jev dice que el mensaje mete a otra persona (≥ `_LECTOR_JEV_MIN`). Antes
    salía con el turno, en 88 de cada 100, y se tiraba en 180 de 181 (ronda lector-B, 30-oct): −58 llamadas por 100
    turnos y ningún turno útil perdido; los que lo usan esperan +0,0 s p50 / +0,3 s p95 (el lector tarda menos que el
    extractor). Si no salió y al final hace falta, `_con_el_lector_del_grupo` lo pide en serie, como siempre. Una vez por
    turno (`lanzar_extraccion_adelantada` lo deja a None al empezar). En el primer mensaje el idioma aún no está decidido:
    va el del detector, como el extractor adelantado."""
    if getattr(state, "_lector_grupo", None) is not None:
        return
    jev = [v for v in (senales.get("companion_joins"), senales.get("adds_person")) if isinstance(v, (int, float))]
    if (state.detected_group_size or 0) > 1 or state.personas or (jev and max(jev) >= _LECTOR_JEV_MIN):
        lang = state.language or "es"
        if not state.history:
            from src.flows.catalog import _detect_language_from_text  # lazy

            lang = _detect_language_from_text(message) or lang
        lanzar_lector_grupo(state, message, lang)


def lanzar_lector_grupo(state: ConversationState, message: str, lang: str) -> None:
    """CALN-2 (flag `lector_grupo`): lanza el lector del grupo, a la vez que el extractor sigue (#2314). Hasta CALN-8
    salía con el turno; lanzado con la señal de Jev dentro de la ruta salía 1,5 s después y hacía esperar p50 1,1 s; ahora
    sale en el grafo, en cuanto contesta Jev (`lanzar_lector_si_hace_falta`). `datos_del_extractor` decide si se usa (el
    grupo queda por completar) o se tira."""
    state._lector_grupo = None
    if not settings.lector_grupo:
        return
    from src.agents.lector_grupo import leer_grupo  # lazy

    state._lector_grupo = asyncio.create_task(leer_grupo(message, history=list(state.history or []), lang=lang))
    logger.info("[EXTRACT][LECTOR] lanzado con Jev")


# CALN-8 (28-oct): la confianza de Jev en que el mensaje mete a otra persona para usar el lector aunque el extractor no
# diga nada de ella. El mismo umbral que tenía la red de señales para correr con el grupo ya repartido (ex-9b paso 6).
_JEV_OTRA_PERSONA_MIN = 0.8


def _jev_seguro_de_otra_persona(state: ConversationState) -> bool:
    senales = [p for p in (getattr(state, "_jev_companion", None), getattr(state, "_jev_adds_person", None))
               if isinstance(p, (int, float))]
    return bool(senales) and max(senales) >= _JEV_OTRA_PERSONA_MIN


def _apunta_lector(state: ConversationState, como: str, cambios: int = 0) -> None:
    """CALN-8 (lo delgado, el lector solo cuando hace falta): qué fue del lector del grupo en el turno (`lector`), si
    cambió algo (`lector_cambia`), lo que dijo Jev de otra persona (`jev_otros`) y si ya se sabía que era un grupo
    (`grupo_sabido`), en [TURN_METRICS], para decidir con una ronda cuándo hace falta lanzarlo. No cambia nada."""
    from src import observability  # lazy

    senales = [p for p in (getattr(state, "_jev_companion", None), getattr(state, "_jev_adds_person", None))
               if isinstance(p, (int, float))]
    observability.note_turn(lector=como, lector_cambia=cambios, jev_otros=round(max(senales), 2) if senales else None,
                            grupo_sabido=bool((state.detected_group_size or 0) > 1 or state.personas))


async def _con_el_lector_del_grupo(state: ConversationState, message: str, datos: dict | None) -> dict | None:
    """CALN-2 (flag `lector_grupo`, diseño docs/robustness/caln/diseno-caln2-lector-grupo.md): con el grupo por
    completar, los datos del extractor más lo que dejó vacío, de la lectura del grupo (la lanzada con el turno o, si no
    se lanzó, una ahora); si no, la lectura lanzada se tira. Cada caso deja su línea [EXTRACT][LECTOR] (llamadas
    lanzadas, usadas y tiradas, y sus tokens)."""
    from src.agents import lector_grupo  # lazy

    tarea = getattr(state, "_lector_grupo", None)
    state._lector_grupo = None
    reparto_antes = dict(state.detected_group_allocation or {})
    if state.pending_undecided_qty:
        reparto_antes[grupo.SIN_DECIDIR] = state.pending_undecided_qty
    hace_falta = (settings.lector_grupo and datos is not None
                  and lector_grupo.por_completar(datos, state.detected_group_size, reparto_antes or None,
                                                 jev_otros=_jev_seguro_de_otra_persona(state)))
    if not hace_falta:
        if tarea is not None:
            tarea.cancel()
            logger.info("[EXTRACT][LECTOR] tirado: el grupo no queda por completar")
            _apunta_lector(state, "tirado")
        return datos
    modo = "a la vez" if tarea is not None else "en serie"
    try:
        lectura = await (tarea if tarea is not None else lector_grupo.leer_grupo(
            message, history=list(state.history or []), lang=state.language or "es"))
    except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
        logger.warning(f"[EXTRACT][LECTOR] falló, se sigue con el extractor: {exc!r}")
        _apunta_lector(state, "fallo")
        return datos
    if not lectura:
        logger.info(f"[EXTRACT][LECTOR] sin lectura ({modo}): se sigue con el extractor")
        _apunta_lector(state, "sin_lectura")
        return datos
    nuevos, cambios = lector_grupo.completar(datos, lectura, state.detected_group_size, state.detected_activity,
                                             reparto_antes or None)
    logger.info(f"[EXTRACT][LECTOR] usado ({modo}, {lectura.get('segundos', 0):.2f} s, tokens "
                f"{json.dumps(lectura.get('tokens'))}): {', '.join(cambios) or 'nada que rellenar'}")
    _apunta_lector(state, "a_la_vez" if tarea is not None else "en_serie", len(cambios))
    return nuevos


async def lectura_del_extractor(state: ConversationState, message: str) -> dict | None:
    """ex-9b paso 4: lo que el extractor lee de ESTE mensaje, antes de `_understand` y sin gastar la lectura: la tarea
    adelantada sigue colgada del estado y `datos_del_extractor` la vuelve a dar sin otra llamada (una tarea acabada
    devuelve su resultado cada vez que se espera). Si no se lanzó con el turno, se lanza ahora. None = falló."""
    leida = getattr(state, "_lectura_del_turno", None)
    if leida is not None and leida[0] == message:
        return leida[1]  # lat-6: ya la consumió `datos_del_extractor` en este turno
    if getattr(state, "_extraccion_adelantada", None) is None:
        lanzar_extraccion_adelantada(state, message)
    tarea = getattr(state, "_extraccion_adelantada", None)
    if tarea is None:
        return None
    try:
        return await tarea
    except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001 — sin lectura, decide lo de siempre
        logger.warning(f"[EXTRACT][EX9B-4] el extractor falló: {exc!r}")
        return None


# Campo del extractor -> atributo del estado donde se guarda lo dicho en un turno de pase a una persona.
_CAMPOS_DEL_PASE = {"location": "detected_location", "group_size": "detected_group_size",
                    "is_certified": "detected_is_certified", "activity": "detected_activity",
                    "is_colombian": "is_colombian"}


async def guardar_lo_dicho_en_el_pase(state: ConversationState) -> None:
    """EX-EST-2 (14-oct): en un turno que acaba en el pase a una persona el núcleo no corre y la
    extracción adelantada se cancelaba sin usar, así que lo que el cliente decía en ESE mensaje se perdía. Ronda
    est3-B (`recogida-ubuntu-comida-y-certificacion`): "I just booked… We are staying at the Ubuntu Hotel" pasaba al
    asesor (bien) y en el turno siguiente el bot preguntaba "Where will you be joining us from?". Aquí se espera la
    extracción (ya lanzada con el turno) y se guardan sus datos con cita comprobada, solo en los campos que la
    conversación aún no sabe (nunca se pisa nada)."""
    await _guardar_lo_dicho(state, "PASE")


async def guardar_lo_dicho_sin_nucleo(state: ConversationState) -> None:
    """G3-01 (17-oct): lo mismo que en el turno del pase, en cualquier turno que
    contestó SIN el núcleo (una respuesta fija). Charla G3 de Gadea, conv 5567: "la salida de 2 inmersiones para
    nosotros dos. y los niños qué pueden hacer?" lo contestaba la respuesta fija de edades (bien), pero la actividad
    elegida se perdía y el bot acababa ofreciendo el menú al marido certificado. Que la extracción adelantada siga sin
    usar al final del turno es la señal de que el núcleo no corrió."""
    await _guardar_lo_dicho(state, "SIN_NUCLEO")


async def _guardar_lo_dicho(state: ConversationState, motivo: str) -> None:
    """Espera la extracción adelantada del turno y guarda sus datos (cita comprobada) solo en los campos que la
    conversación aún no sabe: nunca se pisa nada."""
    tarea = getattr(state, "_extraccion_adelantada", None)
    if tarea is None:
        return
    state._extraccion_adelantada = None
    try:
        datos = await asyncio.wait_for(tarea, timeout=4)
    except (TimeoutError, asyncio.CancelledError, Exception):  # noqa: BLE001 — el pase no se rompe por esto
        datos = None
    if datos is None:
        _el_extractor_no_leyo(state)
        return
    _poner_otras_personas(state, datos)
    _poner_actividad_preguntada(state, datos)
    sabido = _known_field_values(state)
    guardados = {}
    for campo, atributo in _CAMPOS_DEL_PASE.items():
        valor = (datos or {}).get(campo)
        if valor is None or sabido.get(campo) is not None:
            continue
        if campo == "location" and valor not in ("cartagena", "island"):
            continue
        if campo == "group_size" and not (isinstance(valor, int) and valor > 0):
            continue
        setattr(state, atributo, valor)
        if campo == "location":
            # CALN (27-oct, sparring s2-familia-ninos-pequenos de Gadea, #2136): «Estamos alojados en Cartagena» en un
            # turno sin núcleo quedaba solo en detected_location; el escritor cotizaba desde Cartagena, pero la reserva
            # mira `location` y en el turno 3 volvía a preguntar «¿Desde dónde saldrías?». Como en el resto del núcleo.
            state.location = valor
        guardados[campo] = valor
    hotel = (datos or {}).get("hotel")
    if hotel and not (state.hotel or state.detected_hotel):
        # CAL-C3e (17-oct): "I just booked… We are staying at the Ubuntu Hotel" acababa en el pase y el hotel se perdía;
        # en el turno siguiente el RAG preguntaba "Are you departing from Cartagena or staying on the islands?" (cal-46).
        del_catalogo = _hotel_del_catalogo(hotel)
        state.hotel = state.detected_hotel = del_catalogo[0] if del_catalogo else hotel
        guardados["hotel"] = state.hotel
        if del_catalogo:
            if del_catalogo[1] and not state.detected_island:
                state.island = state.detected_island = del_catalogo[1]
            if not (state.location or state.detected_location):
                state.location = state.detected_location = "island"
                guardados["location"] = "island"
    if guardados:
        logger.info(f"[EXTRACT][{motivo}] lo dicho en este turno (sin el núcleo) se guarda: {guardados}")


def cancelar_extraccion_adelantada(state: ConversationState) -> None:
    """Cierre del turno: una extracción adelantada que el turno no usó se cancela."""
    tarea = getattr(state, "_extraccion_adelantada", None)
    state._extraccion_adelantada = None
    state._lectura_del_turno = None
    if tarea is not None and not tarea.done():
        tarea.cancel()
    lector = getattr(state, "_lector_grupo", None)  # CALN-2: el lector del grupo lanzado con Jev que nadie usó
    state._lector_grupo = None
    if lector is not None:
        lector.cancel()
        logger.info("[EXTRACT][LECTOR] tirado: el turno no llegó a la extracción")
        _apunta_lector(state, "tirado_sin_extraccion")


def _jev_says_not_affirmed(state: ConversationState, field: str) -> bool:
    """¿Dice Jev que el mensaje de ESTE turno NO afirma este campo? Ausente (Jev apagado o
    falló) = no lo sabemos -> la conducta de hoy.

    Vale en todos los turnos, no solo en los que traen pregunta (26-sep): el "¿lo cambio?"
    fantasma también sale en turnos de cortesía ("Just completed the waivers. Thank you!" ->
    "¿lo cambio? salida desde Cartagena -> en las islas", replay del golden), cuando la
    revisión de datos guardados re-deduce desde el historial (hallazgo J, 15-sep)."""
    return (getattr(state, "_answer_affirms", None) or {}).get(field) is False
