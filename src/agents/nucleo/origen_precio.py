"""El origen antes del precio (CALN-8 (5), 5-nov): la puerta que no cotiza sin saber desde dónde sale el cliente
(`_origen_antes_del_precio`, `_puerta_del_origen`), las dos variantes del catálogo cuando no se sabe (ord-7,
`_dos_variantes`), la pieza de precios por código (`_precios_por_codigo`, `_con_la_pieza`), la pregunta del origen que se
guarda (`_fijar_origen_antes_del_precio`) y cómo se reconoce en una respuesta que ya la hace.

Movido tal cual desde `conversational_core.py`, que lo re-exporta. Ver `src/agents/nucleo/__init__.py`.
"""

from __future__ import annotations

import logging
import re

from src.agents.conversational_core import (
    _CONFIRMA_ORIGEN,
    SLOT_LOCATION,
    _jev_dice_el_lugar,
    _jev_dice_que_no_lo_dice,
    ask_slot,
)
from src.domain import activities as dom
from src.flows import cart_render, moneda
from src.flows.como_reserva import ENLACE, como_reserva, hotel_conocido
from src.flows.state import ConversationState

logger = logging.getLogger("uvicorn.error")


# 6-oct (flag `rag_origen_pregunta`): con el origen desconocido el RAG pregunta ya "¿saldrías desde Cartagena o ya
# estás en las islas?"; si detrás se pegaba la pregunta del origen de la reserva, el cliente leía la misma pregunta dos
# veces seguidas.
# Solo se mira cuando la reserva iba a preguntar justo el origen (`SLOT_LOCATION`), así que basta con reconocer las
# formas de preguntarlo ("¿desde dónde prefieren salir?", "¿saldrían desde Cartagena o ya están en las islas?").
_PREGUNTA_ORIGEN_RE = re.compile(
    r"desde d[oó]nde|(sal|part)\w* desde cartagena o|(depart|leav)\w* from cartagena or|"
    r"where (would|will|do) you (be )?(depart|leav|start)|cartagena or (are you |you're )?already",
    re.IGNORECASE,
)


def _answer_asks_the_origin(state: ConversationState, answer: str) -> bool:
    """¿La reserva iba a preguntar el origen y la respuesta del RAG ya lo pregunta? Entonces va sola."""
    return state.core_pending_slot == SLOT_LOCATION and bool(_PREGUNTA_ORIGEN_RE.search(answer))


def _cierra_preguntando_el_origen(state: ConversationState, answer: str) -> bool:
    """lat-9 paso 2 (LAT-0b, #2053): sin el origen, el escritor da los dos precios y lo pregunta (decisión
    «origen-y-precio»). Esa pregunta ocupa el turno, sea cual sea la pendiente de la reserva, que queda para el
    siguiente; pegarle detrás la otra eran dos preguntas seguidas («¿Desde dónde saldrías? … ¿Eres buzo certificado?»).
    Solo si el origen SIGUE sin saberse: si el cliente lo acaba de dar, esa pregunta es la fijada al empezar el turno y
    está desfasada (integra6: 4 «vuelve a preguntar desde dónde saldría» tras decirlo); la cambia el código."""
    if state.location or state.detected_location:
        return False
    ultima = next((ln for ln in reversed(answer.strip().splitlines()) if ln.strip()), "")
    return "?" in ultima and bool(_PREGUNTA_ORIGEN_RE.search(ultima))


