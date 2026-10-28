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

lat-11 T6e (26-oct): el tool y el prompt de la extracción del relleno (`fill_gaps`) se quitaron, y sus tests.
"""

import pytest

from src.domain import activities as dom

LANGS = ["es", "en"]


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
