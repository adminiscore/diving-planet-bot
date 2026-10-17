"""CAL-D (17-oct, cal-74): la pregunta del origen de un plan con noche dice los DÍAS de su ficha.

"Where would you be departing from? This plan takes several days…" a un cliente del Open Water, que son 2 días
(`duration_days` de services.json). El dato estaba en el catálogo y la frase era fija. Ahora sale de la ficha del plan;
"varios días" queda solo cuando aún no se sabe qué plan es (un paquete sin concretar va de 2 a 4 días).
"""

from src.agents import conversational_core as cc
from src.flows.state import ConversationState


def _estado(idioma="es", **campos) -> ConversationState:
    return ConversationState(conversation_id="t", language=idioma, **campos)


def test_los_dias_salen_de_la_ficha_del_plan():
    assert cc._dias_del_plan(_estado(detected_activity="padi_open_water")) == 2
    assert cc._dias_del_plan(_estado(detected_activity="padi_open_water_referral")) == 2
    assert cc._dias_del_plan(_estado(detected_service_id="7_dives_3_days")) == 3
    # Buceo certificado sin plan concreto: los paquetes duran de 2 a 4 días, no se sabe.
    assert cc._dias_del_plan(_estado(detected_activity="certified_diving")) is None
    assert cc._dias_del_plan(_estado()) is None


def test_la_pregunta_del_origen_dice_los_dias_exactos():
    pregunta = cc.ask_slot(_estado("en", detected_activity="padi_open_water"), cc.SLOT_LOCATION)
    assert "takes 2 days" in pregunta and "several days" not in pregunta
    pregunta = cc.ask_slot(_estado("es", detected_activity="padi_open_water"), cc.SLOT_LOCATION)
    assert "dura 2 días" in pregunta and "varios días" not in pregunta


def test_sin_plan_concreto_se_queda_en_varios_dias():
    st = _estado("es", detected_activity="certified_diving", detected_duration="multi_day")
    assert "dura varios días" in cc.ask_slot(st, cc.SLOT_LOCATION)
