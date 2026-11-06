"""CALN-6 (27-oct, decisión de Gadea: opción A): un compositor al final del turno.

La respuesta de un turno se escribe en ~26 sitios y se le pegan trozos en ~27 (`docs/robustness/caln/
estudio-caln6-composicion.md`): el escritor cierra con la pregunta de la reserva, el código le añade detrás lo que se le
escapó (arq-7b: qué incluye, la recogida, el alojamiento), los avisos van al final, y la pregunta se vuelve a pegar. En
la ronda caln1-B, 16 respuestas decían lo mismo dos veces y 17 llevaban dos preguntas.

Paso 1: la pregunta de la reserva va UNA vez y al FINAL. `ask_slot` apunta en el turno cada pregunta que formula
(`_preguntas_del_turno`); aquí se quitan sus copias de la respuesta y se pone la de la pregunta pendiente al final, si la
tabla dice que puede salir (`src/flows/que_preguntar.py`). Si la respuesta no la llevaba (una tarjeta, un pase), no se toca.

CALN-43 (decisión de Gadea, 6-nov): en un turno de la reserva el escritor no pregunta, así que las copias son textos nuestros,
tal cual, y la nuestra va siempre (antes, si el escritor ya preguntaba otra cosa, la de la reserva esperaba al turno siguiente).
"""
from __future__ import annotations

import logging
import re
import unicodedata

from src.flows import que_preguntar
from src.flows.como_reserva import ENLACE, como_reserva, hotel_conocido

logger = logging.getLogger("uvicorn.error")

_PARRAFO = "\n\n"
# Una frase que acaba en «?» (con el cierre de negrita, cursiva o paréntesis), dentro de una línea.
_PREGUNTA_RE = re.compile(r"[^.!?\n]*\?+[*_)\]]*")
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
# aún lo estaba decidiendo. CALN-43 P11 (decisión de Gadea, 6-nov): lo que pregunta el flujo sale como mucho 2 veces, sin excepciones; qué va
# en su lugar lo dice la tabla (`src/flows/que_preguntar.py`). Antes salía una 3.ª si pedía reservar o pagar, y así salieron las tres del
# panel 059c. Un «¡Perfecto!» suelto no es una respuesta: con el origen van las dos salidas.
_VECES_MAX = que_preguntar.VECES_MAX
_PALABRAS_DE_UNA_RESPUESTA = 5


# CALN-27 y CALN-43 (un dato, un solo dueño): si hay tarjeta con enlace, los enlaces de reserva los pone ella. Antes solo se quitaba el mismo enlace
# (en 16 de 50 charlas salía dos veces), y CALN-24 arbitraba si el escritor daba el de otro plan. Ahora el escritor recibe el plan de la tabla, y lo que
# no sea de la tarjeta se va; se queda el refresher, que lo pone el código con su «✅». Solo se toca lo de antes de la 1.ª tarjeta (dos tarjetas pueden
# llevar el mismo enlace, como el minicurso y los Bubble Makers).
_ENLACE_DE_RESERVA_RE = re.compile(r"https://book\.divingplanet\.org/book/[\w\-]+/\d+")
_ENLACE_CON_IDIOMA_RE = re.compile(_ENLACE_DE_RESERVA_RE.pattern + r"(?:\?[\w=&\-]*)?(?:#[\w\-]*)?")  # «…#rvrd-1» es parte del enlace
_TARJETA_RE = re.compile(r"(?m)^🤿 \*")
_FIN_DE_FRASE_RE = re.compile(r"(?<=[.!?:])\s+")


def _sin_enlaces_repetidos(respuesta: str) -> str:
    """Quita de lo que escribe el escritor los enlaces de reserva, si la tarjeta de abajo lleva los suyos."""
    tarjeta = _TARJETA_RE.search(respuesta)
    if not tarjeta:
        return respuesta
    cuerpo, resto = respuesta[:tarjeta.start()], respuesta[tarjeta.start():]
    del_codigo = {e for p in cuerpo.split(_PARRAFO) if p.startswith("✅") for e in _ENLACE_DE_RESERVA_RE.findall(p)}
    suyos = set(_ENLACE_DE_RESERVA_RE.findall(cuerpo)) - del_codigo
    if not suyos or not _ENLACE_DE_RESERVA_RE.search(resto):
        return respuesta
    limpio = _sin_estos_enlaces(cuerpo, suyos)
    logger.info("[CORE][CALN27] compositor: la tarjeta lleva el enlace: fuera el del escritor")
    return f"{limpio}{_PARRAFO}{resto}" if limpio else resto


def _enlaces_de_buceo_sin_precio_cerrado(state, respuesta: str) -> set[str]:
    """CALN-43, P5: el paquete sin hacer su nocturna, cuyo precio cierra un asesor, no lleva enlace de buceo: reservaría al precio del paquete entero. Se
    quitó el filtro general (paquete sin enlace → sin enlaces de buceo): le quitaba al irlandés de s04j el de las salidas, que había pedido."""
    from src.agents.conversational_core import plan_del_estado  # lazy
    from src.domain import activities as dom  # lazy
    from src.flows.catalog import RAW_SERVICES  # lazy

    if not (getattr(state, "detected_cert_days", None) and plan_del_estado(state).asesor_cierra_el_precio):
        return set()
    de_buceo = {enlace.group(0) for sid, s in RAW_SERVICES.items() if dom.activity_for_service(sid) == dom.activity_for_service("2_dives_1_day")
                and (enlace := _ENLACE_DE_RESERVA_RE.search(s.get("booking_url") or ""))}
    return set(_ENLACE_DE_RESERVA_RE.findall(respuesta)) & de_buceo


