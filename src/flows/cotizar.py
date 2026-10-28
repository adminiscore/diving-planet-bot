"""CALN-3 (27-oct): el resolvedor de precios. Diseño de Gonzalo en `docs/robustness/caln/diseno-caln3-precios.md`;
decisiones del 27-oct (Gadea delegó en su Claude «lo más lógico, orgánico, en la línea de la arquitectura, sin añadir
de más»): A pasando por B; sin plan elegido, los 2-3 candidatos del contexto; sin total del grupo en el texto;
descuentos, el online siempre y el de grupo cuando aplica.

Paso 1, EN SOMBRA: qué importes tocan en este turno, calculados por código con lo que sabe el estado al acabar el turno
(las personas de CALN-2, el origen, la moneda, el plan), y se apunta en la traza frente a los que dio la respuesta. No
cambia nada de lo que ve el cliente. Los importes salen de `hechos` (los mismos ayudantes que ya usa el escritor: el
plan base o los paquetes de varios días, los dos orígenes y las dos monedas si no se saben): aquí solo se decide QUÉ
actividades cotizar.

Paso 2 (27-oct, Gonzalo): sin actividad elegida, la pregunta del precio ya no va al RAG con el catálogo entero (CALN3-P01,
«¿cuánto cuesta bucear?»: tres turnos sin un precio, la puerta del origen quitaba los importes). El escritor recibe los
hechos de los candidatos (`hechos_de_los_candidatos`), cada uno con su plan base en los dos orígenes, y el código pregunta
el origen detrás, como con una actividad elegida.
"""
from __future__ import annotations

import logging
import re

from src.domain import activities as dom
from src.flows import hechos as hechos_mod

logger = logging.getLogger("uvicorn.error")


def _elegidas(state) -> list[str]:
    """Las del grupo (CALN-2) o la elegida o por la que pregunta."""
    reparto = [a for a, n in (state.detected_group_allocation or {}).items() if n and dom.by_id(a) is not None]
    if reparto:
        return reparto
    for actividad in (state.detected_activity, state.actividad_preguntada, state.suggested_activity):
        registro = dom.by_id(actividad) if actividad else None
        if registro is not None and not registro.generic:
            return [actividad]
    return []


def candidatos(state) -> list[str]:
    """Sin actividad elegida, los candidatos que deja lo que se sabe (decisión 2: los 2-3 del contexto, nunca el
    catálogo): certificado, el buceo; sin certificar, el minicurso y, si no ha dicho que quiere bucear, el snorkel
    (CALN3-P01: «nunca he buceado» a «¿cuánto cuesta bucear?» no pide el snorkel); sin saber si está certificado, el
    buceo y el minicurso. Solo se llama cuando pide precio: «hola, ¿cuánto cuesta bucear?» llega sin lectura del
    extractor (Jev: nada que apuntar), así que no se espera a `quiere_bucear`."""
    if state.is_certified is True:
        return ["certified_diving"]
    if state.is_certified is False:
        return ["minicourse"] if getattr(state, "quiere_bucear", False) else ["minicourse", "snorkel"]
    return ["certified_diving", "minicourse"]


def actividades_a_cotizar(state) -> list[str]:
    """Las elegidas o, sin ninguna, los candidatos."""
    return _elegidas(state) or candidatos(state)


def hechos_de_los_candidatos(state, intenciones: list[str]) -> list[dict]:
    """Paso 2: los hechos de los candidatos, cada uno con su plan base y sin la lista de los demás planes (los paquetes
    de buceo de los dos orígenes eran media carta: «nunca el catálogo entero»)."""
    bloques = hechos_mod.hechos(state, intenciones, candidatos(state))
    for bloque in bloques:
        bloque.pop("otros_planes", None)
    return bloques


def cotizar(state) -> dict:
    """La pieza de precios del turno: las actividades, los importes (cifras, sin separadores) y lo que falta saber."""
    actividades = _elegidas(state)
    if actividades:
        bloques = hechos_mod.hechos(state, ["precio"], actividades)
    else:
        actividades = candidatos(state)
        bloques = hechos_de_los_candidatos(state, ["precio"]) if actividades else []
    def cifras(precios) -> list[str]:
        return sorted({re.sub(r"\D", "", p[clave]) for p in precios for clave in ("online", "normal") if p.get(clave)})

    base = [p for b in bloques for p in (*(b.get("precio") or {}).values(), *(b.get("precio_cop") or {}).values())]
    otros = [p.get(clave) or {} for b in bloques for p in b.get("otros_planes") or [] for clave in ("precio", "precio_cop")]
    falta = [dato for dato, sabido in (("origen", state.location in hechos_mod.ORIGENES),
                                       ("plan", bool(state.detected_activity or state.detected_group_allocation)))
             if not sabido]
    # `importes`: los del plan de cada actividad, en los orígenes y monedas que tocan (los que tienen que salir);
    # `otros`: los demás planes (paquetes), que pueden salir pero no hace falta.
    return {"actividades": actividades, "importes": cifras(base), "otros": cifras(otros), "falta": falta}