# 7-oct (Álvaro, opción C del punto 3; flag `rag_origen_pregunta`): si el cliente pide un PRECIO y no sabemos desde
# dónde sale, el bot pregunta el origen ANTES de cotizar (lo pide el golden) y lo hace el CÓDIGO, no el modelo: con
# instrucciones en el contexto del RAG (6-oct, V1 y V2) o repreguntaba lo que el cliente ya había dado a entender o
# volvía a cotizar Cartagena. La pregunta del precio se guarda y se contesta en cuanto el cliente dice el origen.
ORIGEN_ANTES_DEL_PRECIO_ES = (
    "Para darte el precio exacto necesito saber desde dónde sales: ¿saldrías *desde Cartagena* o ya estás *en las "
    "Islas del Rosario*? Los planes y los precios cambian según el punto de salida. 🌊"
)
ORIGEN_ANTES_DEL_PRECIO_EN = (
    "To give you the exact price I need to know where you're starting from: would you leave *from Cartagena* or are "
    "you already *on the Rosario Islands*? Plans and prices change depending on the departure point. 🌊"
)
_PIDE_PRECIO_RE = re.compile(
    r"cu[aá]nto (cuesta|cuestan|vale|valen|sale|salen|cobran|ser[ií]a|es\b)|\bprecios?\b|\bcostos?\b|\bcoste\b|"
    r"\btarifas?\b|\bvalor\b|how much|\bprices?\b|\bcosts?\b|\brates?\b|\bfees?\b",
    re.IGNORECASE,
)
# El precio de algo que no vendemos (el hotel, la noche) no depende de desde dónde sale el cliente.
_PRECIO_AJENO_RE = re.compile(
    r"hotel|alojamiento|hospedaje|por noche|la noche|habitaci|taxi|\bnights?\b|\brooms?\b|accommodation|lodging",
    re.IGNORECASE,
)
# Pistas del origen en lo que ha escrito el CLIENTE (el saludo del bot nombra los dos orígenes). Si el cliente ya
# nombró Cartagena o las islas, el origen se deja al RAG como siempre: preguntarlo sería repreguntar (lección de V1).
_PISTA_ORIGEN_RE = re.compile(r"cartagena|\bislas?\b|\bislands?\b|bar[uú]|tierra bomba", re.IGNORECASE)


# 7-oct (Gonzalo, ronda core origen-c-B): la puerta mira la RESPUESTA, no solo la pregunta. Mirando solo la pregunta
# fallaba por los dos lados: "Amigo el precio que está allí es en dólares o pesos?" (dice "precio", pero pregunta la
# MONEDA; antes se contestaba y con la puerta se quedaba sin respuesta) y "Gracias - y en pesos?" (pide un importe sin
# ninguna palabra de precio; el RAG cotizaba Cartagena). La regla de la opción C es "no cotizar sin origen": se
# comprueba justo eso, que la respuesta lleve un importe.
_IMPORTE_RE = re.compile(
    r"\d[\d.,]*\s*(?:cop|usd|us\$|d[oó]lares|dollars|pesos)\b|(?:usd|cop|us\$|\$)\s*\d",
    re.IGNORECASE,
)


