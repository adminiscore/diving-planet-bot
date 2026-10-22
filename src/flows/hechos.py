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
import unicodedata
from functools import lru_cache
from pathlib import Path

from src.domain import activities as dom
from src.flows import cart_render
from src.flows.catalog import (
    COMPANION_INCLUDES,
    COMPANION_PRICE,
    ISLAND_SERVICE_MAP,
    RAW_SERVICES,
    SERVICES,
)
from src.flows.state import ConversationState
from src.utils import money

INTENCIONES = ("precio", "incluye", "requisitos", "horario", "disponibilidad", "edad", "enlace")
ORIGENES = ("cartagena", "island")
# Las intenciones cuyos hechos cambian según desde dónde sale el cliente: sin origen van las dos variantes.
_DEPENDEN_DEL_ORIGEN = {"precio", "incluye", "horario", "enlace"}
# Planes que exigen el formulario médico de curso (política medical_restrictions): cursos, minicurso y refresher (se
# reserva como minicurso), por su `cart_type` en el registro de actividades.
_CON_FORMULARIO_MEDICO = {"course", "beginner", "refresh"}

_POLICIES = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "policies.json"


@lru_cache(maxsize=1)
def _politicas() -> dict:
    datos = json.loads(_POLICIES.read_text(encoding="utf-8-sig"))
    return datos.get("policies", datos)


def _politica(clave: str, lang: str) -> str | None:
    valor = _politicas().get(clave)
    if isinstance(valor, dict):
        return valor.get(lang) or valor.get("es")
    return valor


def _moneda(state: ConversationState) -> str:
    """COP a colombianos y residentes; USD al resto, si no se sabe o en un grupo mixto (decisiones de Gadea)."""
    if getattr(state, "mixed_nationality_notice", False):
        return "USD"
    return "COP" if state.is_colombian else "USD"


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
    bloques = []
    for actividad in actividades:
        registro = dom.by_id(actividad)
        if registro is None:
            continue
        bloque: dict = {"actividad": actividad, "nombre": dom.label(actividad, lang), "origen": origen}
        if registro.cart_type == "companion":
            bloques.append(_acompanante(bloque, pedidas, origen, origenes, moneda, lang))
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
            if otros:  # el buceo y los paquetes: el plan base y la lista de los demás con su precio
                bloque["otros_planes"] = [{"plan": _nombre(s, lang), "precio": _precio(s, moneda)}
                                          for s in otros if _precio(s, moneda)]
        if "incluye" in pedidas:
            bloque["incluye"] = _por_origen(actividad, origenes, lambda sid: _lista(sid, "included", lang), elegido)
            # Lo que NO incluye: de la ficha y, en los planes de las islas (sus fichas no lo traen), de la política de la
            # recogida («no incluyen transporte desde Cartagena ni almuerzo»). Sin esto, «¿hay almuerzo?» desde las
            # islas se quedaba sin contestar (banco arq-1d, v2).
            no_incluye = _por_origen(actividad, origenes, lambda sid: _lista(sid, "not_included", lang), elegido)
            if "island" in origenes and _plan_base(actividad, "island", elegido):
                no_incluye["island"] = [*no_incluye.get("island", []), _politica("island_pickup", lang)]
            if no_incluye:
                bloque["no_incluye"] = no_incluye
        if "requisitos" in pedidas:
            requisitos: list[str] = []
            sid = _plan_base(actividad, origen or "cartagena", elegido)
            if sid:
                requisitos += _lista(sid, "requirements", lang)
            if registro.cart_type in _CON_FORMULARIO_MEDICO:
                requisitos.append(_politica("medical_restrictions", lang))
            if registro.requires_certification:
                requisitos.append(_politica("certification_required", lang))
            requisitos += [_politica("insurance_form_requirement", lang), _politica("what_to_bring", lang)]
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
        if "enlace" in pedidas:
            if state.is_colombian and not getattr(state, "mixed_nationality_notice", False):
                # Decisión de Gadea (21-oct): el cierre de un colombiano lo coordina un asesor (pago en COP), sin enlace.
                bloque["enlace"] = {"asesor": True}
            else:
                bloque["enlace"] = _por_origen(
                    actividad, origenes,
                    lambda sid: cart_render._resolve_service_booking_url(SERVICES.get(sid) or {}, state), elegido)
        if {"incluye", "horario"} & set(pedidas):
            # Cómo se llega según el origen (G10 de control, 22-oct: «no aclara que en Cartagena no se recoge en el
            # hotel», «no dice que el regreso está incluido sin cargo», «falta "a 5 minutos del centro"»).
            recogida = {o: [_politica("meeting_point", lang)] if o == "cartagena"
                        else [_politica("island_pickup_free", lang)]
                        for o in origenes if _plan_base(actividad, o, elegido)}
            bloque["recogida"] = {o: [x for x in v if x] for o, v in recogida.items() if any(v)}
        if {"precio", "incluye", "horario", "requisitos"} & set(pedidas):
            alojamiento = _alojamiento(actividad, registro, lang, elegido)
            if alojamiento:  # G10: «no aclara que el alojamiento no está incluido» en los planes de varios días
                bloque["alojamiento"] = alojamiento
        if not origen and _DEPENDEN_DEL_ORIGEN & set(pedidas):
            bloque["pregunta_pendiente"] = "origen"
        bloques.append(bloque)
    return bloques


