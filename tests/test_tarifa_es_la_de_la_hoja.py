"""VAL-BASE (26-oct): cada tarifa de `pricing.json` es la de la hoja original del negocio
(`data/excel_exports/TARIFA 2026 UNO POR UNO.json`, la exportación de TARIFA 2026 UNO POR UNO.xltx).

`test_tarifa_cuadra.py` mira que cada precio cuadre con el resto de la tarifa; si el negocio pone un precio raro a
propósito, se confirma allí. Lo que no veía es una tarifa copiada en el servicio equivocado: hasta el 26-oct, desde las
islas, los pesos de los dos paquetes de 4 inmersiones estaban cruzados (el de 4 diurnas llevaba los 830.000 COP del de
3 diurnas + 1 nocturna, y al revés). Cada cifra existía en la hoja, así que el 21-oct se dio por buena; el bot la daba a
los clientes. Aquí, para cada servicio, la fila de la hoja en dólares (por su precio pleno y con descuento) y la fila de
la hoja en pesos (por su precio) tienen que ser LA MISMA fila.
"""
import json
import re
import unicodedata
from pathlib import Path

import pytest

TARIFA = json.loads(Path("data/knowledge_base/pricing.json").read_text(encoding="utf-8-sig"))
HOJA = json.loads(Path("data/excel_exports/TARIFA 2026 UNO POR UNO.json").read_text(encoding="utf-8"))
HOJAS = {"from_cartagena": ("CARTAGENA PESOS", "CARTAGENA DOLARES"), "from_islands": ("ISLA PESOS", "ISLA DOLARES")}
# Servicios que no están en la hoja de mayo: el negocio los añadió después (Bubble Makers: precios definitivos, Gadea,
# 26-oct).
FUERA_DE_LA_HOJA = {"bubble_makers"}


def _plano(texto) -> str:
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]+", " ", texto).strip()


def _numero(valor):
    try:
        return float(str(valor).replace(",", "."))
    except ValueError:
        return None


def _filas(nombre_hoja: str) -> dict[str, tuple]:
    hoja = next(h for h in HOJA["sheets"] if h["name"] == nombre_hoja)
    filas = {}
    for fila in hoja["grid"]:
        if isinstance(fila, list) and len(fila) >= 5 and _plano(fila[1]) and _numero(fila[4]):
            filas[_plano(fila[1])] = (_numero(fila[4]), _numero(fila[5]) if len(fila) > 5 else None)
    return filas


def _servicios():
    for origen in HOJAS:
        for grupo in TARIFA[origen].values():
            if isinstance(grupo, dict):
                for clave, fila in grupo.items():
                    if isinstance(fila, dict) and "usd_online" in fila and clave not in FUERA_DE_LA_HOJA:
                        yield origen, clave, fila


def _cerca(a, b, margen) -> bool:
    return a is not None and b is not None and abs(a - b) < margen


@pytest.mark.parametrize("origen,clave,fila", list(_servicios()), ids=lambda x: x if isinstance(x, str) else "")
def test_dolares_y_pesos_son_de_la_misma_fila_de_la_hoja(origen, clave, fila):
    pesos, dolares = (_filas(h) for h in HOJAS[origen])
    en_dolares = {n for n, (plena, descuento) in dolares.items()
                  if _cerca(descuento, fila["usd_online"], 0.01) and _cerca(plena, fila["usd_normal"], 0.6)}
    en_pesos = {n for n, (uno, otro) in pesos.items()
                if _cerca(uno, fila["cop_online"], 1) or _cerca(otro, fila["cop_online"], 1)}
    assert en_dolares, f"{origen}.{clave}: sus dólares no están en la hoja"
    assert en_pesos, f"{origen}.{clave}: sus pesos no están en la hoja"
    assert en_dolares & en_pesos, (f"{origen}.{clave}: los dólares son de {sorted(en_dolares)} y los pesos de "
                                   f"{sorted(en_pesos)} (¿copiados en el servicio equivocado?)")


def test_revisa_casi_toda_la_tarifa():
    """Control: si la exportación cambia de forma, el test de arriba no miraría nada."""
    assert len(list(_servicios())) >= 40