def _origen_antes_del_precio(state: ConversationState, message: str, answer: str | None) -> str | None:
    """El texto fijo que pregunta el origen, si la respuesta del RAG (`answer`) cotiza sin saber desde dónde sale el
    cliente; si no, None (y la respuesta va tal cual).

    Cotiza = lleva un importe, y el cliente pide un precio o repregunta tras la pregunta del origen sin contestarla
    ("¿y en pesos?"). Un importe en la respuesta a otra cosa ("¿qué incluye?") se deja como hoy."""
    if state.location or state.detected_location:
        return None
    if _jev_dice_el_lugar(state):
        # gen-15: la puerta mira el origen antes de que la extracción del turno lo guarde, y sus pistas son palabras
        # («Cartagena», «islas», «Barú»): «We booked 3 nights at Mulata. How much is snorkeling?» se repreguntaba 2/2
        # con Jev seguro (islands 0,97). Si Jev está seguro de dónde está el cliente, el mensaje ya lo dice.
        return None
    texto = message or ""
    # ord-7: un enlace de reserva también depende del origen («mándame el enlace del Open Water» daba el de Cartagena).
    da_enlace = bool(answer) and "book.divingplanet.org" in answer
    if not answer or not (_IMPORTE_RE.search(answer) or da_enlace):
        return None
    jev = getattr(state, "_jev_pide_precio", None)
    if jev is not None:
        # ex-9b paso 5: Jev dice si pide el precio de NUESTRAS actividades (el hotel, la noche o un taxi no cuentan);
        # las palabras sueltas solo si Jev calla. "Me quedo en el hotel Caribe" ya no salta la puerta.
        pide = jev is True
    elif _PRECIO_AJENO_RE.search(texto):
        return None
    else:
        pide = bool(_PIDE_PRECIO_RE.search(texto))
    if not (pide or state.pregunta_precio_pendiente or da_enlace):
        return None
    del_cliente = [h.get("content") or "" for h in (state.history or []) if h.get("role") == "user"]
    este = [texto]
    if _jev_dice_que_no_lo_dice(state):
        # CAL-C3c: "bucear en islas del rosario" nombra las islas sin decir dónde está el cliente (cal-71/73); si Jev
        # está seguro de que ESTE mensaje no dice su origen, sus palabras no cuentan como pista y se pregunta antes de
        # cotizar. El mensaje ya está en el historial cuando contesta el RAG: se quita de ahí también.
        este = []
        if del_cliente and del_cliente[-1] == texto:
            del_cliente = del_cliente[:-1]
    if any(_PISTA_ORIGEN_RE.search(t) for t in [*del_cliente, *este]):
        return None
    pregunta = ORIGEN_ANTES_DEL_PRECIO_ES if state.language == "es" else ORIGEN_ANTES_DEL_PRECIO_EN
    por_confirmar = (state.pending_correction or {}).get("location")
    if por_confirmar in _CONFIRMA_ORIGEN:
        # ORIGEN-CONFIRMA: el extractor leyó un origen que falta confirmar; se pregunta eso, no «¿desde dónde?».
        pregunta = _CONFIRMA_ORIGEN[por_confirmar]["es" if state.language == "es" else "en"]
    con_enlaces = da_enlace and como_reserva(state) == ENLACE  # CALN-35
    variantes = _dos_variantes(state, answer, con_enlace=con_enlaces)
    if variantes:
        tras = (ORIGEN_TRAS_LOS_ENLACES_ES, ORIGEN_TRAS_LOS_ENLACES_EN) if con_enlaces else (
            ORIGEN_TRAS_LAS_VARIANTES_ES, ORIGEN_TRAS_LAS_VARIANTES_EN)
        pregunta = f"{variantes}\n\n{tras[0] if state.language == 'es' else tras[1]}"
    elif not da_enlace and _cotiza_los_dos_origenes(state, answer):
        # 27-oct (decisión de Gadea del 26-oct, «origen-y-precio»: sin el origen, dos precios y pregunta): sin variantes
        # del catálogo (paquetes y planes de buzo con varios planes por origen) se quitaban todos los importes y quedaba
        # solo la pregunta, aunque el escritor hubiera dado el precio de cada origen (4-5 criterios por ronda en
        # integra4-6: «preguntó el origen pero no cotizó»). Si los da los dos, se dejan y detrás va la pregunta; si da
        # uno solo, o un enlace (el de una sola salida), se quitan como antes.
        cuerpo = _sin_la_pregunta_final(answer) if _cierra_preguntando_el_origen(state, answer) else answer
        tras = ORIGEN_TRAS_LAS_VARIANTES_ES if state.language == "es" else ORIGEN_TRAS_LAS_VARIANTES_EN
        return f"{cuerpo.rstrip()}\n\n{tras}"
    resto = _sin_importes(answer)
    return f"{resto}\n\n{pregunta}" if resto else pregunta


