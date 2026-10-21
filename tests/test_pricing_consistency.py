"""ord-3 (21-oct, decisión de Gadea, Coral #1150): la tarifa vive en UN sitio, `pricing.json`.

Antes había dos copias de cada precio (services.json y pricing.json) y este test comprobaba que fueran iguales. Ahora
cada servicio de services.json dice qué fila de la tarifa es la suya (`tarifa`) y `catalog` le pone los precios al
cargar. Aquí se comprueba que el enlace no se rompe y que no vuelve a haber copias:

- ningún servicio lleva precios propios;
- cada `tarifa` existe y tiene sus cuatro precios;
- toda fila de la tarifa con precio la usa un servicio, es el acompañante o dice por qué no se ofrece;
- las notas de precio no repiten cifras (se quedarían viejas al cambiar la tarifa).
"""
import json
import re
from pathlib import Path

import pytest

from src.flows import catalog

SERVICES = json.loads(Path("data/knowledge_base/services.json").read_text(encoding="utf-8-sig"))["services"]
CAMPOS = ("price_usd", "price_usd_normal", "price_cop", "price_cop_normal")
COLUMNAS = ("usd_online", "usd_normal", "cop_online", "cop_normal")
SIN_PRECIO = {"divemaster", "private"}  # se cotizan con un asesor


def _filas_con_precio():
    for origen in ("from_cartagena", "from_islands"):
        for categoria, filas in catalog.TARIFA[origen].items():
            if not isinstance(filas, dict):
                continue
            for clave, fila in filas.items():
                if isinstance(fila, dict) and "usd_online" in fila:
                    yield f"{origen}.{categoria}.{clave}", fila


def test_ningun_servicio_lleva_precios_propios():
    con_precio = sorted(sid for sid, s in SERVICES.items() if any(c in s for c in CAMPOS))
    assert not con_precio, f"precios copiados en services.json (van en pricing.json): {con_precio}"


@pytest.mark.parametrize("service_id", sorted(SERVICES))
def test_cada_servicio_apunta_a_una_fila_con_sus_cuatro_precios(service_id):
    ruta = SERVICES[service_id].get("tarifa")
    if service_id in SIN_PRECIO:
        assert ruta is None
        return
    assert ruta, f"{service_id} no dice qué fila de la tarifa es la suya"
    fila = catalog.fila_de_la_tarifa(ruta)
    assert all(fila.get(c) is not None for c in COLUMNAS), f"{service_id} -> {ruta}: faltan precios"
    assert "no_se_ofrece" not in fila, f"{service_id} -> {ruta}: esa fila dice que no se ofrece"
    assert [catalog.SERVICES[service_id][c] for c in CAMPOS] == [fila[c] for c in COLUMNAS]


def test_toda_fila_con_precio_se_usa_o_dice_por_que_no():
    usadas = {s["tarifa"] for s in SERVICES.values() if s.get("tarifa")}
    acompanante = "from_cartagena.servicios_buceo_snorkel.acompanante"
    sueltas = [ruta for ruta, fila in _filas_con_precio()
               if ruta not in usadas and ruta != acompanante and not fila.get("no_se_ofrece")]
    assert not sueltas, f"filas con precio sin servicio ni motivo («no_se_ofrece»): {sueltas}"


def test_el_acompanante_sale_de_su_fila():
    fila = catalog.fila_de_la_tarifa("from_cartagena.servicios_buceo_snorkel.acompanante")
    assert catalog.COMPANION_PRICE == {c: fila[c] for c in COLUMNAS}


def test_las_notas_de_precio_no_repiten_cifras():
    cifra = re.compile(r"\$\s?\d|\d[\d.,]*\s*(?:USD|COP)\b")
    con_cifras = [f"{sid}.{k}" for sid, s in SERVICES.items() for k, v in s.items()
                  if k.startswith("price_note") and cifra.search(v or "")]
    assert not con_cifras, f"cifras en notas de precio (salen de la tarifa): {con_cifras}"
