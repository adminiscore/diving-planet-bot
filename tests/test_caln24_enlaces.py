"""CALN-24 (4-nov): el escritor y la tarjeta con enlaces de planes distintos: no sale la tarjeta y se pregunta cuál quiere."""
from src.agents.nucleo.slotfill_close import _si_chocan_los_enlaces

DOS = "https://book.divingplanet.org/book/salidas-de-buceo/1?language=es"
SIETE = "https://book.divingplanet.org/book/3-days-7-dives/10?language=es"
TARJETA = f"🤿 *Salidas de Buceo - 2 inmersiones (1 día)*\n💰 *178 USD* por persona\n\n👉 *Haz clic aquí:*\n{DOS}"


def test_lima_el_escritor_da_el_de_7_y_la_tarjeta_el_de_2():
    escritor = (f"Para reservar los cinco, entren al link del paquete. Les dejo el del plan de 3 días:\n\n"
                f"👉 Paquete de 7 inmersiones (3 días): {SIETE}\n\n"
                "Pídanle al equipo el descuento de grupo antes de pagar.")
    texto = _si_chocan_los_enlaces(escritor, TARJETA, "es")
    assert texto.endswith("? 🌊") and "7 inmersiones" in texto and "2 inmersiones" in texto
    assert "book.divingplanet.org" not in texto
    assert "descuento de grupo" in texto  # lo demás que dijo se queda
    assert "Les dejo el del plan de 3 días:" not in texto  # lo que anunciaba el enlace se va con él


def test_el_mismo_enlace_no_choca():
    assert _si_chocan_los_enlaces(f"Puedes reservar aquí: {DOS}", TARJETA, "es") is None


def test_el_mismo_enlace_en_otro_idioma_no_choca():
    assert _si_chocan_los_enlaces(f"Book here: {DOS.replace('language=es', 'language=en')}", TARJETA, "en") is None


def test_sin_enlace_del_escritor_no_choca():
    assert _si_chocan_los_enlaces("La salida es a las 8.", TARJETA, "es") is None


def test_la_tarjeta_en_pesos_no_lleva_enlaces_y_no_se_compara():
    assert _si_chocan_los_enlaces(f"Reserva aquí: {DOS}", "🤿 *Tour de Snorkeling*\n💰 *448.000 COP*", "es") is None


def test_un_enlace_que_no_es_del_catalogo_no_se_nombra():
    inventado = "https://book.divingplanet.org/book/no-existe/999"
    assert _si_chocan_los_enlaces(f"Reserva aquí: {inventado}", TARJETA, "es") is None


def test_el_refresher_lo_pone_el_codigo_dentro_del_cierre():
    refresher = "https://book.divingplanet.org/book/minicurso-de-buceo/2?language=es"
    cierre = f"✅ *Refresher añadido*. Resérvalo aquí: {refresher}\n\n{TARJETA}"
    assert _si_chocan_los_enlaces("Antes de bucear harás el refresher.", cierre, "es") is None
    assert _si_chocan_los_enlaces(f"El refresher se reserva aquí: {refresher}", cierre, "es") is None