# s4-31 (8-oct, flag `origen_conserva_respuesta`): en la ronda del golden visible con Luna (`2026-10-08-luna-visible`),
# 6 de los 33 fallos del RAG eran de la puerta del origen: la pregunta fija SUSTITUÍA la respuesta entera y se perdía lo
# que no era el precio ("no hay precio especial para colombianos, solo cambia la moneda", "con 1,5 años no hace falta
# el refresher", "el refresher tiene el coste del minicurso"). Ahora se quitan solo las frases con un importe y la
# pregunta final de la respuesta (la sustituye la del origen); si no queda nada que decir, solo la pregunta.
_FRASE_RE = re.compile(r"(?<=[.!?])\s+")
# Escalón 0 en PRE (8-oct): además del importe dependen del origen el link de reserva (uno por origen: se dejaba el de
# Cartagena mientras se preguntaba el origen) y lo que incluye ("Incluye lancha ida y vuelta y almuerzo" es solo de
# Cartagena, y sin la frase del precio se quedaba sin sujeto).
_DEPENDE_DEL_ORIGEN_RE = re.compile(
    rf"{_IMPORTE_RE.pattern}|book\.divingplanet\.org|^\W*(?:esto |el plan |el curso |el paquete )?(?:incluye|includes|it includes)\b"
    r"|desde cartagena|from cartagena|cartagena-islas|islands-cartagena|almuerzo|\blunch\b",
    re.IGNORECASE,
)


def _sin_importes(answer: str) -> str:
    lineas = []
    for linea in (answer or "").splitlines():
        if not _DEPENDE_DEL_ORIGEN_RE.search(linea):
            lineas.append(linea)
            continue
        frases = [f for f in _FRASE_RE.split(linea) if f.strip() and not _DEPENDE_DEL_ORIGEN_RE.search(f)]
        if frases:
            lineas.append(" ".join(frases))
        else:
            # El título de una lista que se ha quitado entera ("los precios son:"). gen-6 (21-oct): "La salida de 2
            # inmersiones cuesta:", una línea en blanco y la lista de precios dejaba el título colgado ("…cuesta:" y
            # luego la pregunta del origen): el título se busca saltando las líneas en blanco.
            ultima = len(lineas) - 1
            while ultima >= 0 and not lineas[ultima].strip():
                ultima -= 1
            if ultima >= 0 and lineas[ultima].rstrip().endswith(":"):
                del lineas[ultima:]
    # La pregunta final (casi siempre "¿quieres el link / que te ayude a reservar?") la sustituye la del origen.
    while lineas and not lineas[-1].strip():
        lineas.pop()
    if lineas:
        frases = _FRASE_RE.split(lineas[-1].strip())
        while frases and "?" in frases[-1]:
            frases.pop()
        lineas[-1] = " ".join(frases)
    texto = re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).strip()
    return texto if len(texto) >= 40 else ""


def _preguntas_fijas_del_origen() -> tuple[str, ...]:
    return (ORIGEN_ANTES_DEL_PRECIO_ES, ORIGEN_ANTES_DEL_PRECIO_EN, ORIGEN_TRAS_LAS_VARIANTES_ES, ORIGEN_TRAS_LAS_VARIANTES_EN,
            ORIGEN_TRAS_LOS_ENLACES_ES, ORIGEN_TRAS_LOS_ENLACES_EN)


def _es_pregunta_de_origen(answer: str | None) -> bool:
    return bool(answer) and any(p in answer for p in _preguntas_fijas_del_origen())


def en_lugar_de_la_pregunta_del_origen() -> dict[str, str]:
    """CALN-43, qué preguntar, paso 5: cada pregunta fija del origen, en un sitio, y lo que queda en su lugar cuando ya salió 2 veces
    (`que_preguntar`). Todas son la pregunta del origen y cuentan como ella; también la confirmación de ORIGEN-CONFIRMA. Antes
    faltaba la de antes del precio: no se contaba y podía salir una 3.ª vez."""
    return {**{texto: "" for texto in _preguntas_fijas_del_origen()},
            **{texto: "" for por_idioma in _CONFIRMA_ORIGEN.values() for texto in por_idioma.values()},
            ORIGEN_TRAS_LOS_ENLACES_ES: SIN_ENLACE_DE_LAS_ISLAS_ES, ORIGEN_TRAS_LOS_ENLACES_EN: SIN_ENLACE_DE_LAS_ISLAS_EN}


