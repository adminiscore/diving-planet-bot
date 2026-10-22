"""Una definicion por campo en el prompt de extraccion (centralizacion, 2026-09-15).

La descripcion del tool sale de `_FIELD_MEANING_EN`. Antes eran tres textos que ya divergian (el tool y las guias
de verificacion EN/ES). Las guias eran del veto y se quitaron con el en mej-1d (21-oct): queda la fuente unica del tool.
"""

import pytest

from src.prompts import booking

FIELDS = ("is_certified", "location", "is_colombian", "activity", "group_size", "group_allocation")


@pytest.mark.parametrize("field", FIELDS)
def test_tool_description_is_the_single_english_meaning(field):
    props = booking.EXTRACTION_TOOL["function"]["parameters"]["properties"]
    assert props[field]["description"] == booking._FIELD_MEANING_EN[field]


def test_residents_pay_as_colombians():
    """El hecho de negocio que ya se habia desincronizado."""
    assert "residents" in booking._FIELD_MEANING_EN["is_colombian"].lower()
