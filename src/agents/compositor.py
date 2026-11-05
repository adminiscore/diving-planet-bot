"""CALN-6 (27-oct, decisión de Gadea: opción A): un compositor al final del turno.

La respuesta de un turno se escribe en ~26 sitios y se le pegan trozos en ~27 (`docs/robustness/caln/
estudio-caln6-composicion.md`): el escritor cierra con la pregunta de la reserva, el código le añade detrás lo que se le
escapó (arq-7b: qué incluye, la recogida, el alojamiento), los avisos van al final, y la pregunta se vuelve a pegar. En
la ronda caln1-B, 16 respuestas decían lo mismo dos veces y 17 llevaban dos preguntas.

Paso 1: la pregunta de la reserva va UNA vez y al FINAL. `ask_slot` apunta en el turno cada pregunta que formula
(`_preguntas_del_turno`); aquí se quitan sus copias de la respuesta, estén donde estén (un párrafo entero o una frase con
«?» dentro de otro), y se pone la de la pregunta pendiente al final. Si la respuesta no la llevaba (una tarjeta, un
pase), no se toca.

Paso 2: UNA pregunta como mucho. Si lo que queda ya pregunta algo (el escritor cierra con su pregunta, la nota de la
tarjeta pregunta), la de la reserva no se pone y queda pendiente para el turno siguiente: la regla de u3-4 y CAL-C3b
(`_answer_replaces_the_booking_question`), que solo valía en algunos caminos. Y las frases de la pregunta final (la
explicación que la acompaña) no se repiten en el cuerpo.
"""
from __future__ import annotations

import logging
import re
import unicodedata

from src.flows.como_reserva import ENLACE, como_reserva, hotel_conocido

logger = logging.getLogger("uvicorn.error")

_PARRAFO = "\n\n"
# Una frase que acaba en «?» (con el cierre de negrita, cursiva o paréntesis), dentro de una línea.
_PREGUNTA_RE = re.compile(r"[^.!?\n]*\?+[*_)\]]*")
# Una frase entera (acaba en «.», «!» o «?»), dentro de una línea.
_FRASE_RE = re.compile(r"[^.!?\n]+[.!?]+[*_)\]]*")
# Un párrafo que acaba preguntando: su última línea acaba en «?» (con la negrita o un emoji detrás).
_ACABA_PREGUNTANDO_RE = re.compile(r"\?[*_)\]]*\s*[\U0001F000-\U0001FAFF☀-➿]?\s*$")
# El saludo de Coral del primer turno (`conversational_core._greeting`) y el «¡Hola!» con que el escritor empieza.
_SALUDO_DE_CORAL_RE = re.compile(r"Soy \*Coral\*|I'm \*Coral\*")
_SALUDO_INICIAL_RE = re.compile(r"^\s*(?:¡\s*)?(?:hola|buenas(?: tardes| noches)?|buenos d[ií]as|hi|hello|hey)\b"
                                r"[^.!?\n]{0,25}?[!.,]\s*", re.IGNORECASE)


def _palabras(texto: str) -> set[str]:
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return set(re.sub(r"[^a-z0-9 ]", " ", t).split())


# 0.52b: la misma pregunta por 3.ª vez es grave (criterio de Álvaro, #2716). «¿Desde dónde saldrías?» salía 7 veces en 7 turnos a quien
# aún lo estaba decidiendo. Lo que pregunta el flujo sale como mucho 2 veces, salvo que pida reservar o pagar, porque entonces
# hace falta, o que no haya nada más que decir (un «¡Perfecto!» suelto no es una respuesta).
_VECES_MAX = 2
_PALABRAS_DE_UNA_RESPUESTA = 5


# CALN-27 (un dato, un solo dueño): el enlace de reserva lo pone la tarjeta. Si el escritor da el mismo, sobra el suyo: en 16 de 50
# charlas de sparring salía el enlace o el pago dos veces. Se compara exacto, sin leer el sentido, y solo se toca lo de antes de la
# 1.ª tarjeta (dos tarjetas pueden llevar el mismo enlace, como el minicurso y los Bubble Makers).
_ENLACE_DE_RESERVA_RE = re.compile(r"https://book\.divingplanet\.org/book/[\w\-]+/\d+")
_ENLACE_CON_IDIOMA_RE = re.compile(_ENLACE_DE_RESERVA_RE.pattern + r"(?:\?[\w=&\-]*)?(?:#[\w\-]*)?")  # «…#rvrd-1» es parte del enlace
_TARJETA_RE = re.compile(r"(?m)^🤿 \*")
_FIN_DE_FRASE_RE = re.compile(r"(?<=[.!?:])\s+")


