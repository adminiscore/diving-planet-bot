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


# ── C1: la agencia, como un cliente (decisión «por-otros», 9-nov) ───────────────────────────────────────────────────

def test_c1_needs_staff_ya_no_pasa_a_la_agencia():
    from src.agents import jev_router as jr

    q = jr._questions_for_turn()[jr.NEEDS_STAFF]["instructions"]
    assert "ALSO FALSE when a travel agency" in q
    assert "for an agency" not in q and "special rates" not in q
    assert "writing as a business" not in q
    # sigue en el pase lo que solo hace una persona: la factura, el enlace especial y lo de una reserva ya hecha
    for palabra in ("invoice", "'special' payment link", "ALREADY made"):
        assert palabra in q


def test_c1_el_escritor_recibe_por_otros_en_los_dos_idiomas():
    from src.domain.decisiones import instruccion
    from src.prompts.info import reglas_del_escritor

    for lang in ("es", "en"):
        assert instruccion("por-otros", lang) in reglas_del_escritor(lang)
    assert "comisión" in instruccion("por-otros", "es") and "commission" in instruccion("por-otros", "en")


def test_c1_el_juez_no_ve_la_instruccion_y_su_huella_no_cambia():
    from scripts.judge_golden_set import decisiones_del_negocio
    from src.domain.decisiones import instruccion

    juez = decisiones_del_negocio()
    assert "«por-otros»" in juez
    assert instruccion("por-otros", "es") not in juez
