"""MEJ-2 (21-oct): la tarifa tiene que cuadrar consigo misma, para que un error de la tarifa no llegue al cliente.

`test_pricing_consistency.py` comprueba que `services.json` y `pricing.json` dicen lo mismo, pero los dos vienen del
mismo CSV de tarifas: si el CSV trae un error, está en los dos. Aquí, cada precio se compara con el resto de la tarifa:

- el precio en USD equivale al de COP con el mismo cambio que los demás (±6 % de la mediana);
- el precio online es la tarifa plena con el 10 % de descuento (±1,5 puntos), en COP y en USD.

Así salieron, el 21-oct, siete precios que no cuadraban (los paquetes de 4, 5, 7 y 9 inmersiones desde las islas, el
Rescue desde las islas y el snorkel nocturno). Gadea los confirmó el mismo día (documento «Revisión de la base de Coral
(2026)»): son los buenos. Quedan en `EXCEPCIONES_CONFIRMADAS` con el precio confirmado; si la tarifa cambia uno, el test
pide volver a confirmarlo. 26-oct (VAL-BASE): dos de ellos, los paquetes de 4 inmersiones desde las islas, no eran precios
raros sino los pesos cruzados entre los dos (ver `test_tarifa_es_la_de_la_hoja.py`); corregidos según la hoja, cuadran
y salen de la lista.
"""

import json
import statistics
from pathlib import Path

import pytest

TARIFA = json.loads(Path("data/knowledge_base/pricing.json").read_text(encoding="utf-8-sig"))

TOLERANCIA_CAMBIO = 0.06
TOLERANCIA_DESCUENTO = 0.015

# (origen, servicio) -> (COP online, USD online) que el negocio confirmó aunque no cuadren con el resto (Gadea, 21-oct).
EXCEPCIONES_CONFIRMADAS = {
    ("from_islands", "paquete_5_buceos"): (1000000, 318.6),
    ("from_islands", "paquete_7_buceos"): (1375000, 432),
    ("from_islands", "paquete_9_buceos"): (1695000, 544.5),
    ("from_islands", "curso_rescate_efr"): (2550000, 648),
    ("from_islands", "snorkel_nocturno"): (170000, 52.2),  # dólar redondo, dado por bueno
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
    s = SERVICIOS[clave]
    if clave in EXCEPCIONES_CONFIRMADAS:
        assert (s["cop_online"], float(s["usd_online"])) == EXCEPCIONES_CONFIRMADAS[clave], (
            f"{clave} cambió de precio: vuelve a confirmarlo con el negocio y actualiza EXCEPCIONES_CONFIRMADAS")
        return
    fallos = _fallos(s)
    assert not fallos, f"{clave}: {'; '.join(fallos)}"


def test_las_excepciones_existen_en_la_tarifa():
    assert set(EXCEPCIONES_CONFIRMADAS) <= set(SERVICIOS)
