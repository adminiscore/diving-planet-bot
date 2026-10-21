"""MEJ-2 (21-oct): la tarifa tiene que cuadrar consigo misma, para que un error de la tarifa no llegue al cliente.

`test_pricing_consistency.py` comprueba que `services.json` y `pricing.json` dicen lo mismo, pero los dos vienen del
mismo CSV de tarifas: si el CSV trae un error, está en los dos. Aquí, cada precio se compara con el resto de la tarifa:

- el precio en USD equivale al de COP con el mismo cambio que los demás (±6 % de la mediana);
- el precio online es la tarifa plena con el 10 % de descuento (±1,5 puntos), en COP y en USD.

Así salieron, el 21-oct, los USD cruzados de los dos paquetes de 4 inmersiones desde las islas, los paquetes de 5, 7
y 9 desde las islas más caros en USD y el Rescue desde las islas más barato. Están en `PENDIENTES_DE_ANDRES` hasta que
el negocio diga el precio bueno (documento «Revisión de la base de Coral (2026)»). Cuando se corrija uno, el test pide
sacarlo de la lista: la lista no puede quedarse vieja.
"""

import json
import statistics
from pathlib import Path

import pytest

TARIFA = json.loads(Path("data/knowledge_base/pricing.json").read_text(encoding="utf-8-sig"))

TOLERANCIA_CAMBIO = 0.06
TOLERANCIA_DESCUENTO = 0.015

# (origen, servicio) -> por qué no cuadra. Se quitan cuando el negocio confirme o corrija el precio.
PENDIENTES_DE_ANDRES = {
    ("from_islands", "paquete_4_buceos_diurnos"): "USD cruzado con el paquete mixto (204,3 por ≈ 234)",
    ("from_islands", "paquete_4_buceos_mixto"): "USD cruzado con el de 4 diurnas (235,8 por ≈ 203)",
    ("from_islands", "paquete_5_buceos"): "USD un 12 % más caro que su COP",
    ("from_islands", "paquete_7_buceos"): "USD un 11 % más caro que su COP",
    ("from_islands", "paquete_9_buceos"): "USD un 14 % más caro que su COP",
    ("from_islands", "curso_rescate_efr"): "USD un 10 % más barato que su COP",
    ("from_islands", "snorkel_nocturno"): "USD redondo (52,2), un 8 % por encima de su COP",
}


def _servicios():
    for origen in ("from_cartagena", "from_islands"):
        for grupo, items in TARIFA[origen].items():
            if not isinstance(items, dict):
                continue
            for clave, s in items.items():
                if isinstance(s, dict) and s.get("cop_online") and s.get("usd_online"):
                    yield (origen, clave), s


SERVICIOS = dict(_servicios())
CAMBIO = statistics.median(s["cop_online"] / float(s["usd_online"]) for s in SERVICIOS.values())


def _fallos(s: dict) -> list[str]:
    fallos = []
    cambio = s["cop_online"] / float(s["usd_online"])
    if abs(cambio / CAMBIO - 1) > TOLERANCIA_CAMBIO:
        fallos.append(f"{cambio:.0f} COP por USD (la tarifa va a {CAMBIO:.0f})")
    for moneda in ("cop", "usd"):
        online, plena = s.get(f"{moneda}_online"), s.get(f"{moneda}_normal")
        if online and plena and abs(1 - float(online) / float(plena) - 0.10) > TOLERANCIA_DESCUENTO:
            fallos.append(f"online {online} frente a plena {plena} en {moneda.upper()}: no es el 10 %")
    return fallos


def test_la_tarifa_tiene_servicios_de_los_dos_origenes():
    assert {o for o, _ in SERVICIOS} == {"from_cartagena", "from_islands"}
    assert len(SERVICIOS) > 30


@pytest.mark.parametrize("clave", sorted(SERVICIOS), ids=lambda c: f"{c[0]}.{c[1]}")
def test_cada_precio_cuadra_con_la_tarifa(clave):
    fallos = _fallos(SERVICIOS[clave])
    if clave in PENDIENTES_DE_ANDRES:
        assert fallos, f"{clave} ya cuadra: sácalo de PENDIENTES_DE_ANDRES"
        pytest.xfail(f"pendiente de Andrés: {PENDIENTES_DE_ANDRES[clave]}")
    assert not fallos, f"{clave}: {'; '.join(fallos)}"


def test_los_pendientes_existen_en_la_tarifa():
    assert set(PENDIENTES_DE_ANDRES) <= set(SERVICIOS)
