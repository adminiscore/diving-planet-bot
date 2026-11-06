"""El pase a una persona, en una función (6-nov, decisión de Gadea #3664).

Antes, 14 sitios de 9 ficheros repetían las mismas líneas (paso ESCALATE, sin botones, motivo y nota). Ahora todos llaman
a `lead_summary.pasar_a_persona`. Este test falla si alguien vuelve a marcar el pase a mano en `src`."""

import re
from pathlib import Path

from src.agents.lead_summary import pasar_a_persona
from src.flows.state import ConversationState, Step

_SRC = Path(__file__).resolve().parents[1] / "src"
_MARCA_EL_PASE = re.compile(r"\.pending_escalation_reason\s*=(?!=)|\.step\s*=\s*Step\.ESCALATE\b")
# Los dos únicos sitios que pueden: la función, y chatwoot, que borra el motivo cuando el pase se ha hecho.
_PERMITIDOS = {("agents/lead_summary.py", "state.step = Step.ESCALATE"),
               ("agents/lead_summary.py", "state.pending_escalation_reason = motivo"),
               ("channels/chatwoot.py", "state.pending_escalation_reason = None")}


def test_nadie_marca_el_pase_fuera_de_la_funcion():
    fuera = []
    for f in sorted(_SRC.rglob("*.py")):
        rel = f.relative_to(_SRC).as_posix()
        for n, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if _MARCA_EL_PASE.search(linea) and (rel, linea.strip()) not in _PERMITIDOS:
                fuera.append(f"{rel}:{n}: {linea.strip()}")
    assert not fuera, "marcan el pase a mano; usad lead_summary.pasar_a_persona:\n" + "\n".join(fuera)


def test_el_pase_marca_paso_motivo_nota_y_quita_los_botones():
    st = ConversationState(conversation_id="t")
    st.quick_replies = [{"title": "Sí"}]
    pasar_a_persona(st, "solicitó asesor")
    assert st.step == Step.ESCALATE
    assert st.pending_escalation_reason == "solicitó asesor"
    assert st.quick_replies == []
    assert "solicitó asesor" in (st.pending_note or "")


def test_sin_nota_ni_botones_para_los_datos_sensibles():
    st = ConversationState(conversation_id="t")
    st.quick_replies = [{"title": "Sí"}]
    pasar_a_persona(st, "datos sensibles detectados", con_nota=False, sin_botones=False)
    assert st.step == Step.ESCALATE
    assert st.pending_escalation_reason == "datos sensibles detectados"
    assert st.quick_replies == [{"title": "Sí"}]
    assert not st.pending_note
