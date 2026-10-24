"""gen-16 (21-oct), flag `referido_no_pregunta_nivel`: a quien quiere TERMINAR aquí un Open Water empezado (el extractor
lee el Referido) no se le pregunta si ya tiene el curso o si quiere sacarlo.

Banco docs/robustness/gen/dialogos-gen16-repreguntas.json (g16-terminar-ow) en PRE: «¿ya tienen el Curso referido (Open
Water) o quieren sacarla con el curso?» 2/2 → con el flag, la reserva sigue con cuántas personas 2/2; el Advanced y
«quiero hacer el Open Water» igual.
"""


from src.agents.intent_detector import DetectedIntent
from src.agents.nucleo import extraction
from src.flows.state import ConversationState

MENSAJE = "empecé el Open Water en mi país e hice la teoría y la piscina; quiero terminar las inmersiones aquí"


def _con_actividad(actividad):
    intent = DetectedIntent()
    intent.activity = actividad
    intent.detected_fields = ["activity"]
    return intent


def test_el_referido_no_pregunta_el_nivel(monkeypatch):
    monkeypatch.setattr(extraction, "course_level_is_ambiguous", lambda message: True)
    st = ConversationState(conversation_id="gen16", language="es")
    extraction._flag_cert_or_course(_con_actividad("padi_open_water_referral"), st, MENSAJE)
    assert st.needs_cert_or_course is False


def test_otro_curso_ambiguo_sigue_preguntando(monkeypatch):
    """«Somos 4 open water» sin decir si lo tienen o lo quieren: se sigue preguntando (decisión del owner, 15-sep)."""
    monkeypatch.setattr(extraction, "course_level_is_ambiguous", lambda message: True)
    st = ConversationState(conversation_id="gen16", language="es")
    extraction._flag_cert_or_course(_con_actividad("padi_open_water"), st, "somos 4 open water")
    assert st.needs_cert_or_course is True
