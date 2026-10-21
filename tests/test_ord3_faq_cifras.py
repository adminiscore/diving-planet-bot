"""ord-3 (21-oct, decisión de Gadea, Coral #1150): toda cifra de precio de las FAQ curadas (las que lee el RAG, base
kb_v2) tiene que estar en la tarifa, `pricing.json`. Si la tarifa cambia y la FAQ no, este test lo dice.

Se compara con las cuatro columnas de todas las filas (online y normal, USD y COP), redondeando los USD a la unidad como
los escriben las FAQ ("124 USD" para 124,2).
"""
import json
import re
from pathlib import Path

from src.flows import catalog

FAQS = json.loads(Path("data/knowledge_base/curada/faqs.json").read_text(encoding="utf-8-sig"))["faqs"]
_USD = re.compile(r"(?:US\$|\$)\s?(\d+(?:[.,]\d{1,2})?)(?!\d)|(\d+(?:[.,]\d{1,2})?)\s?(?:USD|dólares|dollars)\b",
                  re.IGNORECASE)
_COP = re.compile(r"(\d{1,3}(?:[.,]\d{3})+)\s?(?:COP|pesos)\b", re.IGNORECASE)

# Cifras de precio que no son de un servicio de la tarifa, con su motivo.
FUERA_DE_LA_TARIFA = {
    (130, "10"): "suplemento de Nitrox por tanque (no es un servicio de la tarifa)",
    (130, "20"): "suplemento de Nitrox para 2 inmersiones (no es un servicio de la tarifa)",
}


def _tarifa():
    usd, cop = set(), set()
    for origen in ("from_cartagena", "from_islands"):
        for filas in catalog.TARIFA[origen].values():
            for fila in (filas.values() if isinstance(filas, dict) else []):
                if isinstance(fila, dict) and "usd_online" in fila:
                    usd |= {round(float(fila["usd_online"])), round(float(fila["usd_normal"]))}
                    cop |= {int(fila["cop_online"]), int(fila["cop_normal"])}
    return usd, cop


def test_las_cifras_de_las_faq_curadas_estan_en_la_tarifa():
    usd, cop = _tarifa()
    fuera = []
    for faq in FAQS:
        texto = " ".join(faq.get(k) or "" for k in ("answer_es", "answer_en"))
        for a, b in _USD.findall(texto):
            cifra = a or b
            if (faq.get("origen"), cifra) in FUERA_DE_LA_TARIFA:
                continue
            if round(float(cifra.replace(",", "."))) not in usd:
                fuera.append(f"FAQ {faq.get('origen')}: {cifra} USD")
        for cifra in _COP.findall(texto):
            if int(re.sub(r"[.,]", "", cifra)) not in cop:
                fuera.append(f"FAQ {faq.get('origen')}: {cifra} COP")
    assert not fuera, f"cifras de las FAQ curadas que no están en la tarifa: {fuera}"


def test_las_excepciones_siguen_existiendo():
    """Si alguien quita o cambia la cifra de la excepción, la excepción sobra."""
    for (origen, cifra) in FUERA_DE_LA_TARIFA:
        faq = next(f for f in FAQS if f.get("origen") == origen)
        assert cifra in faq["answer_es"]
