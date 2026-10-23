"""ARQ-1t (22-oct, flag `paquete_varios_dias`): «el paquete de varios días» sin cifra. El extractor lo dice (paso 6), la
duración queda en varios días y, sin plan elegido, los hechos son los de los paquetes: el precio desde el primero (con la
lista de todos) y qué incluye, lo común a todos. Controles: con un plan elegido o sin varios días, como antes."""
import pytest

from src.agents import extractor_turno as ex
from src.agents.intent_detector import DetectedIntent
from src.agents.nucleo import extractor as core_extractor
from src.config import settings
from src.flows import hechos
from src.flows.state import ConversationState


def _bloque(intenciones, **campos):
    st = ConversationState(conversation_id="arq1t", language="es")
    for k, v in campos.items():
        setattr(st, k, v)
    return hechos.hechos(st, intenciones, ["certified_diving"])[0]


def test_el_campo_va_solo_con_el_flag(monkeypatch):
    monkeypatch.setattr(settings, "paquete_varios_dias", False)
    assert "paquete_varios_dias" not in ex.campos_paso6([])
    monkeypatch.setattr(settings, "paquete_varios_dias", True)
    assert "paquete_varios_dias" in ex.campos_paso6([])


@pytest.mark.parametrize("flag, dice, duracion", [(True, True, "multi_day"), (False, True, None), (True, None, None)])
def test_la_duracion_queda_en_varios_dias(monkeypatch, flag, dice, duracion):
    monkeypatch.setattr(settings, "paquete_varios_dias", flag)
    intent = DetectedIntent()
    st = ConversationState(conversation_id="arq1t")
    core_extractor._poner_duracion(intent, st, {"paquete_varios_dias": dice} if dice else {}, "el paquete de varios días")
    assert intent.duration == duracion


def test_incluye_lo_comun_a_los_paquetes(monkeypatch):
    monkeypatch.setattr(settings, "paquete_varios_dias", True)
    b = _bloque(["incluye"], detected_duration="multi_day")
    cartagena = b["incluye"]["cartagena"]
    assert "Almuerzo el primer día" in cartagena
    assert not any("inmersiones guiadas" in x for x in cartagena)  # el número cambia de un paquete a otro
    assert any("alojamiento" in x.lower() for x in b["no_incluye"]["cartagena"])
    assert len(b["paquetes"]["cartagena"]) >= 3 and all("días" in p for p in b["paquetes"]["cartagena"])


def test_el_plan_base_apuntado_por_defecto_no_es_una_eleccion(monkeypatch):
    """rutas/booking apunta `detected_service_id` = el plan base en cuanto se sabe la actividad (banco arq-1t, A = B)."""
    monkeypatch.setattr(settings, "paquete_varios_dias", True)
    b = _bloque(["incluye"], detected_duration="multi_day", detected_service_id="2_dives_1_day")
    assert "paquetes" in b


def test_el_precio_parte_del_primer_paquete(monkeypatch):
    monkeypatch.setattr(settings, "paquete_varios_dias", True)
    b = _bloque(["precio"], detected_duration="multi_day", location="cartagena")
    assert "días" in b["precio"]["cartagena"]["plan"] and b["otros_planes"]


@pytest.mark.parametrize("campos", [{"detected_duration": "single_day"}, {"detected_duration": "multi_day",
                                                                            "selected_service": "5_dives_2_days"}])
def test_controles_como_antes(monkeypatch, campos):
    monkeypatch.setattr(settings, "paquete_varios_dias", True)
    b = _bloque(["incluye"], **campos)
    assert "paquetes" not in b
    assert any("inmersiones guiadas" in x for x in b["incluye"]["cartagena"])


def test_apagado_como_antes(monkeypatch):
    monkeypatch.setattr(settings, "paquete_varios_dias", False)
    b = _bloque(["incluye"], detected_duration="multi_day")
    assert "paquetes" not in b and any("2 inmersiones" in x for x in b["incluye"]["cartagena"])


def test_la_foto_del_turno_lleva_los_varios_dias_del_mensaje(monkeypatch):
    """El redactor contesta antes de que la extracción guarde la duración (como el origen y la nacionalidad)."""
    from src.agents import redactor_hechos

    monkeypatch.setattr(settings, "paquete_varios_dias", True)
    st = ConversationState(conversation_id="arq1t")
    foto = redactor_hechos._foto(st, {"paquete_varios_dias": True}, None)
    assert foto.detected_duration == "multi_day" and st.detected_duration is None
