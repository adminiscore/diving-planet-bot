"""ARQ-8d/8e/8f (23-oct, reparto de Gadea #1617; causas del G10 nº 6, sin frases del examen). Sin red.

- 8d `incluye_lo_que_se_hace`: con «¿qué incluye?» va lo que se hace (el itinerario de la ficha) y, en las islas, la
  frase de `island_pickup` de lo que no incluyen, no el párrafo entero.
- 8e `recogida_se_coordina`: la recogida de las islas dice cómo se coordina (el muelle o punto más cercano).
- 8f `precio_pendiente_con_el_origen`: el precio que esperaba el origen entra en las intenciones del turno.
- 8f `listas_una_vez`: lo que se repite igual en varias actividades se pinta una vez, sin rótulos dobles ni sueltos."""
import pytest

from src.agents import redactor_hechos as rh
from src.flows import hechos
from src.flows.state import ConversationState


def _estado(origen=None, lang="es"):
    st = ConversationState(conversation_id="arq8", language=lang)
    st.location = origen
    return st


# --- 8d -------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", ["es", "en"])
def test_las_tres_partes_de_la_recogida_son_politicas(lang):
    """lat-deuda-u (26-oct): ya no se corta `island_pickup` por frases; son tres políticas."""
    coordinacion, no_incluyen = hechos._partes_de_la_recogida(lang)
    assert coordinacion == hechos._politica("island_pickup", lang)
    assert no_incluyen == hechos._politica("island_plans_exclude", lang)
    assert ("almuerzo" if lang == "es" else "lunch") in no_incluyen
    assert "Barú" not in no_incluyen and "Barú" not in coordinacion
    assert "Barú" in hechos._politica("baru_departs_from_cartagena", lang)


def test_con_incluye_va_lo_que_se_hace_y_lo_que_no_incluyen(monkeypatch):
    b = hechos.hechos(_estado("island"), ["incluye"], ["minicourse"])[0]
    que_se_hace = " ".join(b["en_que_consiste"]["island"])
    assert "piscina" in que_se_hace and "1 inmersión" in que_se_hace
    assert b["no_incluye"]["island"] == [hechos._partes_de_la_recogida("es")[1]]
    assert hechos._partes_de_la_recogida("es")[1] in b["recogida"]["island"]  # la pone el código entera


def test_con_el_horario_no_se_repite(monkeypatch):
    b = hechos.hechos(_estado("island"), ["incluye", "horario"], ["minicourse"])[0]
    assert "en_que_consiste" not in b and b["horario"]


def test_sin_origen_lo_que_se_hace_de_los_dos(monkeypatch):
    b = hechos.hechos(_estado(), ["incluye"], ["padi_open_water"])[0]
    assert set(b["en_que_consiste"]) == {"cartagena", "island"}


def test_arq3_echa_de_menos_lo_que_se_hace(monkeypatch):
    b = hechos.hechos(_estado("island"), ["incluye"], ["minicourse"])[0]
    solo_incluye = " ".join(b["incluye"]["island"])
    perdidos = hechos.faltan(solo_incluye, [b], ["incluye"])
    assert any("piscina" in p for p in perdidos) and any("1 inmersión" in p for p in perdidos)


def test_el_codigo_pone_lo_que_se_hace_en_su_marca(monkeypatch):
    b = hechos.hechos(_estado("island"), ["incluye"], ["minicourse"])[0]
    out = rh._poner_listas("Esto incluye:\n[[incluye]]\nY esto es lo que harás:\n[[en_que_consiste]]", [b], ["incluye"], "es")
    assert "[[" not in out and "piscina" in out and "Seguro de buceo" in out


def test_sin_su_marca_lo_que_se_hace_va_al_final(monkeypatch):
    b = hechos.hechos(_estado("island"), ["incluye"], ["minicourse"])[0]
    out = rh._poner_listas("Esto incluye:\n[[incluye]]", [b], ["incluye"], "es")
    assert "piscina" in out and not hechos.faltan(out, [{"en_que_consiste": b["en_que_consiste"]}], ["incluye"])


# --- 8e -------------------------------------------------------------------------------------------------------------

def test_la_recogida_de_las_islas_dice_como_se_coordina(monkeypatch):
    b = hechos.hechos(_estado("island"), ["horario"], ["specialty_nitrox"])[0]
    assert b["recogida"]["island"] == [hechos._politica("island_pickup_free", "es"),
                                       hechos._partes_de_la_recogida("es")[0]]
    assert "8:00" in " ".join(b["horario"]["island"])


