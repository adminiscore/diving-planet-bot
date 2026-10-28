"""CALN-7 (28-oct, Gadea): el escritor dice lo que la política exige. De los fallos que se repiten ronda tras ronda, en
tres el dato no estaba en los hechos de la pregunta: la preparación de la ficha (las 4 h de teoría), el formulario
médico sin actividad elegida y los requisitos del refresher cuando el buzo lo necesita (docs/robustness/caln/
estudio-caln7-politicas.md)."""
from src.agents import redactor_hechos
from src.flows import hechos as h
from src.flows.state import ConversationState


def _conv(**campos):
    st = ConversationState(conversation_id="caln7", language="es")
    for campo, valor in campos.items():
        setattr(st, campo, valor)
    return st


def test_los_requisitos_de_un_servicio_llevan_su_preparacion():
    [b] = h.hechos(_conv(location="island"), ["requisitos"], ["padi_advanced"])
    assert any("al menos 4 horas" in r for r in b["requisitos"])


def test_sin_preguntar_requisitos_la_preparacion_no_va():
    [b] = h.hechos(_conv(location="island"), ["precio"], ["padi_advanced"])
    assert "requisitos" not in b


def test_los_requisitos_sin_actividad_llevan_el_formulario_medico():
    [b] = h.hechos_sin_actividad(_conv(), ["requisitos"])
    assert any("formulario médico" in r for r in b["requisitos"])


def test_el_buzo_que_necesita_el_refresher_recibe_los_requisitos_del_refresher():
    st = _conv(language="en")
    assert redactor_hechos._actividad(st, {"activity": "certified_diving", "refresher_interested": True}) == "refresher"
    assert redactor_hechos._actividad(st, {"activity": "certified_diving"}) == "certified_diving"
    # Si PREGUNTA por el buceo certificado, se le contesta de eso (arq-1n).
    assert redactor_hechos._actividad(st, {"actividad_preguntada": "certified_diving",
                                           "refresher_interested": True}) == "certified_diving"


def test_lo_que_de_un_plan_confirma_un_asesor_va_con_sus_hechos():
    """Rotativa 010: «¿la de 9 puede hacer Bubble Makers?» sin la nota de que el traslado, el horario y el almuerzo
    desde Cartagena los confirma un asesor (solo estaba en el catálogo de todos los turnos)."""
    [b] = h.hechos(_conv(), ["edad"], ["bubble_makers"])
    assert "asesor" in b["lo_confirma_un_asesor"]["cartagena"]
    assert "lo_confirma_un_asesor" not in h.hechos(_conv(location="island"), ["edad"], ["bubble_makers"])[0]
    assert "lo_confirma_un_asesor" not in h.hechos(_conv(), ["precio"], ["snorkel"])[0]