# ord-7 (21-oct, flag `origen_dos_variantes`, decisión de Gadea con ord-0): sin saber el origen, la puerta quitaba el
# precio, lo que incluye, el almuerzo y el enlace, y el cliente se quedaba sin nada de lo que preguntó (g10-029: «¿hay
# comida?», g9-003: «¿qué incluye?»). Con las dos variantes del catálogo se contesta sin suponer el origen; la pregunta
# del origen va después, para el enlace y el plan exacto.
ORIGEN_TRAS_LAS_VARIANTES_ES = "¿Saldrías *desde Cartagena* o ya estás *en las Islas del Rosario*? Así te paso el plan exacto. 🌊"
ORIGEN_TRAS_LAS_VARIANTES_EN = "Would you leave *from Cartagena* or are you already *on the Rosario Islands*? Then I'll give you the exact plan. 🌊"
SIN_ENLACE_DE_LAS_ISLAS_ES = "Si sales desde las islas, antes necesito saber tu hotel."
SIN_ENLACE_DE_LAS_ISLAS_EN = "If you're leaving from the islands, I first need to know your hotel."
ORIGEN_TRAS_LOS_ENLACES_ES = f"{SIN_ENLACE_DE_LAS_ISLAS_ES} ¿Saldrías *desde Cartagena* o ya estás *en las Islas del Rosario*? 🌊"
ORIGEN_TRAS_LOS_ENLACES_EN = f"{SIN_ENLACE_DE_LAS_ISLAS_EN} Would you leave *from Cartagena* or are you already *on the Rosario Islands*? 🌊"
_VARIANTE = {
    "es": {"cartagena": ("Desde Cartagena", "lancha ida y vuelta desde el Muelle de la Bodeguita"),
           "island": ("Ya en las islas", "recogida en tu hotel si tiene acceso marítimo"),
           "titulo": "{actividad}, según desde dónde salgas (precio online por persona):",
           "con_almuerzo": "almuerzo incluido", "sin_almuerzo": "sin almuerzo"},
    "en": {"cartagena": ("From Cartagena", "round-trip boat from Muelle de la Bodeguita"),
           "island": ("Already on the islands", "pickup at your hotel if it has sea access"),
           "titulo": "{actividad}, depending on where you start from (online price per person):",
           "con_almuerzo": "lunch included", "sin_almuerzo": "no lunch"},
}


def _dos_variantes(state: ConversationState, answer: str = "", con_enlace: bool = False) -> str | None:
    """Las dos salidas de la actividad de la que pregunta el cliente, del catálogo: precio online por persona en su
    moneda (`src/flows/moneda.py`), el transporte y si lleva almuerzo. None si
    no hay una actividad concreta con un solo plan por origen (los paquetes de buceo tienen varios) o si el importe que
    dio el RAG (`answer`) no es de ninguna de las dos: la actividad anotada no era la cotizada (banco ord-7: «tengo el
    Open Water, ¿cuánto cuesta el repaso?» anotaba el Open Water y salían los precios del curso). `con_enlace`: cada
    variante lleva su enlace de reserva (el RAG había dado uno sin saber el origen)."""
    from src.flows.catalog import SERVICES  # lazy

    actividad = state.actividad_preguntada or state.detected_activity or state.suggested_activity
    if not actividad:
        return None
    servicios = []
    for origen in ("cartagena", "island"):
        ids = dom.service_ids(actividad, origen)
        servicio = SERVICES.get(ids[0]) if len(ids) == 1 else None
        if not servicio:
            return None
        servicios.append((origen, servicio))
    if answer and not _cotiza_alguno(answer, [s for _, s in servicios]) and not _enlaza_alguno(answer, servicios, state):
        return None
    lang = "es" if state.language == "es" else "en"
    textos = _VARIANTE[lang]
    lineas = [textos["titulo"].format(actividad=f"*{dom.label(actividad, lang)}*")]
    for origen, servicio in servicios:
        precio = moneda.precio(state, servicio.get("price_usd"), servicio.get("price_cop"))
        if not precio:
            return None
        nombre, transporte = textos[origen]
        almuerzo = textos["con_almuerzo" if "almuerzo" in (servicio.get("includes_es") or "").lower() else "sin_almuerzo"]
        linea = f"• *{nombre}*: {precio}, {transporte}; {almuerzo}."
        # CALN-35: el de las islas, cuando diga su hotel.
        url = (cart_render._resolve_service_booking_url(servicio, state)
               if con_enlace and (origen != "island" or hotel_conocido(state)) else None)
        lineas.append(f"{linea} {url}" if url else linea)
    return "\n".join(lineas)


