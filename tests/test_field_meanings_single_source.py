"""Una definicion por campo en los prompts (centralizacion, 2026-09-15).

La descripcion del tool y las guias de verificacion EN/ES salen de
`_FIELD_MEANING_EN/ES`. Antes eran tres textos que ya divergian. Primero para
`is_certified`, `location` e `is_colombian` y, en el punto 2, tambien para `activity`,
`group_size` y `group_allocation`.

Las reglas que solo sabia el veto (curso PADI nombrado, tramos con sustantivo, suma al
total) viven en `_FIELD_VERIFY_RULES_*` y solo entran en las guias: puestas en el tool
hicieron perder datos al camino de relleno (medido, ronda C).
"""

import pytest

from src.prompts import booking

FIELDS = ("is_certified", "location", "is_colombian", "activity", "group_size", "group_allocation")


@pytest.mark.parametrize("field", FIELDS)
def test_tool_description_is_the_single_english_meaning(field):
    props = booking.EXTRACTION_TOOL["function"]["parameters"]["properties"]
    assert props[field]["description"] == booking._FIELD_MEANING_EN[field]


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("lang,rules,meanings", [
    ("en", booking._FIELD_RULES_EN, booking._FIELD_MEANING_EN),
    ("es", booking._FIELD_RULES_ES, booking._FIELD_MEANING_ES),
])
def test_verification_rules_are_built_from_the_meaning(field, lang, rules, meanings):
    assert rules[field] == booking._meaning_rule(field, lang)
    assert meanings[field] in rules[field]


def test_residents_pay_as_colombians_in_every_copy():
    """El hecho de negocio que ya se habia desincronizado: esta en EN y ES."""
    assert "residents" in booking._FIELD_MEANING_EN["is_colombian"].lower()
    assert "residentes" in booking._FIELD_MEANING_ES["is_colombian"].lower()


@pytest.mark.parametrize("lang", ["en", "es"])
def test_rules_that_had_drifted_are_in_every_guide(lang):
    rules = booking._FIELD_RULES_EN if lang == "en" else booking._FIELD_RULES_ES
    # La regla `undecided` (decision del owner) no estaba en las guias de verificacion.
    assert "undecided" in rules["group_allocation"]
    # Las reglas del veto siguen en su guia, en los dos idiomas.
    assert ("noun" if lang == "en" else "sustantivo") in rules["group_allocation"]
    assert "PADI" in rules["activity"]


def test_verification_only_rules_never_reach_the_tool():
    props = booking.EXTRACTION_TOOL["function"]["parameters"]["properties"]
    for field, extra in booking._FIELD_VERIFY_RULES_EN.items():
        assert extra not in props[field]["description"]
