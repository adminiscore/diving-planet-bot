"""Los `enum` del schema tienen que aparecer ENUMERADOS en el texto del prompt.

Hallazgo 2026-09-12 (probe contra el modelo real desde PRE): para "primer nivel
de buceo" el modelo devolvia `'certificarse'` -- una palabra tomada del propio
texto de la regla, no un valor del enum -- de forma REPRODUCIBLE (10/10 con
temperature=0.0). Declarar `enum` en el schema NO basta ni con `tool_choice`
forzado.

El primer arreglo fue escribir la lista a mano en la regla de `activity`. Eso
era un PARCHE: `EXTRACTION_TOOL` y `SIGNALS_TOOL` tienen 5 campos con enum
(`activity`, `duration`, `location`, `recall_field`, `companion_activity`) y
DOS prompts que los consumen (`extraction_system_prompt` para `fill_gaps` y
`fields_verification_system_prompt` para el veto). Cubrir uno de los cinco en
uno de los dos deja la misma bomba puesta en los otros.

Ahora la lista se GENERA desde el schema (`_enum_values_sentence`). Estos tests
son la barrera estructural: no comprueban `activity` en particular, sino que
**todo** campo con enum quede cubierto en **ambos** prompts. Un campo o un valor
nuevo los hace fallar solo, sin que nadie se acuerde de este hallazgo.
"""

import pytest

from src.prompts.booking import (
    _ENUM_VALUE_GLOSSES_EN,
    _ENUM_VALUE_GLOSSES_ES,
    _FIELD_VERIFICATION_RULES_ES,
    EXTRACTION_TOOL,
    SIGNALS_TOOL,
    _enum_values_sentence,
    _field_enum,
    extraction_system_prompt,
    fields_verification_system_prompt,
)

LANGS = ["es", "en"]


def _enum_fields(tool):
    props = tool["function"]["parameters"]["properties"]
    return [f for f in props if _field_enum(f, tool)]


def test_there_are_enum_fields_to_guard():
    """Si esto falla, el resto de tests pasarian en vacio."""
    assert _enum_fields(EXTRACTION_TOOL)
    assert _enum_fields(SIGNALS_TOOL)


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("field", _enum_fields(EXTRACTION_TOOL))
def test_fill_gaps_prompt_enumerates_every_enum_field(field, lang):
    """`fill_gaps` pide campos sin resolver: si uno tiene enum, el prompt tiene
    que decir cuales son los valores."""
    prompt = extraction_system_prompt(lang, [field])
    faltan = [v for v in _field_enum(field) if v not in prompt]
    assert not faltan, f"{field} ({lang}): el prompt de fill_gaps no enumera {faltan}"


@pytest.mark.parametrize("lang", LANGS)
def test_verification_prompt_enumerates_every_enum_field_it_can_verify(lang):
    """Mismo contrato para el prompt del veto, sobre los campos que tienen
    regla de verificacion."""
    verificables = [f for f in _FIELD_VERIFICATION_RULES_ES if _field_enum(f)]
    assert verificables, "ningun campo verificable tiene enum: test en vacio"
    for field in verificables:
        prompt = fields_verification_system_prompt([field], lang)
        faltan = [v for v in _field_enum(field) if v not in prompt]
        assert not faltan, f"{field} ({lang}): el prompt del veto no enumera {faltan}"


@pytest.mark.parametrize("lang", LANGS)
def test_batched_verification_prompt_keeps_every_enum(lang):
    """El veto agrupa N campos en UNA peticion: al agrupar no se puede perder
    la lista de ninguno."""
    fields = list(_FIELD_VERIFICATION_RULES_ES)
    prompt = fields_verification_system_prompt(fields, lang)
    for field in fields:
        for value in _field_enum(field) or []:
            assert value in prompt, f"{field}={value} ({lang}) se pierde al agrupar"


@pytest.mark.parametrize("lang", LANGS)
def test_fields_without_enum_add_nothing(lang):
    """Booleanos y enteros no llevan lista: el mecanismo no debe ensuciar sus
    prompts."""
    assert _enum_values_sentence("group_size", lang) == ""
    assert _enum_values_sentence("is_certified", lang) == ""


@pytest.mark.parametrize("lang", LANGS)
def test_signals_tool_enums_are_renderable(lang):
    """`SIGNALS_TOOL` todavia no consume el mecanismo, pero el helper tiene que
    saber renderizarlo: es la puerta para engancharlo sin reescribir nada."""
    for field in _enum_fields(SIGNALS_TOOL):
        sentence = _enum_values_sentence(field, lang, SIGNALS_TOOL)
        for value in _field_enum(field, SIGNALS_TOOL):
            assert value in sentence