def _sin_enlaces_repetidos(respuesta: str) -> str:
    """Quita de lo que escribe el escritor la frase del enlace que ya sale más abajo."""
    tarjeta = _TARJETA_RE.search(respuesta)
    if not tarjeta:
        return respuesta
    cuerpo, resto = respuesta[:tarjeta.start()], respuesta[tarjeta.start():]
    de_la_tarjeta = set(_ENLACE_DE_RESERVA_RE.findall(resto))
    if not de_la_tarjeta & set(_ENLACE_DE_RESERVA_RE.findall(cuerpo)):
        return respuesta
    limpio = _sin_estos_enlaces(cuerpo, de_la_tarjeta)
    logger.info("[CORE][CALN27] compositor: el enlace del escritor ya sale en la tarjeta: fuera el suyo")
    return f"{limpio}{_PARRAFO}{resto}" if limpio else resto


def _sin_enlaces_de_reserva(state, respuesta: str) -> str:
    """CALN-35: a quien no reserva por enlace no le llega ninguno, venga de donde venga. La respuesta adelantada se escribe antes
    de leer este mensaje («…para colombianos», mini c055), así que el escritor no siempre lo sabe; aquí ya está todo leído."""
    if como_reserva(state) == ENLACE:
        return respuesta
    enlaces = set(_ENLACE_DE_RESERVA_RE.findall(respuesta))
    if not enlaces:
        return respuesta
    logger.info(f"[CORE][CALN35] compositor: fuera el enlace de reserva ({como_reserva(state)})")
    return _sin_estos_enlaces(respuesta, enlaces)


def _sin_estos_enlaces(cuerpo: str, enlaces: set[str]) -> str:
    """El texto sin la frase de esos enlaces. Lo que anunciaba el enlace («Reserva aquí:») se va con él; si el párrafo se queda sin
    nada, se va entero."""
    parrafos = []
    for parrafo in cuerpo.split(_PARRAFO):
        lineas = []
        for linea in parrafo.split("\n"):
            frases = []
            for frase in _FIN_DE_FRASE_RE.split(linea):
                if set(_ENLACE_DE_RESERVA_RE.findall(frase)) & enlaces:
                    if frases and frases[-1].rstrip().endswith(":"):
                        frases.pop()
                    # Lo que venga detrás del enlace sin punto («…: https://… Lleva tu carné.») no es la frase del enlace.
                    detras = _ENLACE_CON_IDIOMA_RE.split(frase)[-1].lstrip(" .,;)")
                    if re.search(r"[^\W\d_]{2,}", detras):
                        frases.append(detras)
                    continue
                frases.append(frase)
            if frases or not linea.strip():
                lineas.append(" ".join(frases))
        while lineas and lineas[-1].rstrip().endswith(":"):
            # Solo la frase que anunciaba el enlace: en la misma línea podía ir la respuesta (mini 0.56: «Yes, we operate on Easter
            # Sunday. … and pay there:», y el cliente se quedaba sin saber si abrimos).
            antes = _FIN_DE_FRASE_RE.split(lineas.pop().rstrip())[:-1]
            if antes:
                lineas.append(" ".join(antes))
        if any(x.strip() for x in lineas):
            parrafos.append("\n".join(lineas))
    return _PARRAFO.join(p.strip() for p in parrafos if p.strip())


def _veces_preguntada(state, slot: str | None) -> int:
    return (getattr(state, "preguntas_hechas", None) or {}).get(slot, 0)


def _ya_se_pregunto_bastante(state, slot: str | None) -> bool:
    """Si pide el enlace, hace falta. Para contestar cómo se paga, no: «¿y por transferencia tiene descuento?» recibía el origen
    por 3.ª vez (certificado-fecha-precio, mini 0.53, en los dos lados)."""
    return _veces_preguntada(state, slot) >= _VECES_MAX and "enlace" not in set(getattr(state, "_intenciones", None) or [])


