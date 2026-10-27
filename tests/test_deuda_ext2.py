"""DEUDA-EXT2 (26-oct; Gadea #2006). Banco docs/robustness/lat/banco-deuda-ext2.json (A = PRE 18/24, B 24/24) y
banco-lat11 (24/24).

1. «PADI open water, advanced open water and deep diver certs» (contestando a «¿cuántas personas?») daba el curso
   Open Water a quien ya lo tiene (3 de 3 en PRE) y el redactor de hechos le cotizaba el curso. Quien está certificado
   no se saca el Open Water. Probado también en el prompt: no lo arreglaba y daba 3 inventos de is_certified en ex0.
2. «Voy con una amiga que no está certificada»: una persona más, en singular y sin total: son 2.
3. Al sumar a alguien sin actividad principal ni total, quien escribe también cuenta («viene mi novio…» daba 1).
4. Con la mayor parte del grupo sin decidir, la principal sigue pendiente (no la del acompañante).
"""

from src.agents import conversational_core as core
from src.agents.intent_detector import DetectedIntent
from src.agents.nucleo import extraction as core_extraction
from src.agents.nucleo import extractor as core_extractor
from src.flows.state import ConversationState


def _intent():
    return DetectedIntent()


def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="deuda-ext2", language="es")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def test_el_curso_open_water_no_es_para_quien_ya_esta_certificado():
    it = _intent()
    core_extractor._poner_actividad(it, _estado(), {"activity": "padi_open_water", "is_certified": True})
    assert it.activity is None
    it = _intent()
    core_extractor._poner_actividad(it, _estado(is_certified=True, detected_is_certified=True),
                                    {"activity": "padi_open_water"})
    assert it.activity is None


def test_quien_no_esta_certificado_si_se_saca_el_open_water():
    for datos in ({"activity": "padi_open_water"}, {"activity": "padi_open_water", "is_certified": False}):
        it = _intent()
        core_extractor._poner_actividad(it, _estado(), datos)
        assert it.activity == "padi_open_water"


def test_el_advanced_de_un_certificado_sigue():
    it = _intent()
    core_extractor._poner_actividad(it, _estado(), {"activity": "padi_advanced", "is_certified": True})
    assert it.activity == "padi_advanced"


def test_una_persona_mas_sin_actividad_son_dos():
    st = _estado()
    core_extraction._contar_al_acompanante_sin_actividad(st, "voy con una amiga que no está certificada",
                                                        {"companion_is_singular": True})
    assert st.detected_group_size == 2


def test_en_plural_o_con_total_no_se_toca():
    st = _estado()
    core_extraction._contar_al_acompanante_sin_actividad(st, "vienen unos amigos que no están certificados",
                                                        {"companion_is_singular": False})
    assert st.detected_group_size is None
    st = _estado(detected_group_size=4)
    core_extraction._contar_al_acompanante_sin_actividad(st, "voy con una amiga", {"companion_is_singular": True})
    assert st.detected_group_size == 4


def test_una_persona_mas_y_otras_en_plural_no_son_dos():
    """CALN2-04 (banco-edades e1): la esposa en singular, pero también las hijas: el total no es 2."""
    st = _estado()
    core_extraction._contar_al_acompanante_sin_actividad(
        st, "Voy con mi esposa, que no bucea, y nuestras hijas de 8 y 5", {"companion_is_singular": True})
    assert st.detected_group_size is None


def test_sin_principal_ni_total_quien_escribe_cuenta():
    st = _estado()
    core._merge_companion_activity(st, "minicourse", 1)
    assert st.detected_group_allocation == {"minicourse": 1}
    assert st.detected_group_size == 2


def test_con_la_mayoria_sin_decidir_la_principal_sigue_pendiente():
    assert core_extractor._principal_del_grupo_repartido(_estado(), {"snorkel": 1, "undecided": 2}) is None
    assert core_extractor._principal_del_grupo_repartido(
        _estado(), {"certified_diving": 2, "snorkel": 1, "undecided": 1}) == "certified_diving"
