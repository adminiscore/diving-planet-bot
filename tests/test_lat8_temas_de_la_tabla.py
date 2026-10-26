"""lat-8 (26-oct, decisión de Gadea #1880): cuatro temas más de la tabla, contados en real-1 (#1879): dónde alojarse
(`hoteles`), quedarse en las islas y volver otro día (`regreso`), fotos y vídeos (`fotos`) y la política general de
cambios y cancelación (`cambios`). Sus hechos son políticas que la base ya tiene. Sin red: la pregunta de Jev, la señal,
los hechos y lo que `faltan` echa de menos. La conducta, en docs/robustness/lat/banco-lat8.json."""
import pytest

from src.agents import jev_router as j
from src.domain.politicas import politica
from src.flows import hechos as h
from src.flows.state import ConversationState
from src.orchestration import graph

TEMAS = {"hoteles": j.PIDE_HOTELES, "regreso": j.PIDE_REGRESO, "fotos": j.PIDE_FOTOS, "cambios": j.PIDE_CAMBIOS}


def _st(**kw) -> ConversationState:
    return ConversationState(conversation_id="lat8", language="es", **kw)


def test_jev_pregunta_los_cuatro_y_otra_cosa_ya_no_los_cuenta():
    q = j._questions_for_turn()
    assert set(TEMAS.values()) <= set(q)
    otra = q[j.PIDE_OTRA_COSA]["instructions"]
    assert "cancellations, " not in otra and otra.endswith(j._OTRA_COSA_SIN_LOS_TEMAS_DE_LAT8)


def test_cambios_excluye_la_reserva_ya_hecha():
    """Cambiar o cancelar una reserva YA hecha sigue yendo a un asesor (decisión de Gadea, #1882)."""
    assert "ALREADY made" in j._PIDE_CAMBIOS_Q["instructions"]


def test_las_senales_viajan_tambien_cuando_jev_duda():
    assert set(TEMAS.values()) <= set(j._TURN_SIGNALS) and set(TEMAS.values()) <= set(j._U34_QUESTIONS)


def test_umbral():
    out = j.answers_to_signals({j.PIDE_FOTOS: {"noul": 0.9}, j.PIDE_HOTELES: {"noul": 0.4}})
    assert out[j.PIDE_FOTOS] is True and out[j.PIDE_HOTELES] is False


def test_la_senal_da_la_intencion():
    assert {graph._INTENCION_DE_SENAL[t] for t in TEMAS} == set(TEMAS.values())
    assert set(TEMAS) <= set(h.INTENCIONES) and set(TEMAS) <= h.INTENCIONES_SIN_ACTIVIDAD
    assert graph.intenciones_del_turno(_st(), {j.PIDE_REGRESO: True}) == ["regreso"]


@pytest.mark.parametrize("tema, claves", [("hoteles", ["other_island_hotels"]), ("regreso", ["return_different_day"]),
                                          ("fotos", ["photos_videos_policy"]),
                                          ("cambios", ["reschedule", "modify_booking", "cancellation"])])
@pytest.mark.parametrize("lang", ["es", "en"])
def test_los_hechos_son_las_politicas(tema, claves, lang):
    st = ConversationState(conversation_id="lat8", language=lang)
    [general] = h.hechos_sin_actividad(st, [tema])
    assert general[tema] == [politica(c, lang) for c in claves]
    [con_actividad] = h.hechos(st, [tema], ["minicourse"])
    assert con_actividad[tema] == general[tema]


def test_faltan_echa_de_menos_lo_que_contesta():
    [b] = h.hechos_sin_actividad(_st(), ["hoteles", "fotos"])
    perdidos = h.faltan("Te esperamos en la isla.", [b], ["hoteles", "fotos"])
    assert perdidos == [b["hoteles"][0], b["fotos"][0]]
    assert h.faltan(b["hoteles"][0] + " " + b["fotos"][0], [b], ["hoteles", "fotos"]) == []


def test_sin_los_temas_nada_cambia():
    [b] = h.hechos_sin_actividad(_st(), ["horario"])
    assert not set(TEMAS) & set(b)