def _sin_enlaces_de_reserva(state, respuesta: str) -> str:
    """CALN-35: a quien no reserva por enlace no le llega ninguno, venga de donde venga. El escritor corre a la vez que
    la lectura de este mensaje («…para colombianos», mini c055), así que no siempre lo sabe; aquí ya está todo leído."""
    if como_reserva(state) == ENLACE:
        otros = _enlaces_de_buceo_sin_precio_cerrado(state, respuesta)
        return _sin_estos_enlaces(respuesta, otros) if otros else respuesta
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


def _sin_la_pregunta(state, cuerpo: str) -> str:
    """Lo que va en vez de la 3.ª vez (`que_preguntar.SIN_ELLA`): la respuesta; si no contesta nada (vacía, o un «¡Perfecto!» suelto),
    detrás un recordatorio que no pregunta, para que el cliente sepa cómo seguir."""
    _aplazar(state)
    if len(_palabras(cuerpo)) >= _PALABRAS_DE_UNA_RESPUESTA:
        return cuerpo
    return _PARRAFO.join(x for x in (cuerpo.strip(), que_preguntar.recordatorio(state.language)) if x)


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
    misma pregunta. Si ya salió bastante, se quita y se queda lo que el cliente pidió. Son textos nuestros, fijos, no del cliente.
    CALN-43 paso 5: la lista es una sola (`origen_precio.en_lugar_de_la_pregunta_del_origen`), con la de antes del precio."""
    from src.agents import conversational_core as core  # lazy
    from src.agents.nucleo.origen_precio import en_lugar_de_la_pregunta_del_origen  # lazy

    resto_por_pregunta = en_lugar_de_la_pregunta_del_origen()
    fija = next((p for p in resto_por_pregunta if p in respuesta), None)
    if fija is None:
        return respuesta
    # Tras los dos enlaces, lo que queda en su lugar es la indicación de cuál usar.
    sin = respuesta.replace(fija, resto_por_pregunta[fija]).rstrip()
    accion = que_preguntar.que_hacer(core.SLOT_LOCATION, _veces_preguntada(state, core.SLOT_LOCATION),
                                     hay_respuesta=len(_palabras(sin)) >= _PALABRAS_DE_UNA_RESPUESTA)
    if accion == que_preguntar.PREGUNTAR:
        _contar_la_pregunta(state, core.SLOT_LOCATION)
        return respuesta
    if accion == que_preguntar.LAS_DOS_SALIDAS and (salidas := _las_dos_salidas(state, sin)):
        return salidas
    logger.info(f"[CORE][CALN43] compositor: el origen ya salió {_VECES_MAX} veces sin contestarse: no sale otra")
    return _sin_la_pregunta(state, sin)


def _sin_estos_textos(respuesta: str, textos: list[str]) -> tuple[bool, str]:
    """(si había alguno, la respuesta sin ellos). Las preguntas del turno son textos nuestros (`ask_slot`), y desde CALN-43 el
    escritor no las escribe: se buscan tal cual, no parecidas (antes, `_sin_las_preguntas` y `_sin_las_frases_de` buscaban las que
    el escritor redactaba a su manera)."""
    cuerpo = respuesta
    for texto in textos:
        cuerpo = cuerpo.replace(texto.strip(), "")
    if cuerpo == respuesta:
        return False, respuesta
    return True, _PARRAFO.join(p.strip() for p in re.split(r"\n\s*\n", cuerpo) if p.strip())


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
    preguntas = [(slot, texto) for slot, texto in (getattr(state, "_preguntas_del_turno", None) or []) if texto]
    pendiente = state.core_pending_slot
    final = next((texto for slot, texto in reversed(preguntas) if slot == pendiente), None)
    if final is None and not pase:
        # Mini 0.58 (semana-santa): una pregunta del turno ya contestada no se queda; sin pendiente, no se toca nada.
        viejas = [texto for slot, texto in preguntas if pendiente and slot != pendiente]
        return _sin_estos_textos(respuesta, viejas)[1] if viejas else respuesta
    quitada, cuerpo = _sin_estos_textos(respuesta, [texto for _, texto in preguntas])
    if not quitada:
        return respuesta  # no la llevaba (una tarjeta, un pase): no se toca
    logger.info(f"[CORE][CALN6] compositor: {len(respuesta)} → {len(cuerpo)} caracteres sin las preguntas del turno "
                f"({[slot for slot, _ in preguntas]}), pendiente {pendiente!r}, pase {pase}")
    if pase:
        return cuerpo  # en un pase sigue una persona
    # CALN-43 (decisión de Gadea, 6-nov): en la reserva la nuestra va siempre, aunque el escritor pregunte otra cosa (no debe).
    accion = que_preguntar.que_hacer(pendiente, _veces_preguntada(state, pendiente),
                                     hay_respuesta=len(_palabras(cuerpo)) >= _PALABRAS_DE_UNA_RESPUESTA)
    if accion == que_preguntar.PREGUNTAR:
        _contar_la_pregunta(state, pendiente)
        return f"{cuerpo.rstrip()}{_PARRAFO}{final}" if cuerpo.strip() else final
    if accion == que_preguntar.LAS_DOS_SALIDAS and (salidas := _las_dos_salidas(state, cuerpo)):
        return salidas
    logger.info(f"[CORE][CALN43] compositor: {pendiente!r} ya salió {_VECES_MAX} veces sin contestarse: no sale otra")
    return _sin_la_pregunta(state, cuerpo)