def _contar_la_pregunta(state, slot: str | None) -> None:
    hechas = dict(getattr(state, "preguntas_hechas", None) or {})
    hechas[slot] = hechas.get(slot, 0) + 1
    state.preguntas_hechas = hechas


def _las_dos_salidas(state, cuerpo: str) -> str | None:
    """Mini 0.53: el freno dejaba salir la 3.ª y la 4.ª vez cuando no quedaba nada más que decir («Frances» → «¿Desde dónde
    saldrías?»). Si el plan tiene una salida por origen, en vez de la misma pregunta van las dos, con su precio y su enlace, y el
    cliente elige. Sin eso (varios planes por origen), None: se pregunta."""
    from src.agents import conversational_core as core  # lazy

    salidas = core._dos_variantes(state, con_enlace=como_reserva(state) == ENLACE)
    if not salidas:
        return None
    logger.info(f"[CORE][053B] compositor: el origen ya salió {_VECES_MAX} veces: van las dos salidas en vez de la pregunta")
    _aplazar(state)
    # Con enlaces, el de las islas falta hasta que diga su hotel (CALN-35).
    cola = core.SIN_ENLACE_DE_LAS_ISLAS_ES if state.language == "es" else core.SIN_ENLACE_DE_LAS_ISLAS_EN
    return _PARRAFO.join(x for x in (cuerpo.strip(), salidas, cola if "http" in salidas and not hotel_conocido(state) else "") if x)


def _con_el_freno_del_origen(state, respuesta: str) -> str:
    """0.52b: el origen también se pregunta por caminos que no pasan por `ask_slot` (tras la lista de precios de los dos orígenes,
    tras los dos enlaces y la confirmación de ORIGEN-CONFIRMA), y en la mini eran 7 de 7 turnos sumando los tres: cuentan como la
    misma pregunta. Si ya salió bastante, se quita y se queda lo que el cliente pidió. Son textos nuestros, fijos, no del cliente."""
    from src.agents import conversational_core as core  # lazy

    resto_por_pregunta = {
        **{texto: "" for por_idioma in core._CONFIRMA_ORIGEN.values() for texto in por_idioma.values()},
        core.ORIGEN_TRAS_LAS_VARIANTES_ES: "",
        core.ORIGEN_TRAS_LAS_VARIANTES_EN: "",
        core.ORIGEN_TRAS_LOS_ENLACES_ES: core.SIN_ENLACE_DE_LAS_ISLAS_ES,
        core.ORIGEN_TRAS_LOS_ENLACES_EN: core.SIN_ENLACE_DE_LAS_ISLAS_EN,
    }
    fija = next((p for p in resto_por_pregunta if p in respuesta), None)
    if fija is None:
        return respuesta
    # Tras los dos enlaces la pregunta sobra aunque pida el enlace: ya los tiene, con la indicación de cuál usar.
    con_los_enlaces = (resto_por_pregunta[fija] and "book.divingplanet.org" in respuesta
                       and _veces_preguntada(state, core.SLOT_LOCATION) >= _VECES_MAX)
    if _ya_se_pregunto_bastante(state, core.SLOT_LOCATION) or con_los_enlaces:
        sin = respuesta.replace(fija, resto_por_pregunta[fija]).rstrip()
        if len(_palabras(sin)) >= _PALABRAS_DE_UNA_RESPUESTA:
            logger.info(f"[CORE][052B] compositor: el origen ya salió {_VECES_MAX} veces sin contestarse: no sale otra")
            _aplazar(state)
            return sin
        if salidas := _las_dos_salidas(state, sin):
            return salidas
    _contar_la_pregunta(state, core.SLOT_LOCATION)
    return respuesta


def _es_la_misma(a: str, b: str) -> bool:
    """Dos textos que dicen lo mismo: las mismas cifras y casi las mismas palabras (sobre el más largo)."""
    if re.findall(r"\d[\d.,]*", a) != re.findall(r"\d[\d.,]*", b):
        return False
    pa, pb = _palabras(a), _palabras(b)
    return bool(pa and pb) and len(pa & pb) / max(len(pa), len(pb)) >= 0.8


