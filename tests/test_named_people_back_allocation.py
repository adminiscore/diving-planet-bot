"""Una persona nombrada respalda una cifra 1 del reparto (2026-09-15).

"mi amigo tiene licencia, yo no": el LLM devolvia bien {certified_diving: 1,
undecided: 1} y total 2, pero la comprobacion de cifras del nucleo exigia un numero
escrito y tiraba el reparto entero. Ahora cuentan las personas nombradas, mas quien
escribe cuando nombra a otra, todo o nada (solo si respaldan todas las cifras), y el
total incluye a las personas sin actividad. Los plurales vagos siguen sin respaldar nada.

Ademas, la peticion fusionada (verificar + rellenar) pierde los campos del grupo: si
vuelve sin ellos y el mensaje trae senal de grupo, se piden solos.
"""

from unittest.mock import patch

import pytest

from src.agents import conversational_core as cc
from src.agents import supervisor
from src.agents.nucleo import extraction as core_extraction
from src.flows.state import ConversationState


@pytest.fixture(autouse=True)
def _grupo_camino_antiguo(monkeypatch):
    """Estos tests fijan el grupo por el camino de antes de ex-7 (regex y redes LLM); con `extraccion_llm_grupo` lo
    decide el extractor (tests/test_ex7_grupo.py)."""


@pytest.fixture(autouse=True)
def _camino_viejo_de_actividad(monkeypatch):
    """Estos tests prueban el camino viejo (regex + veto/relleno). Con ex-8 (`extraccion_llm_actividad`) la actividad y
    la nacionalidad las decide el extractor "LLM primero": tests/test_ex8_actividad_nacionalidad.py."""


def test_one_piece_for_a_singular_person():
    """El acompanante singular y el conteo de personas usan la misma pieza: antes cada
    uno tenia su lista de determinantes ("un|una|mi|a" frente a "mi|my|su|el...")."""
    from src.agents.intent_detector import _SINGULAR_PERSON

    assert cc._NAMED_PERSON_RE.pattern == _SINGULAR_PERSON
    assert _SINGULAR_PERSON in cc._SINGULAR_COMPANION_RE.pattern
    # Hueco que cierra la pieza compartida: "my" no estaba en la lista del acompanante.
    assert cc._SINGULAR_COMPANION_RE.search("my wife wants to snorkel")


@pytest.mark.parametrize("message, singular", [
    ("viene mi novia", True),
    ("my wife wants to snorkel", True),
    ("viene uno que quiere bucear", True),               # sin persona nombrada: extras
    ("vamos 3, mi pareja y yo buceamos y mi suegra hace snorkel", False),
    ("my daughter is 9 and my son is 12, my wife and i dive", False),
    ("vienen mis amigos", False),
])
def test_singular_companion_needs_exactly_one_person(message, singular):
    assert cc._singular_companion(message) is singular


async def _understand_with_llm(message, llm_patch, combined=None, **state_fields):
    """`llm_patch` es lo que devuelve `fill_gaps`; `combined`, lo que devuelve la peticion
    fusionada (por defecto, lo mismo)."""
    calls = []

    async def fake_extract(*args, **kwargs):
        calls.append("extract_and_verify")
        return dict(llm_patch if combined is None else combined), {}

    async def fake_fill(*args, **kwargs):
        calls.append(("fill_gaps", tuple(kwargs.get("only_fields") or ())))
        return dict(llm_patch)

    state = ConversationState(conversation_id="named-people")
    state.language = "es"
    for name, value in state_fields.items():
        setattr(state, name, value)
    with (
        patch.object(cc, "extract_and_verify", fake_extract, create=True),
        patch.object(core_extraction, "fill_gaps", fake_fill),
        patch.object(supervisor.settings, "llm_group_size_veto_cutover", True),
        patch.object(supervisor.settings, "llm_group_allocation_veto_cutover", True),
    ):
        await cc._understand(state, message)
    return state, calls


@pytest.mark.asyncio
async def test_named_people_keep_the_split_and_the_total():
    state, _ = await _understand_with_llm(
        "mi amigo tiene licencia, yo no", {"group_allocation": {"certified_diving": 1, "undecided": 1}},
    )
    assert state.detected_group_allocation == {"certified_diving": 1}
    assert state.pending_undecided_qty == 1
    assert state.detected_group_size == 2        # antes: 1, sin la persona pendiente
    assert state.is_certified is None            # la licencia es del amigo, no del cliente


@pytest.mark.asyncio
async def test_writer_counts_even_without_saying_yo():
    state, _ = await _understand_with_llm(
        "soy certificado y mi hijo no", {"group_allocation": {"certified_diving": 1, "undecided": 1}},
    )
    assert state.detected_group_allocation == {"certified_diving": 1}
    assert state.detected_group_size == 2


@pytest.mark.asyncio
async def test_partial_backing_never_stores_a_partial_split():
    # "mis primos" es plural: el 3 de snorkel no tiene respaldo, asi que no se guarda
    # un reparto a medias y el bot pregunta.
    state, _ = await _understand_with_llm(
        "yo buceo, mi amigo y mis primos hacen snorkel",
        {"group_allocation": {"certified_diving": 1, "snorkel": 3}},
    )
    assert state.detected_group_allocation is None


@pytest.mark.asyncio
async def test_vague_plural_still_needs_a_number():
    state, _ = await _understand_with_llm(
        "yo buceo y mis amigos hacen snorkel", {"group_allocation": {"certified_diving": 1, "snorkel": 4}},
        detected_group_size=5,
    )
    assert state.detected_group_allocation is None
    assert state.detected_group_size == 5


@pytest.mark.asyncio
async def test_a_level_someone_holds_is_not_the_course_in_the_split():
    # "mi pareja tiene el advanced": el LLM puso 1/2 {padi_advanced: 1}.
    state, _ = await _understand_with_llm(
        "mi pareja tiene el advanced y yo no tengo nada",
        {"group_size": 2, "group_allocation": {"padi_advanced": 1, "undecided": 1}},
    )
    assert state.detected_group_allocation == {"certified_diving": 1}
    assert state.detected_group_size == 2


@pytest.mark.asyncio
async def test_total_backed_by_named_people_is_kept_without_a_split():
    # La segunda peticion devolvio solo el total: cuadra con novia + quien escribe.
    state, _ = await _understand_with_llm(
        "mi novia es buza certificada y yo nunca he buceado", {"group_size": 2}, combined={},
    )
    assert state.detected_group_size == 2


@pytest.mark.asyncio
async def test_named_people_never_override_a_known_total():
    state, _ = await _understand_with_llm(
        "tambien viene un amigo", {"group_size": 2}, detected_group_size=4,
    )
    assert state.detected_group_size == 4


@pytest.mark.asyncio
async def test_no_second_request_while_the_cert_or_course_question_is_pending():
    # "2 open water y 3 snorkel": nivel PADI sin decir si lo tienen o lo quieren. El bot
    # pregunta primero (owner); la segunda peticion guardaba {padi_open_water: 2, ...} (b05).
    state, calls = await _understand_with_llm(
        "2 open water y 3 snorkel",
        {"group_allocation": {"padi_open_water": 2, "snorkel": 3}},
        combined={},
        detected_group_size=5,
    )
    assert ("fill_gaps", ("group_allocation",)) not in calls
    assert state.detected_group_allocation is None
    assert state.needs_cert_or_course is True