def _cotiza_los_dos_origenes(state: ConversationState, answer: str) -> bool:
    """¿La respuesta da un precio de algún plan de la actividad desde Cartagena Y otro de algún plan ya en las islas?
    Con los datos del catálogo, no con palabras."""
    from src.flows.catalog import SERVICES  # lazy

    actividad = state.actividad_preguntada or state.detected_activity or state.suggested_activity
    if not actividad or not answer:
        return False
    por_origen = [[SERVICES[s] for s in dom.service_ids(actividad, origen) if s in SERVICES]
                  for origen in ("cartagena", "island")]
    return all(servicios and _cotiza_alguno(answer, servicios) for servicios in por_origen)


def _enlaza_alguno(answer: str, servicios: list[tuple[str, dict]], state: ConversationState) -> bool:
    """¿La respuesta lleva el enlace de reserva de alguna de las dos variantes?"""
    urls = (cart_render._resolve_service_booking_url(s, state) or "" for _, s in servicios)
    return any(u and u.split("?")[0] in answer for u in urls)


def _precios_por_codigo(state: ConversationState, entradas: dict) -> bool:
    """CALN-19 (4-nov, sparring s04g y s04e): en un mensaje mezclado que pide precio, el escritor del RAG escribía los
    importes y `con_la_pieza` se llevaba las frases que nombran cada plan: «It requires an overnight stay… That course
    takes two days…», sin decir de qué plan. Como en el redactor de hechos (paso 3 «A»), se le dice ANTES que no los
    escriba (`RAG_PRECIOS_POR_CODIGO`) y la pieza va debajo, con la misma condición (`pide_ahora`). True si es el caso."""
    bloques, intenciones = entradas.get("hechos_bloques") or (None, ())
    if "precio" not in intenciones:
        return False
    if getattr(state, "_jev_pide_precio", None) is not True and not any(b.get("origen") for b in bloques):
        return False
    entradas.update(precios_por_codigo=True, hechos_bloques=(bloques, [i for i in intenciones if i != "precio"]))
    return True


def _puerta_del_origen(state: ConversationState, message: str, answer: str, sin_precio: bool = False,
                       pieza_pedida: bool = False) -> str:
    """La respuesta del RAG tras la puerta del origen (opción C): la pregunta del origen (con las dos variantes, ord-7)
    si cotiza o enlaza sin saber el origen; si no, la respuesta tal cual. gen-19 (21-oct) añadía aquí el enlace cuando
    tocaba; se quitó por decisión de Gadea: en su banco no cambiaba nada (el enlace ya salía cuando lo piden). ord-9
    (la lista de qué incluye, de la ficha) se retiró en arq-2c (22-oct): la da el redactor de hechos.

    CALN-3 paso 4 (1): antes, si la respuesta cotiza, sus importes los cambia la pieza de precios (`_con_la_pieza`)."""
    if not sin_precio and (con_pieza := _con_la_pieza(state, answer, pieza_pedida)):
        return con_pieza
    return _origen_antes_del_precio(state, message, answer) or answer