def _frase_sin_la_pregunta(frase: str, preguntas: list[str]) -> str | None:
    """La frase del escritor que acaba en la pregunta de la reserva, con algo delante: «Para este plan hay que dormir en las islas:
    ¿Desde dónde saldrías?» (tanda s05a, a quien acaba de decir «desde Cartagena»). Queda lo de delante, con punto. None si no es el caso."""
    entera = frase.rstrip()
    for pregunta in preguntas:
        if len(entera) > len(pregunta) and entera.casefold().endswith(pregunta.casefold()):
            delante = entera[:-len(pregunta)].rstrip().rstrip(":,;—-").rstrip()
            return f"{delante}." if delante else ""
    return None


def _sin_las_preguntas(respuesta: str, preguntas: list[str]) -> tuple[bool, str]:
    """(si había alguna, la respuesta sin ellas): fuera los párrafos que son un párrafo de una pregunta del turno y, dentro
    de los demás, las frases con «?» que son la frase con «?» de una pregunta."""
    partes_de_preguntas = [p.strip() for q in preguntas for p in q.split(_PARRAFO) if p.strip()]
    frases_de_preguntas = [f.strip() for q in preguntas for f in _PREGUNTA_RE.findall(q)]
    quitada, quedan = False, []
    for parrafo in respuesta.split(_PARRAFO):
        if parrafo.strip() and any(_es_la_misma(parrafo.strip(), p) for p in partes_de_preguntas):
            quitada = True
            continue
        antes = parrafo
        for frase in _PREGUNTA_RE.findall(parrafo):
            if any(_es_la_misma(frase.strip(), q) for q in frases_de_preguntas):
                parrafo = parrafo.replace(frase, "", 1)
            elif (sin_ella := _frase_sin_la_pregunta(frase, frases_de_preguntas)) is not None:
                parrafo = parrafo.replace(frase, sin_ella, 1)
        if parrafo != antes:
            quitada = True
            parrafo = re.sub(r"[ \t]{2,}", " ", parrafo).strip()
        if parrafo.strip():
            quedan.append(parrafo)
    return quitada, _PARRAFO.join(quedan)


def _sin_las_frases_de(cuerpo: str, pregunta: str) -> str:
    """El cuerpo sin las frases de la pregunta que va al final, dichas ya en el cuerpo: «¡Perfecto, serían 2 personas
    para el minicurso! Puedes salir desde Cartagena… o, si ya estás en las islas…» y debajo «¿Desde dónde saldrías?
    Puedes salir desde Cartagena…» (4 de las 7 respuestas que repiten en caln2-B). Solo frases largas: «¡Perfecto!» no
    es la pregunta."""
    frases = [f.strip() for f in _FRASE_RE.findall(pregunta) if len(_palabras(f)) >= 6]
    if not frases:
        return cuerpo
    quedan = []
    for parrafo in cuerpo.split(_PARRAFO):
        antes = parrafo
        for frase in _FRASE_RE.findall(parrafo):
            if any(_es_la_misma(frase.strip(), f) for f in frases):
                parrafo = parrafo.replace(frase, "", 1)
        if parrafo != antes:
            parrafo = re.sub(r"[ \t]{2,}", " ", parrafo).strip()
        if parrafo.strip():
            quedan.append(parrafo)
    return _PARRAFO.join(quedan)


def _ya_pregunta(cuerpo: str) -> bool:
    """¿Algún párrafo acaba preguntando? (la pregunta del escritor, la de la nota de la tarjeta)."""
    return any(_ACABA_PREGUNTANDO_RE.search(p.strip().splitlines()[-1]) for p in cuerpo.split(_PARRAFO) if p.strip())


def _aplazar(state) -> None:
    """La pregunta de la reserva no se hace este turno: sigue pendiente (`core_pending_slot` no cambia) y se va lo que
    preparó para su respuesta, que el cliente no ve: sus botones y la actividad que recomendaba (gen-8, CAL-C1). Si no,
    un «sí» a la pregunta del escritor («¿quieres que te cuente más del curso?») elegía esa actividad
    (`nucleo/routing._apply_short_answer`)."""
    state.quick_replies = []
    antes = getattr(state, "_sugerida_al_empezar", None)
    if getattr(state, "suggested_activity", None) and state.suggested_activity != antes:
        state.suggested_activity = antes


