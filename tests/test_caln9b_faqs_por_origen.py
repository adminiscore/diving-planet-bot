"""CALN-9b (3-nov, minis de la 0.46): las FAQ que mezclaban los dos orígenes («el almuerzo solo el primer día para quienes
salen desde Cartagena; si ya estás en las islas, no está incluido») hacían mezclar al escritor lo que incluye cada plan.
En la base van partidas por origen y, con el origen sabido, la del otro no llega al escritor. Sin red."""
from scripts.kb_v2 import build_kb_v2
from src.agents.rag_agent import fichas_del_origen


def _faqs():
    return [d for d in build_kb_v2() if d["metadata"]["source"] == "faqs"]


def test_las_faq_mixtas_van_partidas_por_origen():
    claves = {(d["metadata"]["key"], d["metadata"].get("origin")) for d in _faqs()}
    for faq in ("11", "99", "101", "122", "acompanante"):
        assert (f"faq:{faq}:cartagena", "cartagena") in claves and (f"faq:{faq}:islas", "islas") in claves
        assert not any(k == f"faq:{faq}" for k, _ in claves)
    assert ("faq:16", "islas") in claves and ("faq:12", None) in claves
    islas = next(d["content"] for d in _faqs() if d["metadata"]["key"] == "faq:99:islas" and d["metadata"]["lang"] == "es")
    assert "no está incluido" in islas and "desde Cartagena" not in islas


def test_con_el_origen_sabido_solo_llega_la_faq_de_su_origen():
    docs = [d for d in _faqs() if d["metadata"]["lang"] == "en"
            and d["metadata"]["key"] in ("faq:12", "faq:99:cartagena", "faq:99:islas")]
    claves = [d["metadata"]["key"] for d in fichas_del_origen(docs, "cartagena", "en")]
    assert claves == ["faq:12", "faq:99:cartagena"]
    assert [d["metadata"]["key"] for d in fichas_del_origen(docs, None, "en")] == [d["metadata"]["key"] for d in docs]