def _con_la_pieza(state: ConversationState, answer: str | None, pieza_pedida: bool = False) -> str | None:
    """CALN-3 paso 4 (1) (29-oct, decisión de Gadea #2499): el RAG general aún escribe importes, de las fichas o del
    catálogo, y la puerta los quitaba sin dar otros: en la 5.ª, 12 de las 51 preguntas del origen eran de la puerta
    (caln5-B), casi todas en turnos que Jev no daba por precio («¿cuánto va a subir?», el coste del refresher). Ahora, si
    la respuesta da un precio del catálogo, fuera sus frases con importes y debajo la pieza de `cotizar`, como en el
    redactor de hechos (paso 3 «A»): sin el origen, los dos y la pregunta (o la confirmación de CALN-3b). None si no
    cotiza o no hay pieza (la puerta de siempre)."""
    from src.agents import redactor_hechos  # lazy
    from src.agents.nucleo.extractor import origen_por_confirmar  # lazy
    from src.flows import cotizar  # lazy
    from src.flows.catalog import SERVICES  # lazy

    if not answer:
        return None
    if not pieza_pedida and not (_IMPORTE_RE.search(answer) and _cotiza_alguno(answer, list(SERVICES.values()))):
        return None
    lang = "es" if state.language == "es" else "en"

    def cifras(texto: str) -> set[str]:
        return {re.sub(r"\D", "", c) for c in re.findall(r"\d[\d.,]*", texto)}

    def de_servicio(s: dict) -> set[str]:
        return {str(round(float(s[k]))) for k in ("price_usd", "price_usd_normal", "price_cop", "price_cop_normal")
                if s.get(k)}

    dados = cifras(answer) & set().union(*(de_servicio(s) for s in SERVICES.values()))
    # Con la pieza pedida, los hechos que ya tiene el escritor (lo que dice ESTE mensaje, `_foto`), salvo que al recoger la
    # respuesta en paralelo la extracción ya haya guardado el origen que esos hechos no sabían.
    bloques = cotizar.bloques_de_precio(state)[1]
    if pieza_pedida and not (state.location and not any(b.get("origen") for b in state._hechos_del_rag[0])):
        bloques = state._hechos_del_rag[0]
    pieza = cotizar.pieza_de_precios(bloques, lang)
    if not pieza or not dados <= cifras(pieza):
        # Cotiza otro plan que el del estado («quiero reservar el paquete de 5 buceos» con la salida de 2 de base, o el
        # refresher de un buzo, que se cobra como el minicurso): la pieza, de los planes que cotizó (medida caln6-B1:
        # eran los 2 turnos en que aún saltaba la puerta).
        suyos = cotizar.bloques_de_los_servicios(state, [sid for sid, s in SERVICES.items() if de_servicio(s) & dados])
        la_suya = cotizar.pieza_de_precios(suyos, lang)
        # Con el origen sabido, sus bloques ya son de su salida: si el escritor da el importe de la otra (belgas de CALN-35: 392 USD,
        # el de Cartagena, a quien sale de las islas, 319), no cuadra porque él se equivoca. Manda la pieza, y sigue siendo la lista del
        # estado si ese plan ya está en ella. Sin esto se quedaba su importe.
        con_origen = any(b.get("origen") for b in suyos)
        if not (pieza and la_suya and con_origen and cifras(la_suya) <= cifras(pieza)):
            bloques, pieza = suyos, la_suya
            if not pieza or not (dados <= cifras(pieza) or con_origen):
                return None
    logger.info("[CORE][CALN3] el RAG general cotiza: sus importes, fuera; debajo, la pieza de precios")
    if any(b.get("origen") for b in bloques):
        return redactor_hechos.con_la_pieza(answer, pieza)
    pregunta = ORIGEN_TRAS_LAS_VARIANTES_ES if lang == "es" else ORIGEN_TRAS_LAS_VARIANTES_EN
    if por_confirmar := origen_por_confirmar(state):
        pregunta = _CONFIRMA_ORIGEN[por_confirmar][lang]
    # Sin el origen, fuera también sus enlaces de reserva (uno por origen: medida caln6-B1, el del snorkel y el del
    # minicurso de Cartagena sin saber de dónde sale), como hacía la puerta; la pregunta promete el enlace exacto.
    answer = "\n".join(" ".join(f for f in _FRASE_RE.split(linea) if "book.divingplanet.org" not in f)
                       if "book.divingplanet.org" in linea else linea for linea in answer.splitlines())
    # La pregunta con que cierra el RAG («¿te paso el enlace?») la sustituye la del origen, como en la puerta.
    partes = [p for p in answer.rstrip().split("\n\n") if p.strip()]
    frases = _FRASE_RE.split(partes[-1].strip())
    while frases and "?" in frases[-1]:
        frases.pop()
    cuerpo = "\n\n".join(p for p in [*partes[:-1], " ".join(frases)] if p.strip())
    return f"{redactor_hechos.con_la_pieza(cuerpo, pieza) if cuerpo else pieza}\n\n{pregunta}"


