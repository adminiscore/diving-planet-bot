"""Bloque 4P del Plan Gadea (10-nov): el pase y la posventa fuera de la reserva. Banco sin IA.

Diseño: `docs/robustness/caln/diseno-bloque4p.md`. Cada prueba cita su parte (C0 a C3) y la decisión de Gadea que cumple.
"""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


# ── C0: la vara, como producción ──────────────────────────────────────────────────────────────────────────────────────
# En producción, `finalize_chatwoot_delivery` (chatwoot.py) borra la nota y el motivo del pase al entregar cada turno. Los
# arneses que miden en PRE (`reproducir_juez_pre`, `charla_rama`) tienen que hacer lo mismo, o el pase se arrastra al turno
# siguiente (51 de 384 turnos del panel del bloque 1).

def _remoto(script: str) -> str:
    texto = (RAIZ / "scripts" / script).read_text(encoding="utf-8")
    return texto[texto.index("route_message"):]


def test_c0_reproducir_juez_pre_borra_el_pase_tras_cada_turno():
    remoto = _remoto("reproducir_juez_pre.py")
    assert "st.pending_escalation_reason = None" in remoto
    assert "st.pending_note = None" in remoto
    # se apunta en la fila ANTES de borrarlo (el campo del estado sigue diciendo si el turno pasó a una persona)
    assert remoto.index('"estado": estado') < remoto.index("st.pending_escalation_reason = None")


def test_c0_charla_rama_borra_el_pase_antes_de_guardar_el_estado():
    remoto = _remoto("charla_rama.py")
    assert remoto.index("st.pending_escalation_reason = None") < remoto.index("serialize_state(st)")
    assert remoto.index("st.pending_note = None") < remoto.index("serialize_state(st)")
    assert 'estado["pending_escalation_reason"]' in remoto
