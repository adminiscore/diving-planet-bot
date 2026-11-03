"""Sparring s03j (3-nov, la 7.ª tanda, de Álvaro, contra PRE 0.45): «4 inmersiones en 2 días desde Cartagena» recibía
el enlace del paquete de 5. El de 4 no tiene enlace de reserva y no estaba en la lista del escritor, que tomaba el del
plan vecino. La lista nombra también los planes sin enlace, que reserva un asesor. Sin red."""
from src.flows.catalog import SERVICES, catalog_booking_links


def test_los_planes_sin_enlace_salen_en_la_lista_como_del_asesor():
    for lang, cabeza in (("es", "SIN LINK DE RESERVA"), ("en", "NO BOOKING LINK")):
        lista = catalog_booking_links(lang)
        con_enlace, sin_enlace = lista.split(cabeza)
        nombre = SERVICES["4_dives_2_days"]["name_es" if lang == "es" else "name_en"]
        assert f"- {nombre}\n" in sin_enlace + "\n" and f"- {nombre}:" not in con_enlace
        assert "2-days-5-dives" in con_enlace and "book.divingplanet.org" not in sin_enlace
