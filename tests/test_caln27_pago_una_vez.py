"""CALN-27 (un dato, un solo dueño): si el escritor ya dijo la moneda con sus palabras, el aviso del pago no la repite."""
from src.flows import avisos
from src.flows.state import ConversationState


def _extranjero(**campos):
    st = ConversationState(conversation_id="caln27", language=campos.pop("language", "es"), is_colombian=False)
    st._intenciones = ["pago"]
    for k, v in campos.items():
        setattr(st, k, v)
    return st


AVISO_ES = "Quien no es colombiano ni residente"
AVISO_EN = "Guests who are not Colombian"


def test_si_el_escritor_ya_dice_usd_no_se_repite():
    st = _extranjero()
    texto = "Como eres chileno, pagas en USD. Reserva cuando quieras."
    assert avisos.poner_avisos(st, texto) == texto
    assert "extranjero-paga-en-usd" in st.avisos_dados  # dado: no sale después


def test_en_ingles_y_con_tilde_tambien():
    assert AVISO_EN not in avisos.poner_avisos(_extranjero(language="en"), "As Australian citizens, you'll pay in USD.")
    assert AVISO_ES not in avisos.poner_avisos(_extranjero(), "Se paga en dólares estadounidenses.")


def test_si_no_lo_dice_sale_el_aviso():
    assert AVISO_ES in avisos.poner_avisos(_extranjero(), "La salida es a las 8:00 desde el muelle.")


def test_un_precio_en_usd_de_la_tarjeta_no_cuenta_como_decirlo():
    assert AVISO_ES in avisos.poner_avisos(_extranjero(), "🤿 *Salidas de Buceo*\n💰 *178 USD* por persona")
