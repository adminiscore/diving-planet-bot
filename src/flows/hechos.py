"""ARQ-1c (22-oct, fase ARQ: el modelo interpreta, el código decide, el modelo redacta): los HECHOS de cada intención.

Diseño: `docs/robustness/arq/diseno-intenciones-y-hechos.md`. Para cada actividad de la que pregunta el cliente y cada
intención (precio, qué incluye, requisitos, horario, disponibilidad, edad, enlace), el código saca de la base los
datos con las reglas del negocio YA aplicadas: la moneda según la nacionalidad, las dos variantes si no se sabe el
origen, las edades en cifra, el asesor en el cierre de un colombiano. El redactor (arq-1d) solo los pone en palabras:
no elige ni calcula, y no recibe el catálogo entero (el 21-oct, con el catálogo delante, reescribía las listas de
memoria y las recortaba).

Sin llamadas a modelos: solo datos (`catalog.RAW_SERVICES`, la tarifa de `pricing.json` vía `catalog`, `policies.json`
y el registro de actividades).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from src.domain import activities as dom
from src.domain.politicas import politica
from src.flows import cart_render, moneda
from src.flows.catalog import (
    COMPANION_INCLUDES,
    COMPANION_NO_INCLUYE,
    COMPANION_PRICE,
    ISLAND_SERVICE_MAP,
    RAW_SERVICES,
    SERVICES,
    descuentos_de_la_base,
    requisitos_de_politica,
)
from src.flows.state import ConversationState
from src.utils import money
from src.utils.text import strip_accents

INTENCIONES = ("precio", "incluye", "requisitos", "horario", "disponibilidad", "edad", "enlace", "descuento",
               "tiempo", "clima", "pago", "hoteles", "regreso", "fotos", "cambios")
ORIGENES = ("cartagena", "island")
# Las intenciones cuyos hechos cambian según desde dónde sale el cliente: sin origen van las dos variantes.
_DEPENDEN_DEL_ORIGEN = {"precio", "incluye", "horario", "enlace"}
_DISCOUNTS = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "discounts.json"


@lru_cache(maxsize=1)
def _descuento_online(lang: str) -> str | None:
    """El descuento online (10 %, se aplica solo al reservar por la web), de discounts.json: va con el enlace (G10 nº 2:
    daba el enlace sin decir que reservando ahí se aplica el precio online)."""
    datos = json.loads(_DISCOUNTS.read_text(encoding="utf-8-sig")).get("discounts", {})
    online = datos.get("online_direct_booking") or {}
    return online.get(f"description_{lang}") or online.get("description_es")


def _politica(clave: str, lang: str) -> str | None:
    """Una política de la base (lat-deuda-u: del lector único del dominio, `src/domain/politicas.py`)."""
    return politica(clave, lang)


def _dos_monedas(state: ConversationState) -> bool:
    """arq-5c: no se sabe si paga en COP (ni es un grupo mixto, que paga en USD). La regla, en `src/flows/moneda.py`."""
    return len(moneda.monedas(state)) == 2


def _moneda(state: ConversationState) -> str:
    """La moneda principal del bloque: COP a colombianos y residentes; USD al resto (sin nacionalidad, también va el
    precio en COP: `_dos_monedas`)."""
    return "COP" if moneda.monedas(state) == ("COP",) else "USD"


def _plan_base(actividad: str, origen: str, elegido: str | None = None) -> str | None:
    """El plan de la actividad en ese origen: el que el cliente eligió o se detectó en la conversación (arq-1k: «¿qué
    incluye?» del paquete de 5 inmersiones recibía lo de la salida de 2, G10 nº 2) y, si no, el base (en el buceo, la
    salida de 2 inmersiones) y, en las islas, su variante. En las islas el primero del registro es la salida de 1
    inmersión: «¿la salida de dos inmersiones?» desde Majagua recibía 97 USD de base (banco arq-1d, p4)."""
    ids = dom.service_ids(actividad, origen)
    if elegido:
        propio = ISLAND_SERVICE_MAP.get(elegido, elegido) if origen == "island" else _DE_LAS_ISLAS.get(elegido, elegido)
        if propio in ids:
            return propio
    base = dom.base_service_id(actividad)
    if origen == "island" and ISLAND_SERVICE_MAP.get(base) in ids:
        return ISLAND_SERVICE_MAP[base]
    return ids[0] if ids else None


_DE_LAS_ISLAS = {isla: cartagena for cartagena, isla in ISLAND_SERVICE_MAP.items()}


def _precio(sid: str, moneda: str) -> dict | None:
    s = SERVICES.get(sid) or {}
    if moneda == "COP":
        online, normal = money.cop(s.get("price_cop")), money.cop(s.get("price_cop_normal"))
    else:
        online, normal = money.usd(s.get("price_usd")), money.usd(s.get("price_usd_normal"))
    return {"online": online, "normal": normal} if online else None


def _nombre(sid: str, lang: str) -> str:
    return (SERVICES.get(sid) or {}).get(f"name_{lang}") or sid


def _precio_del_plan(sid: str, moneda: str, lang: str) -> dict | None:
    """El precio con el nombre de su plan: sin él, «¿la salida de dos inmersiones?» desde las islas recibía 124 USD sin
    decir de qué plan eran y el redactor, con razón, no lo daba (banco arq-1d F, p4)."""
    precio = _precio(sid, moneda)
    return {"plan": _nombre(sid, lang), **precio} if precio else None


def _lista(sid: str, campo: str, lang: str) -> list[str]:
    s = RAW_SERVICES.get(sid) or {}
    return list(s.get(f"{campo}_{lang}") or s.get(f"{campo}_es") or [])


def _por_origen(actividad: str, origenes: tuple[str, ...], fn, elegido: str | None = None) -> dict:
    out = {}
    for origen in origenes:
        sid = _plan_base(actividad, origen, elegido)
        valor = fn(sid) if sid else None
        if valor:
            out[origen] = valor
    return out


def hechos(state: ConversationState, intenciones: list[str], actividades: list[str]) -> list[dict]:
    """Un bloque de hechos por actividad, con solo las intenciones pedidas (y las que el registro sabe dar)."""
    lang = "es" if state.language == "es" else "en"
    origen = state.location if state.location in ORIGENES else None
    origenes = (origen,) if origen else ORIGENES
    moneda = _moneda(state)
    pedidas = [i for i in intenciones if i in INTENCIONES]
    elegido = state.selected_service or getattr(state, "detected_service_id", None)
    # arq-1t: pide varios días sin plan elegido → los hechos de los paquetes de varios días, no los de la salida de uno.
    # El plan base que se apunta solo al saber la actividad (`detected_service_id`, rutas/booking) no es una elección.
    varios_dias = not state.selected_service and state.detected_duration == "multi_day"
    bloques = []
    for actividad in actividades:
        registro = dom.by_id(actividad)
        if registro is None:
            continue
        detectado = getattr(state, "detected_service_id", None)
        sin_plan = varios_dias and detectado in (None, dom.base_service_id(actividad))
        paquetes = {o: _paquetes_de_varios_dias(actividad, o) for o in origenes} if sin_plan else {}
        paquetes = {o: s for o, s in paquetes.items() if s}
        if paquetes:
            elegido = paquetes.get("cartagena", next(iter(paquetes.values())))[0]  # el primero, como base del precio
        bloque: dict = {"actividad": actividad, "nombre": dom.label(actividad, lang), "origen": origen}
        if registro.cart_type == "companion":
            bloques.append(_acompanante(bloque, pedidas, origen, origenes, moneda, lang, _dos_monedas(state)))
            continue
        if "precio" in pedidas:
            bloque["moneda"] = moneda
            # La regla de la moneda (el precio es el mismo, solo cambia la moneda): «según la página tienen un precio
            # especial para colombianos» recibía los precios en COP sin que nadie dijera que no lo hay (core arq1d-B2).
            mixto = getattr(state, "mixed_nationality_notice", False)
            bloque["regla_moneda"] = _politica("mixed_nationality_group" if mixto else "colombian_pricing", lang)
            bloque["precio"] = _por_origen(actividad, origenes, lambda sid: _precio_del_plan(sid, moneda, lang), elegido)
            base = _plan_base(actividad, origen or "cartagena", elegido)
            otros = [s for s in dom.service_ids(actividad, origen or "cartagena") if s != base]
            if not origen:
                # lat-9 paso 3 (27-oct): sin origen, también los de las islas, cada uno con el suyo. Eran solo los de
                # Cartagena y sin decirlo: «¿cuánto cuesta el paquete de 5 inmersiones?» no tenía su precio en las islas.
                de_las_islas = [ISLAND_SERVICE_MAP.get(s) for s in otros]
                base_islas = _plan_base(actividad, "island", elegido)
                otros += [s for s in de_las_islas if s and s != base_islas and s in dom.service_ids(actividad, "island")]
            if otros:  # el buceo y los paquetes: el plan base y la lista de los demás con su precio
                bloque["otros_planes"] = [{"plan": _nombre(s, lang), "precio": _precio(s, moneda),
                                           **({} if origen else {"origen": "island" if s in _DE_LAS_ISLAS else "cartagena"})}
                                          for s in otros if _precio(s, moneda)]
            if _dos_monedas(state):
                # arq-5c (decisión de Gadea, 23-oct; G10 nº 5, ~6 fallos): sin saber si es colombiano, el precio en las
                # dos monedas, con la regla de siempre (el mismo precio, solo cambia la moneda).
                bloque["moneda"] = "USD / COP"
                bloque["precio_cop"] = _por_origen(actividad, origenes,
                                                   lambda sid: _precio_del_plan(sid, "COP", lang), elegido)
                for plan, sid in zip(bloque.get("otros_planes") or [], [s for s in otros if _precio(s, moneda)],
                                     strict=False):
                    plan["precio_cop"] = _precio(sid, "COP")
            if grupo := _descuento_de_grupo(state, registro, lang):
                bloque["descuento_de_grupo"] = grupo
        if "incluye" in pedidas and paquetes:
            # arq-1t: lo común a todos los paquetes de varios días del origen (solo cambia el número de inmersiones) y
            # la lista de paquetes; lo que NO incluyen, igual (el alojamiento y los almuerzos de los otros días).
            bloque["incluye"] = {o: _comunes([_lista(s, "included", lang) for s in sids]) for o, sids in paquetes.items()}
            no_incluye = {o: _comunes([_lista(s, "not_included", lang) for s in sids]) for o, sids in paquetes.items()}
            if "island" in paquetes:
                no_incluye["island"] = [*no_incluye.get("island", []), _no_incluyen_las_islas(lang)]
            bloque["no_incluye"] = {o: [x for x in v if x] for o, v in no_incluye.items() if any(v)}
            bloque["paquetes"] = {o: [_nombre(s, lang) for s in sids] for o, sids in paquetes.items()}
        elif "incluye" in pedidas:
            bloque["incluye"] = _por_origen(actividad, origenes, lambda sid: _lista(sid, "included", lang), elegido)
            # Lo que NO incluye: de la ficha y, en los planes de las islas (sus fichas no lo traen), de la política de la
            # recogida («no incluyen transporte desde Cartagena ni almuerzo»). Sin esto, «¿hay almuerzo?» desde las
            # islas se quedaba sin contestar (banco arq-1d, v2).
            no_incluye = _por_origen(actividad, origenes, lambda sid: _lista(sid, "not_included", lang), elegido)
            if "island" in origenes and _plan_base(actividad, "island", elegido):
                no_incluye["island"] = [*no_incluye.get("island", []), _no_incluyen_las_islas(lang)]
            if no_incluye:
                bloque["no_incluye"] = no_incluye
            if "horario" not in pedidas:
                # arq-8d: lo que se hace (la clase, la piscina, la inmersión) es lo que el cliente espera oír con «¿qué
                # incluye?», y en la ficha está en el itinerario; con el horario ya va (sin repetirlo).
                que_se_hace = _por_origen(actividad, origenes, lambda sid: _lista(sid, "itinerary", lang), elegido)
                if que_se_hace:
                    bloque["en_que_consiste"] = que_se_hace
        if "requisitos" in pedidas:
            requisitos: list[str] = []
            sid = _plan_base(actividad, origen or "cartagena", elegido)
            if sid:
                requisitos += _lista(sid, "requirements", lang)
                # CALN-7 (28-oct): la preparación de la ficha («Para completar la teoría necesitas al menos 4 horas…»),
                # solo cuando se preguntan los requisitos de ESTE servicio (en el catálogo de todos los turnos se
                # descartó el 17-oct: competía con lo que hacía falta en cada uno).
                s = RAW_SERVICES.get(sid) or {}
                requisitos.append(s.get(f"preparation_{lang}") or s.get("preparation_es") or "")
            # lat-deuda-u: los que son políticas (formulario médico, refresh, seguro, vuelo), los de ESTA actividad y no
            # los del plan con el que se vende (el refresher, con la ficha del minicurso).
            requisitos += requisitos_de_politica(actividad, lang)
            requisitos += _previo_y_edad(registro, lang)
            if registro.requires_certification:
                requisitos.append(_politica("certification_required", lang))
            requisitos.append(_politica("what_to_bring", lang))
            bloque["requisitos"] = [r for r in dict.fromkeys(requisitos) if r]
        if "horario" in pedidas:
            bloque["horario"] = _por_origen(actividad, origenes, lambda sid: _lista(sid, "itinerary", lang), elegido)
            bloque["horario_general"] = [p for p in (_politica("operating_hours", lang),
                                                     _politica("activity_schedule", lang)) if p]
        if "disponibilidad" in pedidas:
            bloque["disponibilidad"] = [p for p in (_politica("availability_always", lang),
                                                    _politica("booking_system_info", lang)) if p]
        if "edad" in pedidas:
            bloque["edad"] = {"minima": registro.min_age, "maxima": registro.max_age}
        if "descuento" in pedidas:
            bloque["descuento"] = _descuentos(state, lang)
        if "tiempo" in pedidas:
            bloque.update(_tiempo(lang))
        bloque.update(_clima_y_pago(state, pedidas, lang))
        bloque.update(_temas_de_lat8(pedidas, lang))
        # arq-1m (G10 nº 2): «¿hay disponibilidad mañana?» o «¿cómo reservamos?» se contestaban con «en la web», sin el
        # enlace (Jev marcaba la disponibilidad, no el enlace): con la disponibilidad va también el enlace de reserva.
        # lat-0a (real-1, 24-oct): «listo, ¿cómo pago?» con el plan ya elegido se contestaba «pagas con tarjeta en la
        # página web» sin el enlace (3 diálogos). Con el pago va también el enlace del plan; el cómo pagar ya lo lleva
        # el pago, así que no se repite en `como_reservar`.
        if "enlace" in pedidas or "pago" in pedidas or "disponibilidad" in pedidas:
            if state.is_colombian and not getattr(state, "mixed_nationality_notice", False):
                # Decisión de Gadea (21-oct): el cierre de un colombiano lo coordina un asesor (pago en COP), sin enlace.
                bloque["enlace"] = {"asesor": True}
            else:
                bloque["enlace"] = _por_origen(
                    actividad, origenes,
                    lambda sid: cart_render._resolve_service_booking_url(SERVICES.get(sid) or {}, state), elegido)
                if bloque["enlace"]:
                    bloque["descuento_online"] = _descuento_online(lang)
                    if "pago" not in pedidas:
                        como = [_politica("how_to_book", lang), _pago_extranjero(lang),
                                _politica("payment_confirmation", lang)]
                        if registro.requires_certification:
                            como.append(_politica("certification_required", lang))
                        bloque["como_reservar"] = [c for c in como if c]
        if {"incluye", "horario"} & set(pedidas):
            # Cómo se llega según el origen (G10 de control, 22-oct: «no aclara que en Cartagena no se recoge en el
            # hotel», «no dice que el regreso está incluido sin cargo», «falta "a 5 minutos del centro"»).
            recogida = {o: [_politica("meeting_point", lang)] if o == "cartagena"
                        else [_politica("island_pickup_free", lang), *_coordinacion_en_las_islas(lang),
                              *_sin_almuerzo_en_las_islas(lang, pedidas)]
                        for o in origenes if _plan_base(actividad, o, elegido)}
            bloque["recogida"] = {o: [x for x in v if x] for o, v in recogida.items() if any(v)}
        if {"precio", "incluye", "horario", "requisitos"} & set(pedidas):
            alojamiento = _alojamiento(actividad, registro, lang, elegido)
            if alojamiento:  # G10: «no aclara que el alojamiento no está incluido» en los planes de varios días
                bloque["alojamiento"] = alojamiento
        if not origen and _DEPENDEN_DEL_ORIGEN & set(pedidas):
            bloque["pregunta_pendiente"] = "origen"
        bloques.append(bloque)
    return _lo_que_faltaba(state, bloques, pedidas, lang)


# arq-1s (22-oct; G10 nº 4): en un curso, un solo formulario (decisión de Gadea), y el alumno del Advanced (certificado Y
# en un curso) recibía los dos (g10-058). Desde lat-deuda-u (26-oct) la política del formulario de curso
# (`medical_restrictions`) y la de buzo certificado (`medical_certified_diver`) van por separado: no hay que cortarla.
# Aquí, el requisito previo del curso (el nivel anterior del registro: el Open Water para el Advanced) y la edad mínima
# en cifra (g10-032).


def _previo_y_edad(registro, lang: str) -> list[str]:
    hechos_: list[str] = []
    if registro.family == "course" and registro.course_level and registro.course_level > 1:
        previo = next((a for a in dom.registry().activities if a.family == "course" and a.certifies
                       and a.course_level == registro.course_level - 1 and not a.generic), None)
        if previo is not None:
            nombre = re.sub(r"\s+", " ", re.sub(r"(?i)\b(curso|course)\b", "", dom.label(previo.id, lang))).strip()
            hechos_.append(f"Requisito previo: tener la certificación {nombre}." if lang == "es"
                           else f"Prerequisite: holding the {nombre} certification.")
    if registro.min_age:
        hechos_.append(f"Edad mínima: desde los {registro.min_age} años." if lang == "es"
                       else f"Minimum age: {registro.min_age} and over.")
    return hechos_


def _tiempo(lang: str) -> dict:
    """arq-1v: si da tiempo antes de irse. La decisión de Gadea (desde las islas va muy justo y lo confirma un asesor;
    desde Cartagena no alcanza; el cierre de las 4:30) va en `tiempo`; la espera antes de volar, aparte (`si_vuela`), para
    que solo se diga si el cliente vuela."""
    tiempo = [p for p in (_politica("time_limited_departure", lang), _politica("activity_schedule", lang)) if p]
    vuela = _politica("flight_after_diving", lang)
    return {"tiempo": tiempo, **({"si_vuela": vuela} if vuela else {})}


def _paquetes_de_varios_dias(actividad: str, origen: str) -> list[str]:
    """arq-1t: los planes de la actividad en ese origen que duran varios días (los paquetes), en el orden del registro."""
    return [s for s in dom.service_ids(actividad, origen) if ((SERVICES.get(s) or {}).get("duration_days") or 0) > 1]


def _comunes(listas: list[list[str]]) -> list[str]:
    """Los elementos que están en TODAS las listas, en el orden de la primera."""
    if not listas:
        return []
    resto = [set(lista) for lista in listas[1:]]
    return [x for x in listas[0] if all(x in r for r in resto)]


# arq-1u (22-oct; G10 nº 4: g10-051, g10-072, g10-006, g10-045): con el enlace de reserva,
# cómo se reserva y se paga por él (el extranjero, 100 % con tarjeta en la web) y que la reserva queda confirmada cuando
# el equipo concilia el pago; si la actividad pide certificación, el carné (g10-027). Al colombiano no se le da el
# enlace (lo coordina un asesor), así que la parte de su pago no va aquí.
def _pago_extranjero(lang: str) -> str | None:
    """Cómo paga quien paga por el enlace (lat-deuda-u: su propia política, ya no un corte de `foreign_card_payment`)."""
    return _politica("foreign_card_payment", lang)


# arq-1p (22-oct): lo que NO depende de la actividad. En el G10 nº 4, 24 turnos se quedaron sin
# redactor porque no se sabía la actividad (`hechos=sin_actividad`); 11 preguntaban solo la hora o la recogida, qué llevar
# o si hay sitio, casi siempre quien ya reservó y no la nombra. Esos hechos son los mismos para todas las actividades (las
# políticas), así que el código los da sin adivinar la actividad. Precio, qué incluye, edad y enlace sí la necesitan.
INTENCIONES_SIN_ACTIVIDAD = frozenset({"horario", "disponibilidad", "requisitos", "descuento", "tiempo", "clima", "pago",
                                       "hoteles", "regreso", "fotos", "cambios"})


def _descuentos(state: ConversationState, lang: str) -> list[str]:
    """arq-4b: los descuentos con sus condiciones, tal cual de discounts.json (online,
    grupo, equipo propio y que no hay descuento por ser colombiano). Son los mismos para todas las actividades: cada uno
    dice a qué aplica."""
    textos = descuentos_de_la_base(lang)  # arq-8h: de la función del catálogo, con la nota del acompañante
    if getattr(state, "mixed_nationality_notice", False):
        # arq-8a (G10 nº 6, g10-043): «mi pareja es colombiana y yo extranjera, ¿hay descuento?» llevaba «los
        # colombianos pagan en COP» y no la regla del grupo mixto (esa solo iba con el precio): «tu pareja paga en pesos y
        # tú en dólares». En un grupo mixto, la regla de la moneda es la suya, como en `regla_moneda`.
        textos = {**textos, "colombian_cop_pricing": _politica("mixed_nationality_group", lang)}
    return [x for x in textos.values() if x]


# CALN-3 (decisión 4 del 27-oct, CALN3-Q04): con el precio, el de grupo solo cuando aplica a ESTE grupo y plan. A 5
# españoles que piden el Open Water se les ofrecía «10 % para grupos de 5 o más… no aplica a cursos PADI. ¿Te paso con un
# asesor para aplicarlo?»: los descuentos iban todos en el contexto sin decir cuál aplica. A quién aplica, de la base
# (`applicability`: buceo recreativo, minicurso y snorkel); los cursos no.
_CON_DESCUENTO_DE_GRUPO = {"cert", "beginner", "snorkel"}
_SIN_DESCUENTO_DE_GRUPO = {
    "es": "El descuento de grupo ({pct} % desde {n} personas) NO aplica a los cursos PADI: no lo ofrezcas para este plan.",
    "en": "The group discount ({pct}% from {n} people) does NOT apply to PADI courses: don't offer it for this plan.",
}


def _descuento_de_grupo(state: ConversationState, registro, lang: str) -> str | None:
    """Si el grupo llega al mínimo: el texto del descuento de grupo si el plan lo tiene, o que no aplica si es un curso.
    Sin grupo de ese tamaño, nada (los demás descuentos, solo si los pregunta)."""
    datos = json.loads(_DISCOUNTS.read_text(encoding="utf-8-sig")).get("discounts", {}).get("group_discount") or {}
    minimo = datos.get("min_people") or 5
    if (state.detected_group_size or 0) < minimo:
        return None
    if registro.cart_type == "course":
        return _SIN_DESCUENTO_DE_GRUPO[lang].format(pct=datos.get("percentage", 10), n=minimo)
    if registro.cart_type in _CON_DESCUENTO_DE_GRUPO:
        return datos.get(f"description_{lang}") or datos.get("description_es")
    return None


def hechos_sin_actividad(state: ConversationState, intenciones: list[str]) -> list[dict]:
    """Un bloque de hechos generales (sin actividad) para las intenciones que no dependen de ella; [] si no hay ninguna."""
    lang = "es" if state.language == "es" else "en"
    origen = state.location if state.location in ORIGENES else None
    origenes = (origen,) if origen else ORIGENES
    pedidas = [i for i in intenciones if i in INTENCIONES_SIN_ACTIVIDAD]
    if not pedidas:
        return []
    bloque: dict = {"actividad": None, "nombre": "general", "origen": origen}
    if "horario" in pedidas:
        bloque["horario_general"] = [p for p in (_politica("operating_hours", lang),
                                                 _politica("activity_schedule", lang)) if p]
        recogida = {o: [_politica("meeting_point", lang) if o == "cartagena" else _politica("island_pickup_free", lang)]
                    for o in origenes}
        bloque["recogida"] = {o: [x for x in v if x] for o, v in recogida.items() if any(v)}
    if "disponibilidad" in pedidas:
        bloque["disponibilidad"] = [p for p in (_politica("availability_always", lang),
                                                _politica("booking_system_info", lang)) if p]
    if "tiempo" in pedidas:
        bloque.update(_tiempo(lang))
    if "requisitos" in pedidas:
        # CALN-7 (28-oct): también el formulario médico, que dice a qué aplica (cursos y minicursos; el refresher):
        # «vengo con mi hermana en silla de ruedas, ¿qué requisitos hay?» salía con el seguro y qué llevar, sin él.
        bloque["requisitos"] = [p for p in (_politica("insurance_form_requirement", lang),
                                            _politica("medical_restrictions", lang),
                                            _politica("what_to_bring", lang)) if p]
        if getattr(state, "is_certified", None) is True:
            # arq-1s: «soy buzo certificado, ¿qué requisitos hay?» sin actividad dicha: el carné también.
            bloque["requisitos"].insert(0, _politica("certification_required", lang))
            bloque["requisitos"] = [p for p in bloque["requisitos"] if p]
    if "descuento" in pedidas:
        bloque["descuento"] = _descuentos(state, lang)
    bloque.update(_clima_y_pago(state, pedidas, lang))
    bloque.update(_temas_de_lat8(pedidas, lang))
    return _lo_que_faltaba(state, [bloque], pedidas, lang)


# arq-5f (23-oct, reparto de Gadea #1525; G10 nº 5): hechos de la base que la tabla no daba.
# La excepción del refresher (g10-008, g10-047), que el horario no se adelanta (g10-066), buceo y snorkel en la misma
# lancha (g10-049) y que alojados en Barú salen desde Cartagena. Se añaden a los bloques ya hechos.
_BUCEO = {"certified_diving", "minicourse", "bubble_makers", "refresher"}


def _sale_de_baru(lang: str) -> str | None:
    """Quien se aloja en Barú sale desde Cartagena (lat-deuda-u: política `baru_departs_from_cartagena`)."""
    return _politica("baru_departs_from_cartagena", lang)


# arq-8d/8e (23-oct; G10 nº 6): `island_pickup` juntaba tres cosas que el código cortaba por sus frases. Desde
# lat-deuda-u (26-oct) son tres políticas: cómo se coordina la recogida (`island_pickup`), lo que esos planes no incluyen
# (`island_plans_exclude`) y que Barú no es de las islas (`baru_departs_from_cartagena`).
def _no_incluyen_las_islas(lang: str) -> str | None:
    """arq-8d: lo que no incluyen los planes de las islas."""
    return _politica("island_plans_exclude", lang)


def _sin_almuerzo_en_las_islas(lang: str, pedidas: list[str]) -> list[str]:
    """arq-8d: con «incluye», la frase de que los planes de las islas no incluyen transporte desde Cartagena ni almuerzo
    va también con la recogida, que la pone el código entera (banco arq-8, B: con `no_incluye` solo, el redactor no la
    decía en 9 de 9, porque `no_incluye` solo se cuenta si el cliente pregunta por algo concreto)."""
    excluye = _no_incluyen_las_islas(lang) if "incluye" in pedidas else None
    return [excluye] if excluye else []


def _coordinacion_en_las_islas(lang: str) -> list[str]:
    """arq-8e: cómo se coordina la recogida en las islas."""
    como = _politica("island_pickup", lang)
    return [como] if como else []


def _bucea(actividad: str | None) -> bool:
    registro = dom.by_id(actividad) if actividad else None
    return actividad in _BUCEO or (registro is not None and registro.cart_type == "course")


def _lo_que_faltaba(state: ConversationState, bloques: list[dict], pedidas: list[str], lang: str) -> list[dict]:
    actividades = {b.get("actividad") for b in bloques} | {
        a for a, n in (getattr(state, "detected_group_allocation", None) or {}).items() if n}
    # La lancha va con el horario o lo que incluye (cómo es la salida), no con una pregunta de edad o de precio.
    con_snorkel_y_buceo = ({"horario", "incluye"} & set(pedidas) and "snorkel" in actividades
                           and any(_bucea(a) for a in actividades))
    for b in bloques:
        if "horario_general" in b:
            b["horario_general"] = [*b["horario_general"], *filter(None, [_politica("schedule_not_adjustable", lang)])]
        actividad = b.get("actividad")
        certificado_sin_actividad = actividad is None and getattr(state, "is_certified", None) is True
        if "requisitos" in pedidas and "requisitos" in b and certificado_sin_actividad:  # con actividad: requisitos_de_politica
            b["requisitos"] = list(dict.fromkeys([*b["requisitos"], *filter(None, [_politica("refresh_requirement",
                                                                                              lang)])]))
        if getattr(state, "_aloja_en_baru", False) and (b.get("recogida") or {}).get("cartagena") is not None:
            b["recogida"]["cartagena"] = [*b["recogida"]["cartagena"], *filter(None, [_sale_de_baru(lang)])]
        if con_snorkel_y_buceo and (actividad is None or actividad == "snorkel" or _bucea(actividad)):
            b["misma_lancha"] = _politica("mixed_group_boat", lang)
    return bloques


# arq-1i (23-oct, decisión de Gadea #1312): el clima en general y cómo se paga, los mismos
# para todas las actividades. La previsión de un día concreto no es un hecho de la base: la da el equipo (sin
# pronósticos), y el redactor ofrece un asesor.
_PREVISION = {
    "es": "El pronóstico o el estado del mar de un día concreto no se da por aquí: lo confirma el equipo. Si el cliente "
          "quiere, se le pasa con un asesor.",
    "en": "The forecast or sea conditions for a specific day are not given here: the team confirms them. If the customer "
          "wants, they can be passed to an advisor.",
}


def _pago_colombiano(lang: str) -> str | None:
    """Cómo pagan los colombianos y residentes (lat-deuda-u: política `payment_colombian`)."""
    return _politica("payment_colombian", lang)


def _clima_y_pago(state: ConversationState, pedidas: list[str], lang: str) -> dict:
    out: dict = {}
    if "clima" in pedidas:
        out["clima"] = [p for p in (_politica("weather_cancellation", lang), _politica("closed_days", lang),
                                    _PREVISION[lang]) if p]
    if "pago" in pedidas:
        # Según la nacionalidad (pa1 del banco: a un alemán no le aplica el anticipo del 50 %): el extranjero paga por
        # el enlace; el colombiano o residente, con un asesor (decisión de gen-4); sin saberlo, los dos.
        mixto = getattr(state, "mixed_nationality_notice", False)
        colombiano = None if mixto else state.is_colombian
        if colombiano is True:
            pago = [_pago_colombiano(lang)]
        elif colombiano is False or mixto:
            pago = [_pago_extranjero(lang), _politica("payment_confirmation", lang), _politica("payment_fallback", lang)]
        else:
            pago = [_politica("foreign_card_payment", lang), _politica("payment_colombian", lang),
                    _politica("payment_confirmation", lang), _politica("payment_fallback", lang)]
        out["pago"] = [p for p in pago if p]
    return out


# lat-8 (26-oct, #1880): cuatro temas más, con las políticas que la base ya tiene. En «cambios», la política general
# (cambiar la fecha o el número de personas, la cancelación); una reserva ya hecha la lleva un asesor (no llega aquí).
_POLITICAS_DE_LAT8 = {
    "hoteles": ("other_island_hotels",),
    "regreso": ("return_different_day",),
    "fotos": ("photos_videos_policy",),
    "cambios": ("reschedule", "modify_booking", "cancellation"),
}


def _temas_de_lat8(pedidas: list[str], lang: str) -> dict:
    out: dict = {}
    for tema, claves in _POLITICAS_DE_LAT8.items():
        if tema in pedidas and (textos := [p for p in (_politica(c, lang) for c in claves) if p]):
            out[tema] = textos
    return out


def _acompanante(bloque: dict, pedidas: list[str], origen: str | None, origenes: tuple[str, ...], moneda: str,
                 lang: str, dos_monedas: bool = False) -> dict:
    """arq-1j: el acompañante (va en la lancha sin bucear) no tiene ficha: su precio es una fila de la tarifa, el mismo en
    los dos orígenes, y lo que incluye cambia con el origen (en las islas, sin lancha desde Cartagena ni almuerzo)."""
    if "precio" in pedidas:
        c = COMPANION_PRICE
        online, normal = ((money.cop(c["cop_online"]), money.cop(c["cop_normal"])) if moneda == "COP"
                          else (money.usd(c["usd_online"]), money.usd(c["usd_normal"])))
        bloque["moneda"] = moneda
        bloque["precio"] = {o: {"plan": bloque["nombre"], "online": online, "normal": normal} for o in origenes}
        if dos_monedas:  # arq-5c: sin saber la nacionalidad, también en COP
            bloque["moneda"] = "USD / COP"
            bloque["precio_cop"] = {o: {"plan": bloque["nombre"], "online": money.cop(c["cop_online"]),
                                        "normal": money.cop(c["cop_normal"])} for o in origenes}
    if "incluye" in pedidas:
        bloque["incluye"] = {o: list(COMPANION_INCLUDES[lang][o]) for o in origenes}
        bloque["no_incluye"] = {o: [COMPANION_NO_INCLUYE[lang]] for o in origenes}
    if not origen and {"precio", "incluye"} & set(pedidas):
        bloque["pregunta_pendiente"] = "origen"
    return bloque


def _alojamiento(actividad: str, registro, lang: str, elegido: str | None = None) -> str | None:
    """En los planes de varios días, que hay que dormir en las islas y el alojamiento no está incluido: la política de
    los cursos de 2 días o, en los paquetes, lo que dice su ficha que no incluye."""
    sid = _plan_base(actividad, "cartagena", elegido) or _plan_base(actividad, "island", elegido)
    if not sid or ((SERVICES.get(sid) or {}).get("duration_days") or 1) < 2:
        return None
    # Cursos de 2 días y paquetes de varios días: la misma política (decisión de Gadea, 22-oct: el alojamiento de los
    # paquetes también se reserva directamente con el hotel; G10 nº 2, g10-067).
    return _politica("courses_overnight_requirement", lang)


# ── ARQ-3: ¿la respuesta lleva los hechos? ───────────────────────────────────
# El redactor recibe los hechos y a veces se deja alguno («cumple la edad mínima» sin decir 10, banco arq-1d F v1). El
# código lo comprueba con lo que es exacto (importes, edades, enlaces) y, en las listas, con las palabras clave de la
# primera frase de cada elemento (el redactor las copia casi tal cual; una paráfrasis corta conserva la mayoría).
# Solo lee los hechos y la respuesta, nunca el mensaje del cliente.
_PALABRA = re.compile(r"[a-z0-9]+")
_URL = re.compile(r"https?://\S+")
_CIFRA = re.compile(r"\d[\d.,]*")
_VACIAS = {"para", "como", "desde", "hasta", "este", "esta", "estos", "estas", "debes", "puedes", "tiene", "tienes",
           "with", "from", "that", "this", "your", "they", "must", "have", "will", "into", "each", "also"}
_MINIMO_DE_PALABRAS = 0.5


def _raices(texto: str) -> set[str]:
    """Las palabras con contenido, recortadas a 5 letras (plural, género y conjugación cercanos cuentan igual)."""
    return {p[:5] for p in _PALABRA.findall(strip_accents(_URL.sub(" ", texto).lower())) if len(p) >= 4 and p not in _VACIAS}


def _cifras(texto: str) -> set[str]:
    return {re.sub(r"\D", "", c) for c in _CIFRA.findall(texto or "")}


def _primera_frase(elemento: str) -> str:
    return re.split(r"(?<=[.!?])\s", elemento.strip(), maxsplit=1)[0]


def _url_sin_parametros(url: str) -> str:
    return url.split("?")[0].split("#")[0].rstrip(".,)")


def _elemento_dado(elemento: str, raices: set[str], answer: str) -> bool:
    frase = _primera_frase(elemento)
    if any(_url_sin_parametros(u) not in answer for u in _URL.findall(frase)):
        return False
    propias = _raices(frase)
    return not propias or len(propias & raices) / len(propias) >= _MINIMO_DE_PALABRAS


def faltan(answer: str, bloques: list[dict], intenciones: list[str]) -> list[str]:
    """Los hechos pedidos que la respuesta no lleva (vacío si los lleva todos)."""
    raices, cifras = _raices(answer), _cifras(answer)
    perdidos: list[str] = []
    for b in bloques:
        if "precio" in intenciones:
            for precio in (*(b.get("precio") or {}).values(), *(b.get("precio_cop") or {}).values()):
                perdidos += [precio[k] for k in ("online", "normal")
                             if precio.get(k) and re.sub(r"\D", "", precio[k]) not in cifras]
        if "edad" in intenciones:
            perdidos += [f"edad {v}" for v in (b.get("edad") or {}).values() if v and str(v) not in cifras]
        if "enlace" in intenciones or "disponibilidad" in intenciones:
            perdidos += [u for u in (b.get("enlace") or {}).values()
                         if isinstance(u, str) and _url_sin_parametros(u) not in answer]
        for intencion in ("incluye", "requisitos", "descuento", "en_que_consiste"):
            if (intencion if intencion != "en_que_consiste" else "incluye") not in intenciones:
                continue
            listas = b.get(intencion) or {}
            for elemento in dict.fromkeys(e for lista in (listas.values() if isinstance(listas, dict) else [listas])
                                          for e in lista):
                if not _elemento_dado(elemento, raices, answer):
                    perdidos.append(elemento)
        # CALN-6 paso 2f (27-oct): la recogida va en los hechos, pero no se exige (si no la decía el escritor, arq-7b la
        # pegaba siempre: repetida o sin venir a cuento; mini-ronda con el juez: 5 → 4 fallos en 14 diálogos).
        if "clima" in intenciones and b.get("clima") and "100" not in cifras:
            perdidos.append(b["clima"][0])  # arq-1i: lo que contesta la pregunta, el reembolso del 100 % si no se reprograma
        if "pago" in intenciones and b.get("pago") and not _elemento_dado(b["pago"][0], raices, answer):
            perdidos.append(b["pago"][0])  # arq-1i: cómo paga ESTE cliente
        for tema in _POLITICAS_DE_LAT8:  # lat-8: lo que contesta la pregunta, la primera política del tema
            if tema in intenciones and b.get(tema) and not _elemento_dado(b[tema][0], raices, answer):
                perdidos.append(b[tema][0])
        if "tiempo" in intenciones and b.get("tiempo"):  # arq-1v: la decisión de Gadea tiene que ir
            if not _elemento_dado(b["tiempo"][0], raices, answer):
                perdidos.append(b["tiempo"][0])
        if "enlace" in intenciones or "disponibilidad" in intenciones:
            for elemento in b.get("como_reservar") or []:  # arq-1u
                if not _elemento_dado(elemento, raices, answer):
                    perdidos.append(elemento)
        if b.get("alojamiento") and not _elemento_dado(b["alojamiento"], raices, answer):
            perdidos.append(b["alojamiento"])
        if "horario" in intenciones:
            horas = {h for lista in (b.get("horario") or {}).values() for e in lista
                     for h in re.findall(r"\b(\d{1,2}):\d{2}", e)}
            if horas and not horas & cifras and not any(f"{h}:" in answer for h in horas):
                perdidos.append("la hora (" + ", ".join(sorted(horas, key=int)) + ")")
    return perdidos
