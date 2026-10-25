"""ARQ-8h (23-oct, decisión de Álvaro por Gadea, #1634; flag `descuentos_un_sitio`): los descuentos, en UN sitio.

Estaban en cinco: discounts.json, pricing.json `discount_policies` (lo que indexaba el RAG: sin tildes, el 5 % de equipo
sin «solo buceo recreativo y cursos PADI» y con el nombre interno del sistema de reservas), un texto fijo del catálogo,
avisos.json y ejemplos del prompt. Con el flag, el catálogo, los hechos y el índice los leen de discounts.json, y el de
grupo lleva la nota del acompañante (la base no dice si entra: lo confirma el equipo al pedir el descuento). Sin red."""
import json
from pathlib import Path

import pytest

from src.flows import catalog, hechos
from src.flows.state import ConversationState

DISCOUNTS = json.loads((Path(__file__).resolve().parents[1] / "data/knowledge_base/discounts.json")
                       .read_text(encoding="utf-8-sig"))["discounts"]


@pytest.mark.parametrize("lang", ["es", "en"])
def test_la_base_tiene_la_nota_del_acompanante(lang):
    assert DISCOUNTS["group_discount"][f"companion_note_{lang}"]


@pytest.mark.parametrize("lang", ["es", "en"])
def test_el_catalogo_lee_la_base(lang):
    texto = catalog.catalog_facts(lang)
    for d in ("online_direct_booking", "group_discount", "own_equipment_discount"):
        assert DISCOUNTS[d][f"description_{lang}"] in texto
    assert DISCOUNTS["group_discount"][f"companion_note_{lang}"] in texto
    assert "10% online (" not in texto  # el texto fijo de antes, fuera


def test_los_hechos_llevan_la_nota():
    assert any(DISCOUNTS["group_discount"]["companion_note_es"] in x for x in hechos._descuentos(ConversationState(conversation_id="arq8h", language="es"), "es"))


def test_el_indice_lee_la_base():
    from scripts.load_embeddings import load_knowledge_base

    docs = [d for d in load_knowledge_base() if str(d["metadata"].get("section", "")).startswith("discount_")]
    textos = " ".join(d["content"] for d in docs)
    assert DISCOUNTS["own_equipment_discount"]["description_es"] in textos  # con «solo buceo recreativo y cursos»
    assert DISCOUNTS["group_discount"]["companion_note_en"] in textos
    assert "roverd" not in textos.lower()
    assert {"discount_group_discount", "discount_own_equipment", "discount_online_booking",
            "discount_colombian_cop_pricing", "discount_policies"} == {d["metadata"]["section"] for d in docs}
