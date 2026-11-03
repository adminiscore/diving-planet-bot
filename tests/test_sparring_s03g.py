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


def test_s03a_en_dive_to_heal_pedir_o_aceptar_el_asesor_pasa():
    """s03a (tanda de Álvaro, 6/6): dentro de DIVE TO HEAL, «sí, pásame con el asesor» o un «sí» a la oferta del asesor
    no pasaba nunca a una persona (el texto del programa y el RAG contestaban antes). Ahora pasa."""
    import asyncio

    from src.agents.escalation_agent import escalation_node
    from src.agents.info_agent import info_node
    from src.flows.state import Step

    oferta = "Sí, con DIVE TO HEAL. ¿Quieres que te pase con un asesor para darte todos los detalles?"
    for nodo, mensaje, senales in ((info_node, "sí", {}), (info_node, "Sí, pásame con el asesor", {"wants_human": True}),
                                   (escalation_node, "Sí, ¿cuánto cuesta? pásame con el asesor", {"wants_human": True})):
        st = ConversationState(conversation_id="s03a", language="es")
        st.step, st.adaptive_diving_context = Step.MAIN_MENU, True
        st.history = [{"role": "user", "content": "uso silla de ruedas"}, {"role": "assistant", "content": oferta}]
        out = asyncio.run(nodo({"conv_state": st, "message": mensaje, "signals": senales}))
        assert st.step == Step.ESCALATE and st.pending_escalation_reason, (nodo.__name__, mensaje, out)
