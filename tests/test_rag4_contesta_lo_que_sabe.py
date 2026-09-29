"""rag-4: contestar la parte que SÍ está en el contexto antes de decir que falta el resto.

La regla del "no lo tengo" era todo-o-nada: decía "si la respuesta no está en el contexto, dilo" y
no decía nada de contestar lo que sí hay. Medido en `rag_piezas` (`2026-09-28-rag2-B2`): de los
fallos que quedan tras rag-2, 9 son de redacción y **todos con el dato ya en el contexto**. En
`salida-confirmada` el bot suelta la plantilla literal de esa regla ("ese detalle puntual no lo
tengo a la mano") teniendo delante "se opera todos los días salvo 25-dic y 1-ene" y "una salida
solo se suspende por mal tiempo".

El test que de verdad importa aquí es el de las ANCLAS: si alguien reescribe la viñeta original en
`RAG_BODY_*` y no toca la constante, el `replace` deja de encajar y el flag se convierte en un
no-op silencioso — encendido en PRE y sin efecto. Eso no lo caza ningún test de conducta.
"""

import pytest

from src.agents.rag_agent import build_system_prompt
from src.config import settings
from src.prompts.info import (
    RAG_BODY_EN,
    RAG_BODY_ES,
    RAG_NO_TENGO_OLD_EN,
    RAG_NO_TENGO_OLD_ES,
    RAG_NO_TENGO_V2_EN,
    RAG_NO_TENGO_V2_ES,
)


@pytest.mark.parametrize(
    ("vieja", "cuerpo", "idioma"),
    [(RAG_NO_TENGO_OLD_ES, RAG_BODY_ES, "es"), (RAG_NO_TENGO_OLD_EN, RAG_BODY_EN, "en")],
)
def test_el_ancla_sigue_encajando_en_el_prompt(vieja, cuerpo, idioma):
    """Si esto falla, el flag NO hace nada aunque esté encendido."""
    assert vieja in cuerpo, f"la viñeta original ya no está literal en RAG_BODY_{idioma.upper()}"
    assert cuerpo.count(vieja) == 1, "aparece más de una vez: el replace tocaría de más"


@pytest.mark.parametrize("idioma", ["es", "en"])
def test_con_el_flag_la_regla_nueva_sustituye_a_la_vieja(monkeypatch, idioma):
    monkeypatch.setattr(settings, "rag_contesta_lo_que_sabe", True)
    p = build_system_prompt(idioma)
    vieja = RAG_NO_TENGO_OLD_ES if idioma == "es" else RAG_NO_TENGO_OLD_EN
    nueva = RAG_NO_TENGO_V2_ES if idioma == "es" else RAG_NO_TENGO_V2_EN
    assert nueva in p
    assert vieja not in p, "la vieja tiene que desaparecer, no quedar las dos"


@pytest.mark.parametrize("idioma", ["es", "en"])
def test_apagado_el_prompt_es_exactamente_el_de_hoy(monkeypatch, idioma):
    """Control deliberado: sin esto, el test de arriba pasaría aunque el flag estuviera siempre on."""
    monkeypatch.setattr(settings, "rag_contesta_lo_que_sabe", False)
    p = build_system_prompt(idioma)
    vieja = RAG_NO_TENGO_OLD_ES if idioma == "es" else RAG_NO_TENGO_OLD_EN
    nueva = RAG_NO_TENGO_V2_ES if idioma == "es" else RAG_NO_TENGO_V2_EN
    assert vieja in p
    assert nueva not in p


def test_la_regla_nueva_conserva_la_salida_de_emergencia(monkeypatch):
    """No es "di siempre algo": si NO hay nada en el contexto, sigue estando permitido decirlo. Sin
    esta mitad, el cambio empujaría al modelo a inventar — justo lo contrario de lo que se busca."""
    monkeypatch.setattr(settings, "rag_contesta_lo_que_sabe", True)
    assert "no hay NADA en el contexto" in build_system_prompt("es")
    assert "really NOTHING in the context" in build_system_prompt("en")
