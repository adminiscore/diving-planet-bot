"""Punto 2 (26-oct, decisión de Gadea): ¿copia un criterio de examen una regla o un dato del negocio en vez de citarlo?

Los criterios citan las decisiones (`data/knowledge_base/decisiones.json`, «(decisión «moneda»)») y «lo que dice la base»
para los datos. Esto lo comprueban, con las MISMAS reglas, el test que vigila el golden
(tests/test_golden_sin_reglas_copiadas.py) y el generador de exámenes (scripts/generar_examen_sintetico.py), que quita los
criterios que copian. Los datos del CLIENTE (su edad, la cifra que cita, la moneda que pide) no cuentan: son contexto.
"""
from __future__ import annotations

import re

from src.domain import valores

CITA = re.compile(r"decisión «([a-z0-9-]+)»")


def reglas_copiadas(texto: str) -> list[str]:
    """Qué copia el criterio: «moneda», «origen», «hora» o «decision» (vacío si nada)."""
    malas = []
    if (re.search(r"\b(USD|COP)\b", texto) and re.search(r"nacionalidad|extranjer|colombian|residente|mixto", texto, re.I)
            and "«moneda»" not in texto):
        malas.append("moneda")
    if (re.search(r"antes de (cotizar|dar (un |el )?precio)", texto, re.I)
            and re.search(r"\bsale|salen|origen|Cartagena|islas", texto) and "«origen-y-precio»" not in texto):
        malas.append("origen")
    if any(re.search(rf"(?<![\d:]){re.escape(h)}(?!\d)", texto) for h in valores.horas_oficiales()):
        malas.append("hora")
    if re.search(r"[Dd]ecisi[oó]n (de|del) (Gadea|owner|negocio|moneda)", texto):
        malas.append("decision")
    return malas
