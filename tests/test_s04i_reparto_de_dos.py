"""Sparring s04i (4-nov, embarazada): «mi esposo es buzo Advanced… y yo snorkel». La pregunta de «¿ya la tienen o quieren
sacarla?» salía 3 veces, el extractor dejaba al esposo sin elegir aunque la lectura sabía qué hace, y el escritor decía
«selecciona 2 personas en cada enlace»: pagaría el doble."""
from src.agents import conversational_core as core
from src.agents import lector_grupo
from src.agents.rutas.contexto_rag import _build_extra_context
from src.flows.state import ConversationState


def _st(**campos) -> ConversationState:
    st = ConversationState(conversation_id="s04i", language="es")
    st.detected_activity, st.location = "snorkel", "cartagena"
    for campo, valor in campos.items():
        setattr(st, campo, valor)
    return st


def test_sin_saberlo_se_pregunta():
    assert core.next_missing_slot(_st(needs_cert_or_course=True)) == core.SLOT_CERT_OR_COURSE


def test_con_un_buzo_en_el_reparto_no_se_pregunta():
    st = _st(needs_cert_or_course=True, detected_group_size=2,
             detected_group_allocation={"certified_diving": 1, "snorkel": 1})
    assert core.next_missing_slot(st) != core.SLOT_CERT_OR_COURSE


def test_con_la_certificacion_ya_dicha_no_se_pregunta():
    assert core.next_missing_slot(_st(needs_cert_or_course=True, is_certified=True)) != core.SLOT_CERT_OR_COURSE


def _persona(quien, actividad, certificado=None):
    return {"quien": quien, "cantidad": 1, "certificado": certificado, "actividad": actividad, "edades": [], "cita": quien}


LECTURA = {"total_dicho": 2, "personas": [_persona("esposo", "certified_diving", True), _persona("cliente", "snorkel")]}


def test_si_la_lectura_decide_a_mas_gente_manda_ella():
    datos = {"activity": "snorkel", "group_size": 2, "group_allocation": {"snorkel": 1, "undecided": 1}}
    salida, cambios = lector_grupo.completar(datos, LECTURA)
    assert salida["group_allocation"] == {"certified_diving": 1, "snorkel": 1}
    assert cambios


def test_si_no_decide_a_mas_gente_queda_lo_del_extractor():
    lectura = {"total_dicho": 2, "personas": [_persona("esposo", None, True), _persona("cliente", "snorkel")]}
    datos = {"activity": "snorkel", "group_size": 2, "group_allocation": {"snorkel": 1, "undecided": 1}}
    salida, _ = lector_grupo.completar(datos, lectura)
    assert salida["group_allocation"] == {"snorkel": 1, "undecided": 1}


def test_si_decide_a_otro_que_no_es_buzo_queda_lo_del_extractor():
    # banco g40: el niño de 4 que el extractor deja sin elegir
    lectura = {"total_dicho": 3, "personas": [_persona("padres", "snorkel"), _persona("niño", "snorkel"), _persona("cliente", "snorkel")]}
    datos = {"activity": "snorkel", "group_size": 3, "group_allocation": {"snorkel": 2, "undecided": 1}}
    assert lector_grupo.completar(datos, lectura)[0]["group_allocation"] == {"snorkel": 2, "undecided": 1}


def test_el_reparto_del_extractor_sin_sin_decidir_no_se_toca():
    datos = {"activity": "snorkel", "group_size": 2, "group_allocation": {"minicourse": 1, "snorkel": 1}}
    assert lector_grupo.completar(datos, LECTURA)[0]["group_allocation"] == {"minicourse": 1, "snorkel": 1}


def test_el_escritor_sabe_quien_hace_que():
    contexto = _build_extra_context(_st(detected_group_size=2, detected_group_allocation={"certified_diving": 1, "snorkel": 1}))
    assert "Quién hace qué: 1 × " in contexto and "solo a las personas de esa actividad" in contexto


def test_con_una_sola_actividad_no_se_dice():
    contexto = _build_extra_context(_st(detected_group_size=2, detected_group_allocation={"snorkel": 2}))
    assert "Quién hace qué" not in contexto
