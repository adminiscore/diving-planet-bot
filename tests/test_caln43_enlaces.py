"""CALN-43: con tarjeta, los enlaces de reserva los pone ella; sustituye al árbitro de CALN-24. Sin IA."""
from src.agents.compositor import _sin_enlaces_repetidos

DOS = "https://book.divingplanet.org/book/salidas-de-buceo/1?language=es"
SIETE = "https://book.divingplanet.org/book/paquete-de-7-inmersiones/8?language=es"
REFRESHER = "https://book.divingplanet.org/book/minicurso-de-buceo/2?language=es"
TARJETA = f"🤿 *Salidas de Buceo*\n💰 *178 USD* por persona\n\n👉 *Para reservar, haz clic aquí:*\n{DOS}"


def test_lima_el_enlace_de_otro_plan_no_sale_con_la_tarjeta():
    limpia = _sin_enlaces_repetidos(f"Te recomiendo el paquete. Reserva aquí: {SIETE}\n\n{TARJETA}")
    assert SIETE not in limpia and DOS in limpia and "Te recomiendo el paquete." in limpia


def test_el_mismo_enlace_tampoco():
    assert _sin_enlaces_repetidos(f"Reserva aquí: {DOS}\n\n{TARJETA}").count(DOS) == 1


def test_el_refresher_lo_pone_el_codigo_y_se_queda():
    nota = f"✅ *Refresher añadido*: resérvalo aquí: {REFRESHER}"
    assert REFRESHER in _sin_enlaces_repetidos(f"{nota}\n\n{TARJETA}")


def test_sin_tarjeta_no_se_toca():
    respuesta = f"Reserva aquí: {SIETE}"
    assert _sin_enlaces_repetidos(respuesta) == respuesta


def test_la_tarjeta_sin_enlace_no_quita_el_del_escritor():
    respuesta = f"El refresher se reserva aquí: {REFRESHER}\n\n🤿 *Paquete de 4*\n👉 Para reservar esto, dime y te paso con un asesor."
    assert _sin_enlaces_repetidos(respuesta) == respuesta