def _sin_saludo_repetido(respuesta: str, *, escribio: bool = False) -> str:
    """Tras el saludo de Coral, el escritor no vuelve a saludar (CALN-6 paso 2: «¡Hola! 🪸 Soy Coral…» y debajo «¡Hola!
    Bucear en las islas…» en 27 de los 116 primeros turnos de caln2-B). Si en el turno contesta el escritor, que ya da
    la bienvenida a su manera («¡Bienvenidos!», «¡Con mucho gusto te ayudo a armar el plan!»: 4 de 10 en la batería
    CALN4), el saludo se queda en la presentación, sin su frase de calidez."""
    partes = respuesta.split(_PARRAFO)
    for i, parrafo in enumerate(partes[:-1]):
        if _SALUDO_DE_CORAL_RE.search(parrafo):
            if escribio:
                from src.agents.conversational_core import CALIDEZ_DEL_SALUDO  # lazy

                for calidez in CALIDEZ_DEL_SALUDO.values():
                    partes[i] = partes[i].replace(calidez, "")
            resto = _SALUDO_INICIAL_RE.sub("", partes[i + 1], count=1)
            if resto.strip() and resto != partes[i + 1]:
                partes[i + 1] = resto if resto[0] in "¡¿*_" else resto[0].upper() + resto[1:]
            break
    return _PARRAFO.join(partes)


def _sin_el_cierre_si_ya_pregunta(respuesta: str) -> str:
    """La invitación genérica de la tarjeta («¿Te ayudo con algo más?…») cede ante una pregunta concreta de la misma
    respuesta (sparring CALN4, b2 t2: «Would you like help adding the refresher for him?» y la tarjeta con su cierre)."""
    from src.flows.cart_render import CIERRE_DE_LA_TARJETA  # lazy

    partes = respuesta.split(_PARRAFO)
    cierres = [i for i, p in enumerate(partes) if p.strip() in CIERRE_DE_LA_TARJETA.values()]
    otras = [p for i, p in enumerate(partes) if i not in cierres and p.strip()]
    if not cierres or not _ya_pregunta(_PARRAFO.join(otras)):
        return respuesta
    logger.info("[CORE][CALN6] compositor: la respuesta ya pregunta; fuera la invitación genérica de la tarjeta")
    return _PARRAFO.join(otras)


def _una_oferta_del_asesor(respuesta: str) -> str:
    """En el cierre en pesos, la tarjeta ofrece el asesor con nuestra frase (`slotfill_close._OFERTA_DEL_ASESOR`, la que
    reconoce el «sí» que la sigue) y el escritor, delante, ya preguntaba lo mismo con otras palabras («¿Quieres que te
    pase con un asesor para continuar la reserva?»): dos preguntas en el mismo mensaje (CALN-18: 7 veces en 3 tandas de
    sparring hasta el 3-nov, y Cali t2 en s04d). Una pregunta como mucho (paso 2), y es la nuestra: fuera las preguntas
    de los párrafos de delante."""
    from src.agents.nucleo.slotfill_close import _OFERTA_DEL_ASESOR  # lazy

    partes = respuesta.split(_PARRAFO)
    oferta = next((i for i, p in enumerate(partes) if p.strip() in _OFERTA_DEL_ASESOR.values()), None)
    if not oferta:
        return respuesta
    delante = []
    for parrafo in partes[:oferta]:
        antes = parrafo
        for frase in _PREGUNTA_RE.findall(parrafo):
            parrafo = parrafo.replace(frase, "", 1)
        if parrafo != antes:
            parrafo = re.sub(r"[ \t]{2,}", " ", parrafo).strip()
            logger.info("[CORE][CALN18] compositor: la tarjeta ofrece el asesor; fuera la pregunta de delante")
            if not _palabras(parrafo):
                continue  # solo quedaba el emoji de la pregunta («… del domingo? 🐠»)
        if parrafo.strip():
            delante.append(parrafo)
    return _PARRAFO.join(delante + partes[oferta:])


