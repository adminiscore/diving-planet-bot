"""CALN-3 (27-oct): el resolvedor de precios. Diseño de Gonzalo en `docs/robustness/caln/diseno-caln3-precios.md`;
decisiones del 27-oct (Gadea delegó en su Claude «lo más lógico, orgánico, en la línea de la arquitectura, sin añadir
de más»): A pasando por B; sin plan elegido, los 2-3 candidatos del contexto; sin total del grupo en el texto;
descuentos, el online siempre y el de grupo cuando aplica.

Paso 1, EN SOMBRA: qué importes tocan en este turno, calculados por código con lo que sabe el estado al acabar el turno
(las personas de CALN-2, el origen, la moneda, el plan), y se apunta en la traza frente a los que dio la respuesta. No
cambia nada de lo que ve el cliente. Los importes salen de `hechos` (los mismos ayudantes que ya usa el escritor: el
plan base o los paquetes de varios días, los dos orígenes y las dos monedas si no se saben): aquí solo se decide QUÉ
actividades cotizar.
"""
from __future__ import annotations

import logging
import re

from src.domain import activities as dom
from src.flows import hechos as hechos_mod

logger = logging.getLogger("uvicorn.error")


def actividades_a_cotizar(state) -> list[str]:
    """Las del grupo (CALN-2) o la elegida o por la que pregunta; sin ninguna, los candidatos que deja lo que se sabe
    (decisión 2: los 2-3 del contexto, nunca el catálogo): certificado, el buceo; sin certificar, el minicurso y el
    snorkel; si solo se sabe que quiere bucear, el buceo y el minicurso."""
    reparto = [a for a, n in (state.detected_group_allocation or {}).items() if n and dom.by_id(a) is not None]
    if reparto:
        return reparto
    for actividad in (state.detected_activity, state.actividad_preguntada, state.suggested_activity):
        registro = dom.by_id(actividad) if actividad else None
        if registro is not None and not registro.generic:
            return [actividad]
    if state.is_certified is True:
        return ["certified_diving"]
    if state.is_certified is False:
        return ["minicourse", "snorkel"]
    return ["certified_diving", "minicourse"] if getattr(state, "quiere_bucear", False) else []


def cotizar(state) -> dict:
    """La pieza de precios del turno: las actividades, los importes (cifras, sin separadores) y lo que falta saber."""
    actividades = actividades_a_cotizar(state)
    bloques = hechos_mod.hechos(state, ["precio"], actividades) if actividades else []
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
