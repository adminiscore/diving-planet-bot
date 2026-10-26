"""Punto 2 (26-oct, decisión de Gadea): los criterios de los exámenes CITAN las decisiones del negocio
(`data/knowledge_base/decisiones.json`) y los datos de la base, no los copian. El 26-oct, al decidir la moneda, 18
criterios del golden visible se quedaron desfasados porque decían «sin nacionalidad, USD»: es el mismo problema de datos
repetidos que lat-deuda-u arregló en la base, pero en el examen. Este test vigila los exámenes que se juzgan con la
misma referencia (el golden con su oculto y los sintéticos que se generen): si falla, el criterio debe citar la
decisión («(decisión «moneda»)») o «lo que dice la base» en vez de escribir la regla o el dato. De un criterio del
examen oculto solo se dice cuántos fallan, nunca su id."""
import json
import re
from pathlib import Path

from src.domain import valores

RAIZ = Path(__file__).resolve().parents[1]
GOLDEN = RAIZ / "docs/robustness/golden-set/golden-dialogues.json"
DECISIONES = RAIZ / "data/knowledge_base/decisiones.json"
_CITA = re.compile(r"decisión «([a-z0-9-]+)»")


def _criterios():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8-sig"))
    ocultos = {d["id"] for d in golden["dialogues"] if d.get("suite") == "oculto"}
    for d in golden["dialogues"]:
        for c in d["criteria"]:
            yield ("(oculto)" if d["id"] in ocultos else f"{d['id']}::{c['id']}"), c["check"]
    for c in golden["global_criteria"]:
        yield f"global:{c['id']}", c["check"]


def _fallan(regla) -> list[str]:
    malos = [donde for donde, texto in _criterios() if regla(texto)]
    visibles = [m for m in malos if m != "(oculto)"]
    return visibles + ([f"{len(malos) - len(visibles)} del examen oculto"] if len(malos) > len(visibles) else [])


def test_cada_decision_citada_existe():
    ids = {d["id"] for d in json.loads(DECISIONES.read_text(encoding="utf-8"))["decisiones"]}
    citadas = {cita for _, texto in _criterios() for cita in _CITA.findall(texto)}
    assert citadas, "ningún criterio cita una decisión: ¿cambió el formato de la cita?"
    assert citadas <= ids, f"decisiones citadas que no están en decisiones.json: {sorted(citadas - ids)}"


def test_la_moneda_se_cita_no_se_copia():
    """Un criterio que dice en qué moneda va el precio según quién es el cliente cita la decisión «moneda». Si el
    cliente PIDE una moneda («¿y en pesos?»), eso es contexto y no hace falta citarla."""
    def copia(texto):
        return (re.search(r"\b(USD|COP)\b", texto) and re.search(r"nacionalidad|extranjer|colombian|residente|mixto",
                                                                  texto, re.I) and "«moneda»" not in texto)
    assert not _fallan(copia), f"criterios con la regla de la moneda copiada: {_fallan(copia)}"


def test_el_origen_antes_del_precio_se_cita_no_se_copia():
    def copia(texto):
        return (re.search(r"antes de (cotizar|dar (un |el )?precio)", texto, re.I)
                and re.search(r"\bsale|salen|origen|Cartagena|islas", texto) and "«origen-y-precio»" not in texto)
    assert not _fallan(copia), f"criterios con la regla del origen copiada: {_fallan(copia)}"


def test_ninguna_hora_oficial_escrita():
    """Las horas son de la base (`valores.json`): un criterio dice «la hora de salida que da la base»."""
    horas = valores.horas_oficiales()

    def copia(texto):
        return any(re.search(rf"(?<![\d:]){re.escape(h)}(?!\d)", texto) for h in horas)
    assert not _fallan(copia), f"criterios con una hora oficial escrita: {_fallan(copia)}"


def test_ninguna_decision_copiada_con_su_fecha():
    """«Decisión de Gadea 18-oct: …» copia la decisión dentro del criterio: va en decisiones.json y se cita por su id."""
    def copia(texto):
        return re.search(r"[Dd]ecisi[oó]n (de|del) (Gadea|owner|negocio|moneda)", texto)
    assert not _fallan(copia), f"criterios que copian una decisión: {_fallan(copia)}"
