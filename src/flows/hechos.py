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
from functools import lru_cache
from pathlib import Path

from src.domain import activities as dom
from src.flows import cart_render
from src.flows.catalog import ISLAND_SERVICE_MAP, RAW_SERVICES, SERVICES
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


def _plan_base(actividad: str, origen: str) -> str | None:
    """El plan de la actividad en ese origen: el base (en el buceo, la salida de 2 inmersiones) y, en las islas, su
    variante. En las islas el primero del registro es la salida de 1 inmersión: «¿la salida de dos inmersiones?»
    desde Majagua recibía 97 USD de base (banco arq-1d, p4)."""
    ids = dom.service_ids(actividad, origen)
    base = dom.base_service_id(actividad)
    if origen == "island" and ISLAND_SERVICE_MAP.get(base) in ids:
        return ISLAND_SERVICE_MAP[base]
    return ids[0] if ids else None


def _precio(sid: str, moneda: str) -> dict | None:
    s = SERVICES.get(sid) or {}
    if moneda == "COP":
        online, normal = money.cop(s.get("price_cop")), money.cop(s.get("price_cop_normal"))
    else:
        online, normal = money.usd(s.get("price_usd")), money.usd(s.get("price_usd_normal"))
    return {"online": online, "normal": normal} if online else None


def _lista(sid: str, campo: str, lang: str) -> list[str]:
    s = RAW_SERVICES.get(sid) or {}
    return list(s.get(f"{campo}_{lang}") or s.get(f"{campo}_es") or [])


def _por_origen(actividad: str, origenes: tuple[str, ...], fn) -> dict:
    out = {}
    for origen in origenes:
        sid = _plan_base(actividad, origen)
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
    bloques = []
    for actividad in actividades:
        registro = dom.by_id(actividad)
        if registro is None:
            continue
        bloque: dict = {"actividad": actividad, "nombre": dom.label(actividad, lang), "origen": origen}
        if "precio" in pedidas:
            bloque["moneda"] = moneda
            bloque["precio"] = _por_origen(actividad, origenes, lambda sid: _precio(sid, moneda))
            base = _plan_base(actividad, origen or "cartagena")
            otros = [s for s in dom.service_ids(actividad, origen or "cartagena") if s != base]
            if otros:  # el buceo y los paquetes: el plan base y la lista de los demás con su precio
                bloque["otros_planes"] = [
                    {"plan": (SERVICES.get(s) or {}).get(f"name_{lang}") or s, "precio": _precio(s, moneda)}
                    for s in otros if _precio(s, moneda)]
        if "incluye" in pedidas:
            bloque["incluye"] = _por_origen(actividad, origenes, lambda sid: _lista(sid, "included", lang))
            # Lo que NO incluye: de la ficha y, en los planes de las islas (sus fichas no lo traen), de la política de la
            # recogida («no incluyen transporte desde Cartagena ni almuerzo»). Sin esto, «¿hay almuerzo?» desde las
            # islas se quedaba sin contestar (banco arq-1d, v2).
            no_incluye = _por_origen(actividad, origenes, lambda sid: _lista(sid, "not_included", lang))
            if "island" in origenes and _plan_base(actividad, "island"):
                no_incluye["island"] = [*no_incluye.get("island", []), _politica("island_pickup", lang)]
            if no_incluye:
                bloque["no_incluye"] = no_incluye
        if "requisitos" in pedidas:
            requisitos: list[str] = []
            sid = _plan_base(actividad, origen or "cartagena")
            if sid:
                requisitos += _lista(sid, "requirements", lang)
            if registro.cart_type in _CON_FORMULARIO_MEDICO:
                requisitos.append(_politica("medical_restrictions", lang))
            if registro.requires_certification:
                requisitos.append(_politica("certification_required", lang))
            requisitos += [_politica("insurance_form_requirement", lang), _politica("what_to_bring", lang)]
            bloque["requisitos"] = [r for r in dict.fromkeys(requisitos) if r]
        if "horario" in pedidas:
            bloque["horario"] = _por_origen(actividad, origenes, lambda sid: _lista(sid, "itinerary", lang))
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
                    lambda sid: cart_render._resolve_service_booking_url(SERVICES.get(sid) or {}, state))
        if not origen and _DEPENDEN_DEL_ORIGEN & set(pedidas):
            bloque["pregunta_pendiente"] = "origen"
        bloques.append(bloque)
    return bloques
