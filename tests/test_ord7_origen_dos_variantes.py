"""ord-7 (21-oct, decisión de Gadea con ord-0).

- `origen_dos_variantes`: sin saber el origen, la puerta del precio ya no deja al cliente sin nada: pone las dos
  variantes del catálogo (desde Cartagena y ya en las islas) y pregunta el origen para seguir.
- `tarjeta_edades_en_cifra`: la tarjeta «qué puede hacer cada quien» dice la edad mínima de cada opción y quién es
  cada línea en el idioma del cliente.
"""
import pytest

from src.agents import conversational_core as cc
from src.flows.state import ConversationState

RAG_CARTAGENA = ("El minicurso cuesta 183 USD online desde Cartagena. Incluye lancha y almuerzo.\n\n"
                 "No necesitas experiencia previa ni ninguna certificación para hacerlo. ¿Quieres el enlace?")


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


def test_la_puerta_pone_las_variantes_y_pregunta_el_origen():
    st = _conv(actividad_preguntada="minicourse")
    texto = cc._origen_antes_del_precio(st, "¿cuánto cuesta el minicurso?", RAG_CARTAGENA)
    assert "183 USD" in texto and "134 USD" in texto
    assert texto.endswith(cc.ORIGEN_TRAS_LAS_VARIANTES_ES)
    assert "No necesitas experiencia previa ni ninguna certificación para hacerlo." in texto  # lo que no depende del origen se queda
    assert cc._es_pregunta_de_origen(texto)


def test_sin_actividad_la_puerta_sigue_como_antes():
    texto = cc._origen_antes_del_precio(_conv(), "¿cuánto cuesta?", RAG_CARTAGENA)
    assert "USD" not in texto and texto.endswith(cc.ORIGEN_ANTES_DEL_PRECIO_ES)


def test_con_origen_no_hay_puerta():
    assert cc._origen_antes_del_precio(_conv(actividad_preguntada="minicourse", location="cartagena"),
                                       "¿cuánto cuesta el minicurso?", RAG_CARTAGENA) is None


def test_si_el_rag_cotizo_otra_actividad_no_hay_variantes():
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

    assert "snorkeling" in jev_router._questions_for_turn()[jev_router.PIDE_PRECIO]["instructions"]


def test_sin_origen_un_enlace_da_los_dos():
    """«Mándame el enlace del Open Water» sin origen daba el de Cartagena: ahora las dos variantes con su enlace."""
    respuesta = ("Claro, aquí tienes el enlace del Open Water: "
                 "https://book.divingplanet.org/book/basic-course/4?language=es")
    texto = cc._origen_antes_del_precio(_conv(actividad_preguntada="padi_open_water"),
                                        "mándame el enlace del open water", respuesta)
    assert "basic-course/4" in texto and "basic-course-already-on-the-island" in texto
    assert texto.endswith(cc.ORIGEN_TRAS_LOS_ENLACES_ES) and cc._es_pregunta_de_origen(texto)
