"""CALN-27 (un dato, un solo dueño): el enlace de reserva lo pone la tarjeta; si el escritor da el mismo, sobra el suyo."""
from src.agents.compositor import _sin_enlaces_repetidos

DOS = "https://book.divingplanet.org/book/salidas-de-buceo/1"
CINCO = "https://book.divingplanet.org/book/2-days-5-dives/9?language=en"
TARJETA = (f"🤿 *5 Dives - 2 days*\n💰 *392 USD* per person\n\n👉 *For more information and to book, click here:*\n{CINCO}")


def test_el_del_escritor_se_va_y_la_tarjeta_se_queda():
    texto = _sin_enlaces_repetidos(f"Absolutely! Here's the link for the package: {CINCO}\n\nYou'll book the hotel apart.\n\n{TARJETA}")
    assert texto.count("2-days-5-dives/9") == 1
    assert "Absolutely!" in texto and "You'll book the hotel apart." in texto
    assert "Here's the link" not in texto  # lo que lo anunciaba se va con él
    assert texto.endswith(TARJETA)


def test_una_frase_con_el_enlace_en_medio_de_un_parrafo():
    texto = _sin_enlaces_repetidos(f"El plan dura 2 días. Reserva aquí: {CINCO} Lleva tu carné.\n\n{TARJETA}")
    assert "El plan dura 2 días." in texto and "Lleva tu carné." in texto and texto.count(CINCO) == 1


def test_el_parrafo_que_solo_era_el_enlace_se_va_entero():
    texto = _sin_enlaces_repetidos(f"Todo claro.\n\nReserva aquí:\n{CINCO}\n\n{TARJETA}")
    assert texto == f"Todo claro.\n\n{TARJETA}"


def test_con_el_idioma_y_con_signos_no_quedan_restos():
    for texto in (f"Reserva aquí: {CINCO}.", f"[Reservar]({CINCO})", f"Reserva: {CINCO} ."):
        assert _sin_enlaces_repetidos(f"{texto}\n\n{TARJETA}") == TARJETA


def test_lo_que_sigue_al_enlace_se_queda_sin_restos():
    salida = _sin_enlaces_repetidos(f"Book here: {CINCO} and bring your card.\n\n{TARJETA}")
    assert salida == f"and bring your card.\n\n{TARJETA}"


def test_el_mismo_plan_en_otro_idioma_tambien_es_el_mismo_enlace():
    otra = CINCO.replace("language=en", "language=es")
    assert _sin_enlaces_repetidos(f"Reserva aquí: {otra}\n\n{TARJETA}") == TARJETA


def test_con_tarjeta_el_enlace_de_otro_plan_se_va():
    """CALN-43: el plan lo decide la tabla y el enlace lo pone la tarjeta (antes arbitraba CALN-24)."""
    assert _sin_enlaces_repetidos(f"Si prefieres un día: {DOS}\n\n{TARJETA}") == TARJETA


def test_sin_tarjeta_no_se_toca():
    entrada = f"Reserva aquí: {CINCO}. O aquí: {CINCO}"
    assert _sin_enlaces_repetidos(entrada) == entrada


def test_dos_tarjetas_con_el_mismo_enlace_siguen_las_dos():
    otra = f"🤿 *Bubble Makers*\n👉 *Click here:*\n{CINCO}"
    entrada = f"Te cuento.\n\n{TARJETA}\n---\n{otra}"
    assert _sin_enlaces_repetidos(entrada).count(CINCO) == 2


def test_si_el_escritor_solo_daba_el_enlace_queda_la_tarjeta():
    assert _sin_enlaces_repetidos(f"Reserva aquí: {CINCO}\n\n{TARJETA}") == TARJETA
