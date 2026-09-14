"""Una definicion por campo en los prompts (centralizacion, 2026-09-15).

La descripcion del tool y las guias de verificacion EN/ES de `is_certified`,
`location` e `is_colombian` salen de `_FIELD_MEANING_EN/ES`. Antes eran tres textos
que ya divergian. Medido: eval-set 217/223 sin casos a peor (y arreglo el residente
"no soy colombiano pero vivo en colombia").
"""

import pytest

from src.prompts import booking

FIELDS = ("is_certified", "location", "is_colombian")


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