def _sin_parrafos_repetidos(respuesta: str) -> str:
    """Fuera los párrafos idénticos a uno anterior (en un pase, lo contestado delante y la respuesta del turno traían la
    misma lista dos veces: caln1-B, pareja-certificados-cop-descuento-almuerzo t3)."""
    vistos, quedan = set(), []
    for parrafo in respuesta.split(_PARRAFO):
        clave = " ".join(parrafo.split())
        if clave and clave in vistos:
            continue
        vistos.add(clave)
        quedan.append(parrafo)
    return _PARRAFO.join(quedan)


def componer(state, respuesta: str, *, pase: bool = False, escribio: bool | None = None) -> str:
    """La respuesta del turno, ya compuesta, sin enlaces para quien no le tocan (CALN-35)."""
    return _sin_enlaces_de_reserva(state, _componer(state, respuesta, pase=pase, escribio=escribio))


def _componer(state, respuesta: str, *, pase: bool = False, escribio: bool | None = None) -> str:
    """La respuesta del turno con la pregunta de la reserva una vez y al final (paso 1), si no pregunta ya otra cosa
    (paso 2). En un turno que pasa a un asesor, sus copias salen y no se vuelve a poner: sigue una persona (y la nota
    de la tarjeta, si va, ya pregunta). `escribio`: si en el turno contestó el escritor (sin darlo, lo dice la traza
    del turno, `rag_used`)."""
    if not respuesta:
        return respuesta
    if escribio is None:
        from src.observability import hechos_del_turno  # lazy

        escribio = bool(hechos_del_turno().get("rag_used"))
    respuesta = _una_oferta_del_asesor(_sin_el_cierre_si_ya_pregunta(_sin_parrafos_repetidos(_sin_saludo_repetido(
        respuesta, escribio=escribio))))
    respuesta = _sin_enlaces_repetidos(respuesta)
    if not pase:
        respuesta = _con_el_freno_del_origen(state, respuesta)
    preguntas = getattr(state, "_preguntas_del_turno", None) or []
    pendiente = state.core_pending_slot
    final = next((texto for slot, texto in reversed(preguntas) if slot == pendiente and texto), None)
    if final is None and not pase:
        # Mini 0.58 (semana-santa, 2 de 3): «Quiero quedarme en las islas» y el escritor cerraba con la pregunta del origen fijada al
        # empezar el turno. Tiene dos frases y debajo va la pieza, así que nadie la reconocía como final, y se quedaba. Ya contestada, fuera.
        ya_contestadas = [texto for slot, texto in preguntas if texto and pendiente and slot != pendiente]
        return _sin_las_preguntas(respuesta, ya_contestadas)[1] if ya_contestadas else respuesta
    quitada, cuerpo = _sin_las_preguntas(respuesta, [texto for _, texto in preguntas if texto])
    if not quitada:
        return respuesta
    logger.info(f"[CORE][CALN6] compositor: {len(respuesta)} → {len(cuerpo)} caracteres sin las preguntas del turno "
                f"({[slot for slot, _ in preguntas]}), pendiente {pendiente!r}, pase {pase}")
    # La explicación de una pregunta del turno que ya no es la pendiente (acaba de contestarla) tampoco se queda.
    for _, texto in preguntas:
        if texto and texto != final:
            cuerpo = _sin_las_frases_de(cuerpo, texto)
    if pase or final is None:
        return cuerpo
    if _ya_pregunta(cuerpo):
        logger.info(f"[CORE][CALN6] compositor: la respuesta ya pregunta; {pendiente!r} queda para el turno siguiente")
        _aplazar(state)
        return cuerpo
    cuerpo = _sin_las_frases_de(cuerpo, final)
    if _ya_se_pregunto_bastante(state, pendiente):
        if len(_palabras(cuerpo)) >= _PALABRAS_DE_UNA_RESPUESTA:
            logger.info(f"[CORE][052B] compositor: {pendiente!r} ya salió {_VECES_MAX} veces sin contestarse: no sale otra")
            _aplazar(state)
            return cuerpo
        if pendiente == "location" and (salidas := _las_dos_salidas(state, cuerpo)):
            return salidas
    _contar_la_pregunta(state, pendiente)
    return f"{cuerpo.rstrip()}{_PARRAFO}{final}" if cuerpo.strip() else final
