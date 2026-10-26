"""Punto 2 (26-oct, decisión de Gadea): los criterios de los exámenes CITAN las decisiones del negocio
(`data/knowledge_base/decisiones.json`) y los datos de la base, no los copian. El 26-oct, al decidir la moneda, 18
criterios del golden visible se quedaron desfasados porque decían «sin nacionalidad, USD»: es el mismo problema de datos
repetidos que lat-deuda-u arregló en la base, pero en el examen. Las reglas de la comprobación están en
`scripts/criterios_sin_reglas.py` (las mismas que usa el generador de exámenes). Si falla, el criterio debe citar la
decisión («(decisión «moneda»)») o «lo que dice la base» en vez de escribir la regla o el dato. De un criterio del
examen oculto solo se dice cuántos fallan, nunca su id."""
import json
from pathlib import Path

import pytest

from scripts.criterios_sin_reglas import CITA, reglas_copiadas

RAIZ = Path(__file__).resolve().parents[1]
GOLDEN = RAIZ / "docs/robustness/golden-set/golden-dialogues.json"
DECISIONES = RAIZ / "data/knowledge_base/decisiones.json"


def _criterios():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8-sig"))
    ocultos = {d["id"] for d in golden["dialogues"] if d.get("suite") == "oculto"}
    for d in golden["dialogues"]:
        for c in d["criteria"]:
            yield ("(oculto)" if d["id"] in ocultos else f"{d['id']}::{c['id']}"), c["check"]
    for c in golden["global_criteria"]:
        yield f"global:{c['id']}", c["check"]


def test_cada_decision_citada_existe():
    ids = {d["id"] for d in json.loads(DECISIONES.read_text(encoding="utf-8"))["decisiones"]}
    citadas = {cita for _, texto in _criterios() for cita in CITA.findall(texto)}
    assert citadas, "ningún criterio cita una decisión: ¿cambió el formato de la cita?"
    assert citadas <= ids, f"decisiones citadas que no están en decisiones.json: {sorted(citadas - ids)}"


@pytest.mark.parametrize("que", ["moneda", "origen", "hora", "decision"])
def test_ningun_criterio_copia_la_regla(que):
    malos = [donde for donde, texto in _criterios() if que in reglas_copiadas(texto)]
    visibles = [m for m in malos if m != "(oculto)"]
    ocultos = len(malos) - len(visibles)
    assert not malos, f"criterios que copian «{que}»: {visibles}" + (f" y {ocultos} del oculto" if ocultos else "")


@pytest.mark.parametrize("texto,esperado", [
    ("Da el precio en USD por no ser colombiano.", ["moneda"]),
    ("Da el precio en la moneda que manda la decisión «moneda» (no es colombiano).", []),
    ("Da en COP, que es lo que pide el cliente, el precio del snorkel.", []),
    ("Antes de dar un precio, pregunta si sale desde Cartagena.", ["origen"]),
    ("Indica el Muelle de la Bodeguita a las 8:00 a. m.", ["hora"]),
    ("Decisión de Gadea 18-oct: no pasa a un asesor.", ["decision"]),
])
def test_las_reglas_de_la_comprobacion(texto, esperado):
    assert reglas_copiadas(texto) == esperado
