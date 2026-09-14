"""F2a del plan de dominio de actividades (docs/robustness/activity-domain-plan.md).

El registro (`data/knowledge_base/activities.json`) guarda DOS textos por actividad
con propositos distintos (decision del owner 2026-09-14, tras medir):

- `gloss`: corto y MEDIDO, para los prompts que EXTRAEN datos del cliente
  (fill_gaps, veto, combinada). Son las glosas que antes vivian copiadas a mano en
  `prompts/booking.py`, movidas a la fuente unica sin cambiar una letra.
- `for_whom`: contexto de negocio completo, para los prompts que ELIGEN entre
  actividades. Se probo meterlo en los de extraccion y cada frase movia lo que el
  modelo se atreve a rellenar (un caso del eval-set y dos de la bateria, en
  sentidos opuestos segun la redaccion), asi que no va ahi.
"""

import pytest

from src.domain import activities as dom
from src.prompts.booking import (
    _ENUM_VALUE_GLOSSES_EN,
    _ENUM_VALUE_GLOSSES_ES,
    EXTRACTION_TOOL,
    SIGNALS_TOOL,
    _field_enum,
    combined_extraction_system_prompt,
    extraction_system_prompt,
    fields_verification_system_prompt,
)

LANGS = ["es", "en"]


def test_every_activity_enum_value_exists_in_the_registry():
    ids = set(dom.activity_ids())
    for field, tool in (("activity", EXTRACTION_TOOL), ("companion_activity", SIGNALS_TOOL)):
        assert set(_field_enum(field, tool)) <= ids, f"{field} usa valores fuera del registro"


def test_activity_glosses_are_not_copied_by_hand_anymore():
    for glosses in (_ENUM_VALUE_GLOSSES_ES, _ENUM_VALUE_GLOSSES_EN):
        assert "activity" not in glosses
        assert "companion_activity" not in glosses


@pytest.mark.parametrize("lang", LANGS)
def test_extraction_prompts_carry_the_registry_gloss_not_the_full_context(lang):
    prompts = [
        extraction_system_prompt(lang, ["activity"]),
        fields_verification_system_prompt(["activity"], lang),
        combined_extraction_system_prompt(["group_size"], ["activity"], lang),
    ]
    glossed = [a for a in dom.registry().activities if a.gloss and a.id in _field_enum("activity")]
    assert glossed, "ninguna actividad del enum tiene gloss: test en vacio"
    for prompt in prompts:
        for activity in glossed:
            assert activity.gloss[lang] in prompt
            assert activity.for_whom[lang] not in prompt


@pytest.mark.parametrize("lang", LANGS)
def test_measured_glosses_survive_the_move(lang):
    """Glosas medidas A/B que no se pueden perder (2026-09-12): certified_diving
    es el DEFECTO tenga o no certificacion (la version "para quien ya esta
    certificado" regresiono) y Open Water cubre "primer nivel" (conv913)."""
    default = "por defecto" if lang == "es" else "default"
    first_level = "primer nivel" if lang == "es" else "first level"
    assert default in dom.by_id("certified_diving").gloss[lang].lower()
    assert first_level in dom.by_id("padi_open_water").gloss[lang].lower()


@pytest.mark.parametrize("lang", LANGS)
def test_certified_diving_context_never_defers_other_data(lang):
    """Medido 2026-09-14 (ablacion, 3/3 deterministas): "y eso se confirma despues"
    hacia que el extractor dejara de rellenar `is_certified`. Aunque `for_whom` ya
    no va a los prompts de extraccion, la regla vale para los de eleccion."""
    text = dom.by_id("certified_diving").for_whom[lang].lower()
    deferred = ("se confirma después", "se confirma despues") if lang == "es" else ("confirmed afterwards",)
    assert not any(phrase in text for phrase in deferred)