def en_sombra(state, respuesta: str) -> None:
    """Paso 1: si el cliente pidió precio o la respuesta lleva importes, apunta en la traza qué daría el código y qué dio
    la respuesta, para medir cuánto se equivoca hoy el escritor (los que faltan y los que sobran)."""
    pide = bool((getattr(state, "_senales_router", None) or {}).get("pide_precio"))
    dados = {re.sub(r"\D", "", m) for m in re.findall(r"\d{1,3}(?:[.,]\d{3})+|\b\d{2,4}(?=\s*(?:USD|COP|US\$))",
                                                       respuesta or "")}
    if not (pide or dados):
        return
    pieza = cotizar(state)
    faltan = [i for i in pieza["importes"] if i not in dados]
    permitidos = set(pieza["importes"]) | set(pieza["otros"])
    unidades = {int(i) for i in permitidos if i}
    # La tarjeta multiplica (N × precio): sus totales no sobran.
    sobran = sorted(d for d in dados if d not in permitidos
                    and not any(int(d) % u == 0 and 2 <= int(d) // u <= 20 for u in unidades))
    logger.info(f"[CORE][CALN3] cotizar en sombra: pide {pide}, actividades {pieza['actividades']}, falta "
                f"{pieza['falta']}, el código {len(pieza['importes'])} importes, la respuesta {len(dados)}; "
                f"faltan {len(faltan)} {faltan[:6]}, sobran {len(sobran)} {sobran[:6]}")


# ── Paso 3 «A» (28-oct, decisión de Gadea #2296): los importes los pone el código ──────────────────────────────────
# El escritor recibe los hechos de precio pero no escribe cifras (`RAG_PRECIOS_POR_CODIGO`); debajo de su texto va esta
# pieza, sacada de los mismos bloques. Con el escritor redactando los importes, se dejaba un origen (p03, p18: «faltan
# 630000, 700000» en la sombra) u ofrecía el descuento de grupo a un curso PADI aunque los hechos dijeran que no (r01).
_PIEZA = {
    "es": {"titulo": "*Precios por persona* (online · normal):", "cartagena": "*Desde Cartagena*",
           "island": "*Ya en las Islas del Rosario*"},
    "en": {"titulo": "*Prices per person* (online · regular):", "cartagena": "*From Cartagena*",
           "island": "*Already on the Rosario Islands*"},
}
_DE_LAS_ISLAS_RE = re.compile(r"\s*(?:[-–]\s*ya en las islas|[-–]\s*already on (?:the )?islands?|"
                              r"\(ya en las islas\)|\(already on (?:the )?islands?\))", re.IGNORECASE)
_EN_EL_PARENTESIS_RE = re.compile(r",\s*(?:ya en las islas|already on (?:the )?islands?)\)", re.IGNORECASE)


def _sin_el_origen(plan: str) -> str:
    """«Salidas de Buceo - 2 inmersiones (1 día, ya en las islas)» → «… (1 día)»: el origen ya va en el título."""
    return _DE_LAS_ISLAS_RE.sub("", _EN_EL_PARENTESIS_RE.sub(")", plan)).strip()


def _importe(usd: dict | None, cop: dict | None) -> str:
    principal = usd or cop or {}
    texto = f"{principal.get('online')} · {principal.get('normal')}"
    if usd and cop:
        texto += f" ({cop.get('online')} · {cop.get('normal')})"
    return texto


def pieza_de_precios(bloques: list[dict], lang: str) -> str | None:
    """La lista de precios de los bloques de hechos, por origen: cada plan con su precio online y normal (y en COP si
    van las dos monedas) y, si aplica, el descuento de grupo. None si ningún bloque trae precio."""
    textos = _PIEZA["es" if lang == "es" else "en"]
    por_origen: dict[str, list[str]] = {}
    notas: list[str] = []
    for b in bloques:
        for origen, precio in (b.get("precio") or {}).items():
            cop = (b.get("precio_cop") or {}).get(origen)
            usd = precio if "COP" not in str(precio.get("online")) else None
            por_origen.setdefault(origen, []).append(f"• {_sin_el_origen(precio['plan'])}: {_importe(usd, cop or (None if usd else precio))}")
        for otro in b.get("otros_planes") or []:
            origen = otro.get("origen") or b.get("origen") or next(iter(b.get("precio") or {}), "cartagena")
            usd = otro.get("precio") if "COP" not in str((otro.get("precio") or {}).get("online")) else None
            cop = otro.get("precio_cop") or (None if usd else otro.get("precio"))
            por_origen.setdefault(origen, []).append(f"• {_sin_el_origen(otro['plan'])}: {_importe(usd, cop)}")
        if b.get("descuento_de_grupo") and b["descuento_de_grupo"] not in notas:
            notas.append(b["descuento_de_grupo"])
    if not por_origen:
        return None
    lineas = [textos["titulo"]]
    for origen in ("cartagena", "island"):
        if origen in por_origen:
            if len(por_origen) > 1:
                lineas.append(textos[origen])
            lineas += list(dict.fromkeys(por_origen[origen]))
    return "\n".join(lineas) + ("\n\n" + "\n".join(notas) if notas else "")