def test_desde_cartagena_no_cambia(monkeypatch):
    b = hechos.hechos(_estado("cartagena"), ["horario"], ["specialty_nitrox"])[0]
    assert b["recogida"] == {"cartagena": [hechos._politica("meeting_point", "es")]}


# --- 8f: listas una vez ----------------------------------------------------------------------------------------------

def _especialidades(origen="cartagena"):
    st = _estado(origen)
    acts = ["specialty_nitrox", "specialty_buoyancy", "specialty_naturalist"]
    return hechos.hechos(st, ["descuento", "horario"], acts)


def test_la_lista_igual_en_todas_sale_una_vez(monkeypatch):
    out = rh._poner_listas("[[descuento]]", _especialidades(), ["descuento"], "es")
    assert out.count("10% de descuento para grupos") == 1
    assert "*Especialidad" not in out  # igual en todas: sin el nombre de cada una


def test_la_recogida_igual_sale_una_vez(monkeypatch):
    out = rh._poner_listas("[[recogida]]", _especialidades(), [], "es")
    assert out.count("Muelle de la Bodeguita") == 1


def test_listas_distintas_cada_una_con_su_nombre(monkeypatch):
    texto = rh._una_vez([({"nombre": "A"}, "• x"), ({"nombre": "B"}, "• y"), ({"nombre": "C"}, "• x")])
    assert texto == "*A, C*\n• x\n\n*B*\n• y"


def test_rotulo_doble_y_rotulo_suelto(monkeypatch):
    respuesta = ("Esto es lo que incluye:\n\n*Desde Cartagena*\n*Desde Cartagena:*\n• Almuerzo\n\n"
                 "*Si ya estás en las Islas del Rosario:*\n• Seguro\n\n*Si ya estás en las Islas del Rosario*\n\n\n\n"
                 "¿Saldrías desde Cartagena?")
    out = rh._sin_rotulos_sueltos(respuesta, "es")
    assert out == ("Esto es lo que incluye:\n\n*Desde Cartagena:*\n• Almuerzo\n\n"
                   "*Si ya estás en las Islas del Rosario:*\n• Seguro\n\n¿Saldrías desde Cartagena?")


def test_un_rotulo_con_su_frase_se_queda(monkeypatch):
    texto = "*From Cartagena:* Muelle de la Bodeguita at 8:00.\n\n*If you're already on the Rosario Islands:*\n• Pick-up"
    assert rh._sin_rotulos_sueltos(texto, "en") == texto


# --- 8f: el precio pendiente ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("pendiente, intenciones, esperado", [
    ("¿cuánto cuestan?", ["incluye"], ["incluye", "precio"]),
    (None, ["incluye"], ["incluye"]),            # sin precio pendiente
    ("¿cuánto cuestan?", [], []),               # Jev calla: nada que añadir
    ("¿cuánto cuestan?", ["precio"], ["precio"]),  # ya estaba
])
def test_el_precio_pendiente_entra_en_las_intenciones(monkeypatch, pendiente, intenciones, esperado):
    from src.orchestration import graph

    monkeypatch.setattr(graph, "_INTENCION_DE_SENAL", {n: n for n in ("precio", "incluye")})
    conv = _estado("cartagena")
    conv.pregunta_precio_pendiente = pendiente
    assert graph.intenciones_del_turno(conv, {n: True for n in intenciones}) == esperado


@pytest.mark.parametrize("jev, mensaje, queda", [
    (False, "soy de Medellín", "¿cuánto cuesta bucear?"),                 # no pregunta precio: se queda la de antes
    (True, "¿y el snorkel cuánto vale?", "¿y el snorkel cuánto vale?"),  # otro precio: manda el nuevo
    (None, "somos de Bogotá", "¿cuánto cuesta bucear?"),                 # Jev calla: las palabras de siempre
])
def test_la_pregunta_de_precio_guardada_no_se_pisa(jev, mensaje, queda):
    from src.agents import conversational_core as core

    st = _estado()
    st.pregunta_precio_pendiente = "¿cuánto cuesta bucear?"
    st._jev_pide_precio = jev
    core._fijar_origen_antes_del_precio(st, mensaje)
    assert st.pregunta_precio_pendiente == queda