# -- Las glosas, que son la parte que NO se deriva del schema -----------------

@pytest.mark.parametrize("glosses", [_ENUM_VALUE_GLOSSES_ES, _ENUM_VALUE_GLOSSES_EN])
def test_glosses_never_name_a_value_that_left_the_schema(glosses):
    """Una glosa huerfana es texto que dice al modelo que existe un valor que
    el schema ya no acepta -- exactamente el fallo que se esta arreglando, del
    reves."""
    for field, per_value in glosses.items():
        enum = _field_enum(field) or _field_enum(field, SIGNALS_TOOL) or []
        huerfanas = [v for v in per_value if v not in enum]
        assert not huerfanas, f"{field}: glosas de valores inexistentes {huerfanas}"


@pytest.mark.parametrize("lang", LANGS)
def test_certified_diving_is_glossed_as_the_default_not_as_already_certified(lang):
    """Una glosa no es decoracion: la primera version gloso `certified_diving`
    como "para quien YA esta certificado", contradiciendo la regla escrita
    encima, y REGRESIONO "uno quiere buceo y el otro snorkel" a `minicourse`
    (medido A/B, 2026-09-12)."""
    sentence = _enum_values_sentence("activity", lang).lower()
    marcador = "por defecto" if lang == "es" else "default"
    assert marcador in sentence


# ── Las REGLAS por campo: una sola fuente, un solo consumidor ────────────────
#
# `_FIELD_RULES_*` (semantica) y `_FIELD_DETECTOR_HINTS_*` ("asi falla el
# detector") estan separados para no duplicar texto, pero HOY solo los consume el
# prompt del veto.
#
# Se intento que `fill_gaps` viera tambien la semantica -- parecia la misma
# centralizacion que se hizo con los enums -- y se midio que es MALA idea: el
# eval-set bajo de 202/207 a 197/207 y los 5 casos nuevos que fallaban eran todos
# abstenciones de `fill_gaps`. Estas reglas estan escritas para verificar y van
# cargadas de "no inventes"/"abstenerse es mejor"; en un prompt cuya tarea es
# rellenar, eso hace que no rellene. Ver el comentario largo en booking.py.
#
# Estos tests fijan ese reparto para que el resultado negativo no se pierda.

from src.prompts.booking import (  # noqa: E402
    _FIELD_DETECTOR_HINTS_EN,
    _FIELD_DETECTOR_HINTS_ES,
    _FIELD_RULES_ES,
    _field_guidance,
)


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("field", list(_FIELD_RULES_ES))
def test_verification_prompt_carries_every_shared_field_rule(field, lang):
    """El veto SI consume la regla completa (semantica + pista + enum)."""
    prompt = fields_verification_system_prompt([field], lang)
    assert _field_guidance(field, lang, with_hints=True) in prompt


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("field", list(_FIELD_RULES_ES))
def test_fill_gaps_prompt_does_not_carry_the_verification_rules(field, lang):
    """RESULTADO NEGATIVO MEDIDO: meterlas aqui costo 5 casos del eval-set y no
    arreglo lo que las motivaba. Si alguien las vuelve a enchufar tal cual, este
    test se lo dice antes de gastar una tanda entera."""
    prompt = extraction_system_prompt(lang, [field])
    rule = _FIELD_RULES_ES[field] if lang == "es" else None
    if rule:
        assert rule not in prompt


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("field", list(_FIELD_DETECTOR_HINTS_ES))
def test_detector_hints_reach_the_veto_but_never_fill_gaps(field, lang):
    """Las pistas de "asi suele fallar el detector" solo tienen sentido cuando hay
    un valor previo del que desconfiar."""
    hints = _FIELD_DETECTOR_HINTS_ES if lang == "es" else _FIELD_DETECTOR_HINTS_EN
    hint = hints[field]
    assert hint.strip() in fields_verification_system_prompt([field], lang)
    assert hint.strip() not in extraction_system_prompt(lang, [field])


def test_a_field_with_enum_but_no_rule_still_gets_its_values():
    """`duration` tiene enum y no tiene regla: la guia debe ser la lista de
    valores, no una cadena vacia."""
    assert "duration" not in _FIELD_RULES_ES
    guidance = _field_guidance("duration", "es", with_hints=False)
    assert "single_day" in guidance and "multi_day" in guidance
