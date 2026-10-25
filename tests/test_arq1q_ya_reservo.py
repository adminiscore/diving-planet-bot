"""ARQ-1q (22-oct, flag `ya_reservo_no_es_pase`): decir que ya reservó no basta para pasar a una persona. Con la reserva
hecha, preguntar el horario, la recogida o qué llevar lo contesta Coral; ver o tocar esa reserva o pago sigue yendo a un
asesor. Aquí, sin red: la pregunta de Jev con el flag y sin él (la conducta, en docs/robustness/arq/banco-arq1q.json)."""
from src.agents import jev_router as j


def test_encendido_lleva_la_frase_al_final(monkeypatch):
    instrucciones = j._questions_for_turn()[j.NEEDS_STAFF]["instructions"]
    assert instrucciones.endswith(j._YA_RESERVO_NO_BASTA)
    assert j._FUERA_DEL_SISTEMA in instrucciones


def test_lo_que_sigue_siendo_de_una_persona_esta_en_la_frase():
    frase = j._YA_RESERVO_NO_BASTA
    for caso in ("change its date", "cancel it", "money back", "confirmation email", "received", "status"):
        assert caso in frase
