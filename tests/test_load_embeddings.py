"""Regression for a real bug found live 2026-07-17: the discount_policies
chunk built by scripts/load_embeddings.py silently embedded blank
descriptions for YEARS because it read "description_es"/"description_en"/
"name_es"/"name_en" keys that don't exist in data/knowledge_base/pricing.json
(the actual keys are just "es"/"en"). RAG had no real content to answer
"hay descuento por grupo?" and fell back to an advisor instead of correctly
saying it only applies to groups of 5+.
"""

from scripts.load_embeddings import load_knowledge_base


def _discount_policy_docs():
    docs = load_knowledge_base()
    return [
        d for d in docs
        if d.get("metadata", {}).get("source") == "pricing"
        and d.get("metadata", {}).get("section") == "discount_policies"
    ]


def test_discount_policy_docs_exist():
    docs = _discount_policy_docs()
    assert len(docs) == 2  # es + en


def test_discount_policy_content_is_not_blank():
    """Guards against the exact regression: every line used to render as
    "- name: " with nothing after the colon."""
    docs = _discount_policy_docs()
    for doc in docs:
        content = doc["content"]
        assert " - " not in content or ": " not in content.split("\n")[-1], (
            "discount line should be a full sentence, not a blank 'label: '"
        )
        for line in content.split("\n"):
            if line.startswith("-"):
                assert len(line.strip()) > 5, f"blank-looking discount line: {line!r}"


def test_group_discount_mentions_minimum_group_size():
    docs = _discount_policy_docs()
    es_doc = next(d for d in docs if d["metadata"]["lang"] == "es")
    assert "5 personas" in es_doc["content"]
    assert "10%" in es_doc["content"]

    en_doc = next(d for d in docs if d["metadata"]["lang"] == "en")
    assert "5 or more" in en_doc["content"]
    assert "10%" in en_doc["content"]


# --- Precision follow-up (2026-07-21, live PRE): the combined chunk mixes ----
# all 5 discount policies into one block, diluting retrieval for a specific
# question ("can i bring my own gear" scored 0.376, below the 0.40 threshold,
# competing with the other 4 unrelated policies in that same chunk). Each
# policy must ALSO be indexed on its own so a specific question retrieves a
# clean, single-topic chunk instead.

def _own_discount_section_docs():
    docs = load_knowledge_base()
    return [
        d for d in docs
        if d.get("metadata", {}).get("source") == "pricing"
        and str(d.get("metadata", {}).get("section", "")).startswith("discount_")
        and d["metadata"]["section"] != "discount_policies"
    ]


def test_individual_discount_policy_chunks_exist_per_language():
    docs = _own_discount_section_docs()
    sections = {d["metadata"]["section"] for d in docs}
    # One dedicated chunk per policy key in pricing.json's discount_policies.
    assert "discount_own_equipment" in sections
    assert "discount_group_discount" in sections
    langs_for_own_equipment = {d["metadata"]["lang"] for d in docs if d["metadata"]["section"] == "discount_own_equipment"}
    assert langs_for_own_equipment == {"es", "en"}


def test_own_equipment_discount_chunk_is_not_diluted_by_other_policies():
    docs = _own_discount_section_docs()
    own_equipment_es = next(
        d for d in docs if d["metadata"]["section"] == "discount_own_equipment" and d["metadata"]["lang"] == "es"
    )
    content = own_equipment_es["content"].lower()
    assert "5%" in content
    assert "equipo" in content
    # Must NOT contain the other policies' text — that's exactly the dilution bug.
    assert "grupos de 5 personas" not in content
    assert "roverd" not in content