def _cotiza_alguno(answer: str, servicios: list[dict]) -> bool:
    """¿Alguna cifra de la respuesta es un precio (online o normal, USD o COP) de estos servicios? Todas las cifras, no
    solo los `_IMPORTE_RE`: ese corta «$124 USD» en «$1»."""
    precios = {str(round(float(s[k]))) for s in servicios
               for k in ("price_usd", "price_usd_normal", "price_cop", "price_cop_normal") if s.get(k)}
    return any(re.sub(r"\D", "", cifra) in precios for cifra in re.findall(r"\d[\d.,]*", answer))


def _fijar_origen_antes_del_precio(state: ConversationState, pregunta: str) -> None:
    """La pregunta del origen ocupa el turno: queda pendiente el origen (con los botones de siempre) y se guarda la
    pregunta del precio para contestarla cuando el cliente lo diga."""
    ask_slot(state, SLOT_LOCATION)  # solo por lo que deja en el estado: el slot pendiente y sus botones
    anterior = state.pregunta_precio_pendiente
    if anterior and not _pide_precio(state, pregunta):
        # arq-8f (banco arq-8c de Gadea, #1667): con una pregunta de precio guardada, «soy de Medellín» (no dice el origen)
        # vuelve a pedirlo y pisaba la pregunta con ese mensaje; luego se contestaba «soy de Medellín». Se queda la de
        # antes, salvo que este mensaje pregunte otro precio.
        pregunta = anterior
    state.pregunta_precio_pendiente = pregunta
    logger.info("[CORE][ORIGEN] precio sin origen -> se pregunta el origen antes de cotizar")


def _pide_precio(state: ConversationState, mensaje: str) -> bool:
    """¿Este mensaje pide un precio? Lo dice Jev (ex-9b paso 5); si calla, las palabras de siempre."""
    jev = getattr(state, "_jev_pide_precio", None)
    if jev is not None:
        return jev is True
    return bool(_PIDE_PRECIO_RE.search(mensaje or "")) and not _PRECIO_AJENO_RE.search(mensaje or "")


def _answer_already_asks(answer: str) -> bool:
    """¿La respuesta ya termina invitando a responder (cierra con una
    pregunta)? Mira la última línea no vacía — así una recomendación que
    acaba en "¿te inclinas por alguna?" no recibe encima el re-prompt del
    slot. Barato y seguro: un falso negativo solo re-adjunta la variante
    corta, nunca vuelve al bloque entero."""
    for line in reversed(answer.strip().splitlines()):
        if line.strip():
            return "?" in line or "¿" in line
    return False


def _sin_la_pregunta_final(answer: str) -> str:
    """El texto del escritor sin su último párrafo si es una pregunta (lat-9 paso 2: la de la reserva la escribe ahí,
    aparte): cuando la pregunta que toca es otra, el código pone la buena."""
    partes = answer.rstrip().split("\n\n")
    return "\n\n".join(partes[:-1]) if len(partes) > 1 and "?" in partes[-1] else answer