def _acompanante(bloque: dict, pedidas: list[str], origen: str | None, origenes: tuple[str, ...], moneda: str,
                 lang: str) -> dict:
    """arq-1j: el acompañante (va en la lancha sin bucear) no tiene ficha: su precio es una fila de la tarifa, el mismo en
    los dos orígenes, y lo que incluye cambia con el origen (en las islas, sin lancha desde Cartagena ni almuerzo)."""
    if "precio" in pedidas:
        c = COMPANION_PRICE
        online, normal = ((money.cop(c["cop_online"]), money.cop(c["cop_normal"])) if moneda == "COP"
                          else (money.usd(c["usd_online"]), money.usd(c["usd_normal"])))
        bloque["moneda"] = moneda
        bloque["precio"] = {o: {"plan": bloque["nombre"], "online": online, "normal": normal} for o in origenes}
    if "incluye" in pedidas:
        bloque["incluye"] = {o: list(COMPANION_INCLUDES[lang][o]) for o in origenes}
    if not origen and {"precio", "incluye"} & set(pedidas):
        bloque["pregunta_pendiente"] = "origen"
    return bloque


def _alojamiento(actividad: str, registro, lang: str, elegido: str | None = None) -> str | None:
    """En los planes de varios días, que hay que dormir en las islas y el alojamiento no está incluido: la política de
    los cursos de 2 días o, en los paquetes, lo que dice su ficha que no incluye."""
    sid = _plan_base(actividad, "cartagena", elegido) or _plan_base(actividad, "island", elegido)
    if not sid or ((SERVICES.get(sid) or {}).get("duration_days") or 1) < 2:
        return None
    if registro.cart_type == "course":
        return _politica("courses_overnight_requirement", lang)
    return next((x for x in _lista(sid, "not_included", lang) if "aloj" in _plano(x) or "accommodation" in _plano(x)),
                None)


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


def _plano(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _raices(texto: str) -> set[str]:
    """Las palabras con contenido, recortadas a 5 letras (plural, género y conjugación cercanos cuentan igual)."""
    return {p[:5] for p in _PALABRA.findall(_plano(_URL.sub(" ", texto))) if len(p) >= 4 and p not in _VACIAS}


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
            for precio in (b.get("precio") or {}).values():
                perdidos += [precio[k] for k in ("online", "normal")
                             if precio.get(k) and re.sub(r"\D", "", precio[k]) not in cifras]
        if "edad" in intenciones:
            perdidos += [f"edad {v}" for v in (b.get("edad") or {}).values() if v and str(v) not in cifras]
        if "enlace" in intenciones:
            perdidos += [u for u in (b.get("enlace") or {}).values()
                         if isinstance(u, str) and _url_sin_parametros(u) not in answer]
        for intencion in ("incluye", "requisitos"):
            if intencion not in intenciones:
                continue
            listas = b.get(intencion) or {}
            for elemento in dict.fromkeys(e for lista in (listas.values() if isinstance(listas, dict) else [listas])
                                          for e in lista):
                if not _elemento_dado(elemento, raices, answer):
                    perdidos.append(elemento)
        for elemento in dict.fromkeys(e for lista in (b.get("recogida") or {}).values() for e in lista):
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
