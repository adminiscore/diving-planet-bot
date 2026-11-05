"""5-nov (Gadea #3570; panel visto-6940, tanda s05f 6952): el escritor ofrece pasar con un asesor y el cliente acepta añadiendo algo
(«Yes, please. Thank you for your help.»). El «sí» solo valía si el mensaje era SOLO la afirmación: el núcleo seguía con la
reserva y volvía a ofrecerlo. Ahora lo reconoce también Jev (`acepta_el_pase`) y el núcleo se aparta para que la cascada haga
el pase; la oferta del cierre en pesos la sigue el cierre."""
import asyncio

from src.agents import supervisor
from src.agents.jev_router import _TURN_SIGNALS, ACEPTA_EL_PASE, answers_to_signals
from src.agents.nucleo import setup as nucleo_setup
from src.agents.nucleo.slotfill_close import _OFERTA_DEL_ASESOR, _quiere_reservar_o_pagar
from src.flows.state import ConversationState, Step

OFERTA_DEL_ESCRITOR = ("A different return date needs to be arranged with a team advisor, who can also confirm whether your "
                       "large suitcase can be accommodated. Would you like me to connect you with one?")


def _estado(ultimo_del_bot: str, step: Step = Step.FREE_TEXT) -> ConversationState:
    st = ConversationState(conversation_id="acepta-pase", language="en")
    st.step = step
    st.history = [{"role": "user", "content": "How can I book?"}, {"role": "assistant", "content": ultimo_del_bot}]
    return st


def test_la_senal_esta_en_la_tabla_y_viaja_con_el_turno():
    assert ACEPTA_EL_PASE in _TURN_SIGNALS
    assert answers_to_signals({ACEPTA_EL_PASE: {"type": "noul", "noul": 0.97}})[ACEPTA_EL_PASE] is True
    assert answers_to_signals({ACEPTA_EL_PASE: {"type": "noul", "noul": 0.47}})[ACEPTA_EL_PASE] is False


def test_un_si_con_algo_mas_acepta_si_lo_dice_jev():
    st = _estado(OFERTA_DEL_ESCRITOR)
    assert supervisor.acepta_la_oferta_del_asesor(st, "Yes, please. Thank you for your help.", {ACEPTA_EL_PASE: True})
    assert not supervisor.acepta_la_oferta_del_asesor(st, "Yes, please. Thank you for your help.", {ACEPTA_EL_PASE: False})


def test_el_si_pelado_acepta_como_siempre():
    # Sin Jev, como hasta hoy: solo el «sí» pelado («yes please» ya no lo es para `_BARE_AFFIRMATION_RE`).
    assert supervisor.acepta_la_oferta_del_asesor(_estado(OFERTA_DEL_ESCRITOR), "yes", {})
    assert not supervisor.acepta_la_oferta_del_asesor(_estado(OFERTA_DEL_ESCRITOR), "yes please", {})


def test_sin_oferta_en_el_ultimo_mensaje_no_hay_pase():
    st = _estado("Perfect! How many people would this be for: just you, or more?")
    assert not supervisor.acepta_la_oferta_del_asesor(st, "Yes, please.", {ACEPTA_EL_PASE: True})


def test_fuera_de_la_conversacion_libre_no_se_mira():
    st = _estado(OFERTA_DEL_ESCRITOR, step=Step.WELCOME)
    assert not supervisor.acepta_la_oferta_del_asesor(st, "yes", {ACEPTA_EL_PASE: True})


def test_el_nucleo_se_aparta_y_la_cascada_hace_el_pase():
    st = _estado(OFERTA_DEL_ESCRITOR)
    senales = {ACEPTA_EL_PASE: True}
    assert asyncio.run(nucleo_setup._setup_phase(st, "Yes, please. Thank you for your help.", senales)) is None
    assert supervisor.pase_pedido_o_aceptado(st, "Yes, please. Thank you for your help.", senales)
    assert st.step == Step.ESCALATE and st.pending_escalation_reason == "aceptó la oferta del bot de hablar con un asesor"


def test_la_oferta_del_cierre_en_pesos_la_sigue_el_cierre():
    st = _estado(f"Te dejo los precios.\n\n{_OFERTA_DEL_ASESOR['es_uno']}")
    st.language = "es"
    assert nucleo_setup._es_la_oferta_del_cierre(st)
    st._senales_router = {ACEPTA_EL_PASE: True}
    assert _quiere_reservar_o_pagar(st, "Sí, por favor. ¿Y el anticipo es del 50 %?")
