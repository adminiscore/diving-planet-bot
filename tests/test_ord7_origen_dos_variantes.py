"""ord-7 (21-oct, decisión de Gadea con ord-0).

- `origen_dos_variantes`: sin saber el origen, la puerta del precio ya no deja al cliente sin nada: pone las dos
  variantes del catálogo (desde Cartagena y ya en las islas) y pregunta el origen para seguir.
- `tarjeta_edades_en_cifra`: la tarjeta «qué puede hacer cada quien» dice la edad mínima de cada opción y quién es
  cada línea en el idioma del cliente.
"""
import pytest

from src.agents import conversational_core as cc
from src.config import settings
from src.flows import eligibility
from src.flows.state import ConversationState

RAG_CARTAGENA = ("El minicurso cuesta 183 USD online desde Cartagena. Incluye lancha y almuerzo.\n\n"
                 "No necesitas experiencia previa ni ninguna certificación para hacerlo. ¿Quieres el enlace?")


@pytest.fixture
def variantes(monkeypatch):
    monkeypatch.setattr(settings, "origen_dos_variantes", True)


def _conv(lang="es", **campos) -> ConversationState:
    st = ConversationState(conversation_id="ord7", language=lang)
    for k, v in campos.items():
        setattr(st, k, v)
    return st


def test_las_dos_variantes_del_catalogo_en_usd():
    texto = cc._dos_variantes(_conv(actividad_preguntada="minicourse"))
    assert "183 USD" in texto and "134 USD" in texto
    assert "almuerzo incluido" in texto and "sin almuerzo" in texto


def test_a_un_colombiano_en_cop():
    texto = cc._dos_variantes(_conv(actividad_preguntada="snorkel", is_colombian=True))
    assert "COP" in texto and "USD" not in texto


def test_en_ingles():
    texto = cc._dos_variantes(_conv("en", actividad_preguntada="minicourse"))
    assert "From Cartagena" in texto and "lunch included" in texto and "no lunch" in texto


@pytest.mark.parametrize("campos", [{}, {"actividad_preguntada": "certified_diving"}])
def test_sin_una_actividad_con_un_plan_por_origen_no_hay_variantes(campos):
    """Sin actividad, o los paquetes de buceo (varios planes por origen): como antes."""
    assert cc._dos_variantes(_conv(**campos)) is None


def test_la_puerta_pone_las_variantes_y_pregunta_el_origen(variantes):
    st = _conv(actividad_preguntada="minicourse")
    texto = cc._origen_antes_del_precio(st, "¿cuánto cuesta el minicurso?", RAG_CARTAGENA)
    assert "183 USD" in texto and "134 USD" in texto
    assert texto.endswith(cc.ORIGEN_TRAS_LAS_VARIANTES_ES)
    assert "No necesitas experiencia previa ni ninguna certificación para hacerlo." in texto  # lo que no depende del origen se queda
    assert cc._es_pregunta_de_origen(texto)


def test_apagado_la_puerta_quita_el_precio_como_antes(monkeypatch):
    monkeypatch.setattr(settings, "origen_dos_variantes", False)
    texto = cc._origen_antes_del_precio(_conv(actividad_preguntada="minicourse"), "¿cuánto cuesta el minicurso?",
                                        RAG_CARTAGENA)
    assert "USD" not in texto and texto.endswith(cc.ORIGEN_ANTES_DEL_PRECIO_ES)


def test_sin_actividad_la_puerta_sigue_como_antes(variantes):
    texto = cc._origen_antes_del_precio(_conv(), "¿cuánto cuesta?", RAG_CARTAGENA)
    assert "USD" not in texto and texto.endswith(cc.ORIGEN_ANTES_DEL_PRECIO_ES)


def test_con_origen_no_hay_puerta(variantes):
    assert cc._origen_antes_del_precio(_conv(actividad_preguntada="minicourse", location="cartagena"),
                                       "¿cuánto cuesta el minicurso?", RAG_CARTAGENA) is None


@pytest.mark.parametrize("flag, esperado_es, esperado_en", [
    (True, "minicurso de buceo (desde 10 años)", "*13 years old* → can choose: dive mini-course (from age 10)"),
    (False, "minicurso de buceo /", "*13 años*"),
])
def test_tarjeta_de_edades(monkeypatch, flag, esperado_es, esperado_en):
    monkeypatch.setattr(settings, "tarjeta_edades_en_cifra", flag)
    plans = eligibility.plan_group(certified=0, noncert_ages=[8, 13])
    assert esperado_es in eligibility.format_group_plan(plans, "es")
    assert esperado_en in eligibility.format_group_plan(plans, "en")


def test_tarjeta_bubble_makers_ya_dice_su_franja(monkeypatch):
    monkeypatch.setattr(settings, "tarjeta_edades_en_cifra", True)
    texto = eligibility.format_group_plan(eligibility.plan_group(certified=0, noncert_ages=[8]), "es")
    assert "Bubble Makers (buceo para niños 8-10) /" in texto and "snorkel (desde 6 años)" in texto


def test_si_el_rag_cotizo_otra_actividad_no_hay_variantes(variantes):
    """Banco ord-7: «tengo el Open Water, ¿cuánto cuesta el repaso?» anotaba el Open Water y salían sus precios."""
    st = _conv(actividad_preguntada="padi_open_water")
    texto = cc._origen_antes_del_precio(st, "¿cuánto cuesta el repaso?", "El repaso cuesta 183 USD online.")
    assert "693" not in texto and texto.endswith(cc.ORIGEN_ANTES_DEL_PRECIO_ES)


@pytest.mark.parametrize("respuesta", ["Cuesta **$134 USD** ya en las islas.", "Son 655.000 COP online.",
                                       "Precio normal: 204 USD."])
def test_cualquier_precio_de_la_actividad_vale(respuesta):
    assert cc._dos_variantes(_conv(actividad_preguntada="minicourse"), respuesta)


def test_jev_pide_precio_nombra_las_actividades(monkeypatch):
    """ord-7: «¿Cuánto cuesta el snorkel?» salía 0,55 con la pregunta de Jev sin las actividades."""
    from src.agents import jev_router

    monkeypatch.setattr(settings, "jev_precio_nombra_actividades", True)
    assert "snorkeling" in jev_router._questions_for_turn()[jev_router.PIDE_PRECIO]["instructions"]
    monkeypatch.setattr(settings, "jev_precio_nombra_actividades", False)
    assert jev_router._questions_for_turn()[jev_router.PIDE_PRECIO] is jev_router._PIDE_PRECIO_Q


def test_sin_origen_un_enlace_da_los_dos(variantes):
    """«Mándame el enlace del Open Water» sin origen daba el de Cartagena: ahora las dos variantes con su enlace."""
    respuesta = ("Claro, aquí tienes el enlace del Open Water: "
                 "https://book.divingplanet.org/book/basic-course/4?language=es")
    texto = cc._origen_antes_del_precio(_conv(actividad_preguntada="padi_open_water"),
                                        "mándame el enlace del open water", respuesta)
    assert "basic-course/4" in texto and "basic-course-already-on-the-island" in texto
    assert texto.endswith(cc.ORIGEN_TRAS_LOS_ENLACES_ES) and cc._es_pregunta_de_origen(texto)


def test_sin_origen_un_enlace_apagado_no_cambia(monkeypatch):
    monkeypatch.setattr(settings, "origen_dos_variantes", False)
    respuesta = "Aquí tienes: https://book.divingplanet.org/book/basic-course/4?language=es"
    assert cc._origen_antes_del_precio(_conv(actividad_preguntada="padi_open_water"),
                                       "mándame el enlace del open water", respuesta) is None
