"""gen-1 + gen-3 (20-oct, fase GEN; docs/robustness/gen/gen1-diagnostico.md). El pase por tema sensible era una respuesta
fija que se comía el resto del mensaje. Tres arreglos (eran flags; promocionados y borrados en sim-5):

- `contesta_antes_de_pasar`: con un tema médico o el clima, el RAG contesta las OTRAS preguntas y después va el pase.
- `clima_con_politica`: el aviso del clima dice antes cuándo operamos y qué pasa si el mar no está apto.
- `dieta_no_es_medica`: una dieta o una alergia alimentaria no es tema médico (se lee al importar el tool del
  enrutador; aquí se prueba el texto que se añade)."""

import pytest

from src.agents import escalation_agent as ea
from src.agents import supervisor
from src.agents.escalation import SENSITIVE_RULES, _rule_message
from src.flows.state import ConversationState, Step

ASMA_Y_EDADES = "tengo asma leve, ¿puedo hacer el minicurso? ¿y desde qué edad pueden bucear mis hijos?"
EDADES = "El snorkel es desde los 6 años y el minicurso desde los 10."
MEDICO = {"sensitive_topic": "medical_questions", "asks_question": True}


def _estado() -> ConversationState:
    st = ConversationState(conversation_id="gen3-pase", language="es")
    st.detected_language = "es"
    st.step = Step.MAIN_MENU
    return st


@pytest.fixture
def rag(monkeypatch):
    llamadas = []

    def poner(respuesta):
        async def falso(query, **kw):
            llamadas.append(kw.get("extra_context") or "")
            return respuesta

        monkeypatch.setattr(supervisor, "rag_answer", falso)
        return llamadas

    return poner


async def test_con_el_flag_contesta_lo_demas_y_luego_pasa(monkeypatch, rag):
    llamadas = rag(EDADES)
    st = _estado()
    out = await ea.escalation_node({"conv_state": st, "message": ASMA_Y_EDADES, "signals": dict(MEDICO)})
    assert out["reply"].startswith(EDADES)
    assert "staff" in out["reply"]  # la línea del pase va después
    assert st.step == Step.ESCALATE and st.pending_escalation_reason == "medical_questions"
    assert "su salud o una condición médica" in llamadas[0]  # el RAG sabe qué NO tiene que contestar


@pytest.mark.parametrize("respuesta", ["NADA", "Nada.", "", None])
async def test_si_no_hay_nada_mas_que_contestar_el_pase_va_solo(monkeypatch, rag, respuesta):
    rag(respuesta)
    out = await ea.escalation_node({"conv_state": _estado(), "message": "tengo asma, ¿puedo bucear?",
                                    "signals": dict(MEDICO)})
    assert out["reply"].startswith("Para preguntas médicas")


async def test_una_queja_se_pasa_sin_llamar_al_rag(monkeypatch, rag):
    llamadas = rag(EDADES)
    await ea.escalation_node({"conv_state": _estado(), "message": "esto es una estafa, ¿y el horario?",
                              "signals": {"sensitive_topic": "complaints_or_emergencies", "asks_question": True}})
    assert not llamadas


async def test_si_el_rag_falla_el_pase_va_solo(monkeypatch):

    async def roto(query, **kw):
        raise TimeoutError("lento")

    monkeypatch.setattr(supervisor, "rag_answer", roto)
    out = await ea.escalation_node({"conv_state": _estado(), "message": ASMA_Y_EDADES, "signals": dict(MEDICO)})
    assert out["reply"].startswith("Para preguntas médicas")


def test_el_aviso_del_clima():
    assert "25 de diciembre" in _rule_message(SENSITIVE_RULES["weather_conditions"], "es")


def test_la_dieta_no_es_medica_en_la_definicion():
    import copy

    from src.prompts import router

    tool = copy.deepcopy(router.ROUTING_TOOL)
    router.con_lo_que_no_es_medico(tool)
    router.con_lo_que_no_es_medico(tool)  # una sola vez aunque se llame desde Jev y desde el enrutador de respaldo
    desc = tool["function"]["parameters"]["properties"]["sensitive_topic"]["description"]
    assert desc.count("celiac") == 1 and "must be left 'none' here." in desc
    # Sparring s30a (decisión de Gadea, 30-oct): el mareo y el embarazo tampoco son médicos (los contesta la base).
    assert desc.count("SEASICKNESS") == 1 and desc.count("PREGNANCY") == 1


async def test_el_rag_no_cree_que_el_pase_ya_esta_hecho(monkeypatch, rag):
    """Con el paso ya en ESCALATE, `tras_pase_recuerda_el_pase` le decía al RAG que el asesor ya tenía el caso."""
    llamadas = rag(EDADES)
    await ea.escalation_node({"conv_state": _estado(), "message": ASMA_Y_EDADES, "signals": dict(MEDICO)})
    assert "YA está pasada" not in llamadas[0]
