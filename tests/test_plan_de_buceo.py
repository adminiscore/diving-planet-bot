"""CALN-43: la tabla del plan, sin IA y sin ruido. Cada fila es una decisión de Gadea (`docs/robustness/caln/tablas-decisiones.md`)."""
import pytest

from src.flows.plan_de_buceo import Plan, plan_de_buceo

SALIDA = Plan(2)


@pytest.mark.parametrize(("pide", "plan"), [
    # Sin decir nada, la salida de siempre
    ({}, SALIDA),
    ({"origen": "cartagena"}, SALIDA),
    ({"dias": 1}, SALIDA),
    ({"dias": 6}, SALIDA),  # no hay paquete de 6 días
    # La cifra que elige el cliente manda sobre todo lo demás
    ({"inmersiones": 2}, SALIDA),
    ({"inmersiones": 3, "dias": 1}, Plan(3)),
    ({"inmersiones": 5, "dias": 2}, Plan(5)),
    ({"inmersiones": 5, "dias": 2, "sin_nocturna": True}, Plan(5)),
    ({"inmersiones": 7, "salidas_sueltas": 2}, Plan(7)),
    # P1: 2 días sin hablar de la nocturna: el de 4
    ({"dias": 2}, Plan(4)),
    ({"dias": 2, "origen": "cartagena"}, Plan(4)),
    ({"dias": 2, "origen": "island"}, Plan(4)),
    # P2 y P3: solo mañanas o sin nocturna, según dónde duerma
    ({"dias": 2, "sin_nocturna": True, "origen": "cartagena"}, Plan(2, veces=2)),
    ({"dias": 2, "sin_nocturna": True, "origen": "island"}, Plan(4)),  # P4
    ({"dias": 2, "sin_nocturna": True}, Plan(4)),  # sin saber dónde duerme, el de 4
    # P3: pide salidas sueltas
    ({"salidas_sueltas": 2}, Plan(2, veces=2)),
    ({"salidas_sueltas": 3, "origen": "island"}, Plan(2, veces=3)),
    ({"salidas_sueltas": 2, "inmersiones": 2}, Plan(2, veces=2)),  # «dos salidas de 2 inmersiones»
    ({"salidas_sueltas": 2, "dias": 2, "sin_nocturna": True}, Plan(2, veces=2)),
    # 3 y 4 días: hay un solo paquete
    ({"dias": 3}, Plan(7)),
    ({"dias": 4}, Plan(9)),
    # P5: sin nocturna, el mismo paquete, y un asesor cierra el precio
    ({"dias": 3, "sin_nocturna": True}, Plan(7, asesor_cierra_el_precio=True)),
    ({"dias": 4, "sin_nocturna": True, "origen": "island"}, Plan(9, asesor_cierra_el_precio=True)),
    # P6: el refresher ocupa uno de los días, si va una persona
    ({"dias": 2, "refresher_solo": True}, SALIDA),
    ({"dias": 3, "refresher_solo": True}, Plan(4)),
    ({"dias": 4, "refresher_solo": True}, Plan(7)),
    ({"dias": 3, "refresher_solo": True, "sin_nocturna": True, "origen": "cartagena"}, Plan(2, veces=2)),
    ({"inmersiones": 5, "dias": 2, "refresher_solo": True}, Plan(5)),  # si eligió el paquete, lo decide él
])
def test_la_tabla_del_plan(pide, plan):
    assert plan_de_buceo(**pide) == plan


def _estado(**campos):
    from src.flows.state import ConversationState

    st = ConversationState(conversation_id="c43", language="es", detected_activity="certified_diving", is_certified=True, detected_group_size=1,
                           is_colombian=False, **campos)
    return st


def _tarjeta(st):
    from src.agents import conversational_core as core
    from src.flows import cart_render

    st.mixed_cart = [core._cart_item(st, "certified_diving", st.detected_group_size)]
    return "\n".join(cart_render._format_activity_booking_messages(st))


def test_tres_dias_sin_nocturna_el_asesor_cierra_el_precio():
    tarjeta = _tarjeta(_estado(location="cartagena", detected_cert_days=3, sin_nocturna=True))
    assert "Paquete de 7" in tarjeta and "el precio te lo cierra un asesor" in tarjeta
    assert "USD" not in tarjeta and "book.divingplanet.org" not in tarjeta


def test_dos_mananas_desde_cartagena_son_dos_salidas_una_reserva_por_dia():
    tarjeta = _tarjeta(_estado(location="cartagena", detected_cert_days=2, sin_nocturna=True))
    assert "2 inmersiones" in tarjeta and "se reserva una por día" in tarjeta and "book.divingplanet.org" in tarjeta


def test_dos_dias_desde_las_islas_sin_nocturna_el_de_cuatro_con_asesor():
    tarjeta = _tarjeta(_estado(location="island", hotel="cocoliso", detected_cert_days=2, sin_nocturna=True))
    assert "Paquete de 4" in tarjeta and "book.divingplanet.org" not in tarjeta and "asesor" in tarjeta


def test_sin_nocturna_viene_de_jev():
    from src.agents.intent_detector import DetectedIntent
    from src.agents.jev_router import SIN_NOCTURNA
    from src.agents.rutas.booking import _poner_el_plan_dicho

    st = _estado()
    st._senales_router = {SIN_NOCTURNA: True}
    _poner_el_plan_dicho(st, DetectedIntent())
    assert st.sin_nocturna is True
