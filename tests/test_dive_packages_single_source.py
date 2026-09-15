"""Paquetes de buceo con una sola fuente (2026-09-15).

Los tamanos estaban copiados en el detector, el nucleo y el RAG, y el RAG leia
"paquete de 4 dias" como el de 4 inmersiones. Ahora salen de los ids
`N_dives_D_days` de services.json (`dom.dive_packages`) y "N inmersiones" se lee con
`dive_counts_in`, compartida por los tres.
"""

import pytest

from src.agents import conversational_core as core
from src.agents import rag_agent
from src.agents.intent_detector import detect_cert_day_count, detect_cert_dive_count, dive_counts_in
from src.domain import activities as dom
from src.flows.state import ConversationState


def test_packages_come_from_the_catalog():
    assert dom.dive_packages() == {
        2: (1, "2_dives_1_day"), 3: (1, "3_dives_1_day"), 4: (2, "4_dives_2_days"),
        5: (2, "5_dives_2_days"), 7: (3, "7_dives_3_days"), 9: (4, "9_dives_4_days"),
    }
    # El nucleo conserva sus tablas de antes, ahora derivadas.
    assert core._DIVES_TO_BASE_PLAN == {n: sid for n, (_, sid) in dom.dive_packages().items()}
    assert core._DAYS_TO_DIVES == {2: 5, 3: 7, 4: 9}


@pytest.mark.parametrize("text, counts", [
    ("quiero 2 inmersiones", [2]),
    ("cinco inmersiones", [5]),
    ("4 o 5 inmersiones", [4, 5]),
    ("el pack de 9", [9]),
    ("el pack de 3", []),          # 3 tambien puede ser dias: no se adivina
    ("paquete de siete", [7]),     # tamano sin unidad, desde el catalogo (sin 5|7|9 en el regex)
    ("pack de 6", []),             # no existe ese paquete en el catalogo
    ("package of nine", [9]),
    ("10 inmersiones", []),        # no existe ese paquete
])
def test_dive_counts_in(text, counts):
    assert dive_counts_in(text) == counts


def test_two_packages_named_is_not_a_choice():
    assert detect_cert_dive_count("no se si 4 o 5 inmersiones") is None
    assert detect_cert_day_count("paquete de 5 dias") is None   # no hay paquete de 5 dias


@pytest.mark.parametrize("query, service", [
    ("cuánto cuesta el paquete de 4 días?", "9_dives_4_days"),       # antes: el de 4 inmersiones
    ("cuánto cuesta el paquete de 3 días?", "7_dives_3_days"),
    ("how much is a 4-day dive package?", "9_dives_4_days"),
    ("cuánto cuesta el paquete de cinco inmersiones?", "5_dives_2_days"),
    ("precio de 9 buceos en 4 días", "9_dives_4_days"),
    ("cuánto cuesta el paquete de 4 inmersiones en 2 días?", "4_dives_2_days"),
    ("cuánto cuesta el paquete de 2 días?", None),                   # 4 o 5 inmersiones
    ("cuánto cuesta el plan de 5 días?", None),                      # antes: el de 5 inmersiones
    ("cuánto cuesta el paquete de 4 o 5 inmersiones?", None),
    ("cuánto cuestan 2 inmersiones?", None),                         # de un dia: otro handler
])
def test_price_package_service(query, service):
    assert rag_agent._price_package_service(query) == service


@pytest.mark.parametrize("bot_message, dives", [
    ("Paquete de 5 inmersiones en 2 días (incluye buceo nocturno)", 5),
    ("La salida de 2 inmersiones cuesta 183 USD y el paquete de 5 inmersiones 392 USD", 5),
    ("Tenemos el paquete de 4 inmersiones en 2 días y el de 5 inmersiones en 2 días", None),
    ("Te propongo el plan de cinco inmersiones en dos días", 5),
])
def test_confirmed_package_reads_one_multi_day_package(bot_message, dives):
    state = ConversationState(conversation_id="c")
    state.history = [{"role": "assistant", "content": bot_message}]
    core._maybe_apply_confirmed_package(state, "vale, quiero este paquete")
    assert state.detected_cert_dives == dives
