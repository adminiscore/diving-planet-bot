"""CALN-43, la tabla del plan: qué plan le toca a un buzo certificado, según lo que ha dicho. Decisiones de Gadea (6-nov), una por fila en
`docs/robustness/caln/tablas-decisiones.md`; las prueba `tests/test_plan_de_buceo.py`, sin IA. Aquí no se lee al cliente ni se redacta: entra lo ya
leído y sale la decisión.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.domain import activities as dom

SALIDA_DE_UN_DIA = 2  # las inmersiones del plan de siempre


@dataclass(frozen=True)
class Plan:
    inmersiones: int  # el paquete del catálogo (`dom.dive_packages`)
    veces: int = 1  # cuántas salidas de un día: una reserva por día
    asesor_cierra_el_precio: bool = False  # el paquete, sin hacer su nocturna


def paquetes_de(dias: int | None) -> list[int]:
    """Las inmersiones de los paquetes de esos días (varios), de menor a mayor. Del catálogo."""
    return sorted(n for n, (d, _) in dom.dive_packages().items() if d == dias) if dias and dias > 1 else []


def plan_de_buceo(*, inmersiones: int | None = None, dias: int | None = None, sin_nocturna: bool = False, salidas_sueltas: int | None = None,
                  origen: str | None = None, refresher_solo: bool = False) -> Plan:
    """`inmersiones`: la cifra que eligió el cliente, que manda. `dias`: los días de buceo que quiere. `sin_nocturna`: la rechaza o quiere solo mañanas.
    `salidas_sueltas`: cuántas salidas de un día pidió. `origen`: cartagena, island o None. `refresher_solo`: va una persona y hace el refresher, que
    ocupa uno de esos días."""
    if salidas_sueltas and inmersiones in (None, SALIDA_DE_UN_DIA):
        return Plan(SALIDA_DE_UN_DIA, veces=salidas_sueltas)
    if inmersiones:
        return Plan(inmersiones)
    if dias and refresher_solo:
        dias -= 1
    paquetes = paquetes_de(dias)
    if not paquetes:
        return Plan(SALIDA_DE_UN_DIA)
    if len(paquetes) == 1:
        # P5: 3 o 4 días sin nocturna: el mismo paquete, que la lleva, sin hacerla; el precio lo cierra un asesor.
        return Plan(paquetes[0], asesor_cierra_el_precio=sin_nocturna)
    if sin_nocturna and origen == "cartagena":
        # P2 y P3: durmiendo en Cartagena, una salida cada día; el paquete obliga a dormir en las islas.
        return Plan(SALIDA_DE_UN_DIA, veces=dias)
    return Plan(paquetes[0])  # P1 y P4: el pequeño, sin nocturna
