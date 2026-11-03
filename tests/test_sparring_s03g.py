"""Sparring s03g (3-nov, contra PRE 0.42; docs/robustness/g3/hallazgos.md, CALN-S03G-01): el paquete de 4 inmersiones
desde las islas no tiene enlace de reserva en la base y el bot daba la página informativa como «Book here». Sin enlace,
ninguno: lo reserva un asesor. Sin red."""
from src.flows import hechos
from src.flows.catalog import SERVICES
from src.flows.state import ConversationState


def test_sin_enlace_de_reserva_en_la_base_no_se_da_la_pagina_informativa():
    assert SERVICES["4_dives_2_days_already_on_island"]["booking_url"] is None
    assert SERVICES["2_dives_1_day"]["booking_url"].startswith("https://book.divingplanet.org/")


def test_el_plan_sin_enlace_lo_reserva_un_asesor():
    st = ConversationState(conversation_id="s03g", language="en")
    st.location, st.is_colombian, st.is_certified = "island", False, True
    st.selected_service = "4_dives_2_days_already_on_island"
    [b] = hechos.hechos(st, ["enlace"], ["certified_diving"])
    assert b["enlace"] == {"asesor": True} and "como_reservar" not in b
    st.selected_service = "2_dives_1_day_already_on_island"
    [b] = hechos.hechos(st, ["enlace"], ["certified_diving"])
    assert b["enlace"]["island"].startswith("https://book.divingplanet.org/")


def test_un_grupo_de_uno_no_trae_menores_aunque_diga_baby():
    """s03g (miami t3): «since I was a baby» marca niños; con el grupo en 1 no se preguntan edades."""
    from src.agents import conversational_core as core

    st = ConversationState(conversation_id="s03g-baby", language="en")
    st.detected_activity, st.location, st.is_colombian = "minicourse", "cartagena", False
    st.kids_mention_detected = True
    st.detected_group_size = 2
    assert core.next_missing_slot(st) == core.SLOT_AGES
    st.detected_group_size = 1
    assert core.next_missing_slot(st) != core.SLOT_AGES
