"""CALN-2 (27-oct): el lector del grupo, paso 1 (sin enchufar). Lo que el código acepta de su lectura."""
import asyncio
import json

import pytest

from src.agents import lector_grupo as lg

MADRE = "Hola! Yo tengo el Open Water y quiero bucear. Mi esposo no bucea y vamos con los niños, de 7 y 4 años."


def _p(**campos):
    base = {"quien": "cliente", "cantidad": 1, "certificado": None, "actividad": None, "edades": [], "cita": ""}
    return {**base, **campos}


def test_la_familia_con_su_cita():
    datos = {"total_dicho": None, "personas": [
        _p(certificado=True, cita="Yo tengo el Open Water"),
        _p(quien="esposo", certificado=False, cita="Mi esposo no bucea"),
        _p(quien="niños", cantidad=2, edades=[7, 4], cita="vamos con los niños, de 7 y 4 años")]}
    lectura = lg.validar(datos, MADRE)
    assert lg.total_de(lectura) == 4 and not lectura["descartes"]
    assert [p["certificado"] for p in lectura["personas"]] == [True, False, None]
    assert lectura["personas"][2]["edades"] == [7, 4]


def test_lo_que_no_esta_en_el_mensaje_no_entra():
    datos = {"personas": [
        _p(cita="Yo tengo el Open Water"),
        _p(quien="abuela", cita="mi abuela viene también"),          # no está en el mensaje: inventada
        _p(quien="esposo", cantidad=0, cita="Mi esposo no bucea"),     # cantidad imposible
        _p(cita="quiero bucear"),                                      # un segundo «cliente»
        _p(quien="niños", cantidad=2, actividad="paracaidismo", edades=[7, 9], cita="vamos con los niños, de 7 y 4 años")]}
    lectura = lg.validar(datos, MADRE)
    assert [d["motivo"] for d in lectura["descartes"]] == ["cita", "cantidad", "dos clientes"]
    ninos = lectura["personas"][-1]
    assert ninos["actividad"] is None and ninos["edades"] == [7]  # el 9 no está en su cita


@pytest.mark.parametrize("total, queda", [(5, 5), (0, None), (True, None), ("4", None)])
def test_el_total_dicho(total, queda):
    assert lg.validar({"total_dicho": total, "personas": []}, MADRE)["total_dicho"] == queda


def _cliente(responder):
    class _C:
        async def create(self, **kw):
            return responder(kw)

    return type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})()


def _falla(_kw):
    raise RuntimeError("sin red")


@pytest.mark.asyncio
async def test_si_la_llamada_falla_no_hay_lectura():
    assert await lg.leer_grupo(MADRE, client=_cliente(_falla)) is None


@pytest.mark.asyncio
async def test_la_llamada_y_su_validacion():
    respuesta = {"total_dicho": None, "personas": [_p(certificado=True, cita="Yo tengo el Open Water")]}

    def _responde(kw):
        assert "Mi esposo no bucea" in kw["messages"][1]["content"]
        msg = type("M", (), {"content": json.dumps(respuesta)})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    lectura = await lg.leer_grupo(MADRE, client=_cliente(_responde))
    assert lg.total_de(lectura) == 1 and lectura["segundos"] >= 0


def test_quien_ya_esta_certificado_no_elige_el_open_water():
    datos = {"personas": [_p(certificado=True, actividad="padi_open_water", cita="Yo tengo el Open Water")]}
    assert lg.validar(datos, MADRE)["personas"][0]["actividad"] is None


# --- Paso 2 (flag `lector_grupo`): cuándo hace falta, qué rellena, lanzado con Jev, usado o tirado -------------------

B5 = {"total_dicho": None, "personas": [
    _p(certificado=True, cita="Yo tengo el Open Water"),
    _p(quien="esposo", certificado=False, cita="Mi esposo no bucea"),
    _p(quien="niños", cantidad=2, edades=[7, 4], cita="vamos con los niños, de 7 y 4 años")], "descartes": []}


@pytest.mark.parametrize("datos, hace_falta", [
    ({"activity": "certified_diving", "is_certified": True, "edades": [7, 4]}, True),        # b5: sin total
    ({"group_size": 6}, True),                                                               # b6: 6 sin reparto
    ({"group_size": 3, "group_allocation": {"snorkel": 2, "undecided": 1}}, True),           # l06: alguien sin elegir
    ({"group_size": 3, "group_allocation": {"snorkel": 3}}, False),                          # completo
    ({"activity": "snorkel"}, False),                                                        # no habla de otros
])
def test_cuando_hace_falta_el_lector(datos, hace_falta):
    assert lg.por_completar(datos) is hace_falta


def test_rellena_lo_que_el_extractor_dejo_vacio():
    nuevos, cambios = lg.completar({"activity": "certified_diving", "is_certified": True, "edades": [7, 4]}, B5)
    assert nuevos["group_size"] == 4
    assert nuevos["group_allocation"] == {"certified_diving": 1, "undecided": 3}
    assert "sin_decidir_certificados" not in nuevos  # el esposo no, los niños no se sabe: no se decide
    assert cambios


def test_el_reparto_del_extractor_que_cuadra_manda_y_el_lector_da_la_certificacion():
    datos = {"group_size": 3, "group_allocation": {"snorkel": 2, "undecided": 1}}
    lectura = {"total_dicho": 3, "personas": [_p(cantidad=2, actividad="snorkel", cita="nosotras dos queremos hacer snorkel"),
                                              _p(quien="primo", certificado=True, cita="Mi primo tiene la certificación")]}
    nuevos, _ = lg.completar(datos, lectura)
    assert nuevos["group_allocation"] == {"snorkel": 2, "undecided": 1}
    assert nuevos["sin_decidir_certificados"] is True


def test_seis_amigos_cuatro_certificados():
    lectura = {"total_dicho": 6, "personas": [_p(cantidad=4, certificado=True, cita="4 tenemos certificación"),
                                              _p(quien="los otros dos", cantidad=2, cita="2 dudan")]}
    nuevos, _ = lg.completar({"group_size": 6}, lectura)
    assert nuevos["group_allocation"] == {"undecided": 6} and nuevos["is_certified"] is True


@pytest.fixture
def _lector_falso(monkeypatch):
    from src.agents.nucleo import extractor as nx
    from src.config import settings

    llamadas = []

    async def _leer(mensaje, **_kw):
        llamadas.append(mensaje)
        return B5

    monkeypatch.setattr(lg, "leer_grupo", _leer)
    monkeypatch.setattr(settings, "lector_grupo", True)
    return nx, llamadas


@pytest.mark.asyncio
async def test_con_el_interruptor_apagado_no_se_lanza(monkeypatch, _lector_falso):
    from src.config import settings

    nx, llamadas = _lector_falso
    monkeypatch.setattr(settings, "lector_grupo", False)
    from src.flows.state import ConversationState

    st = ConversationState(conversation_id="lector-apagado")
    st._jev_companion = 0.9
    nx.lanzar_lector_grupo(st, MADRE)
    assert st._lector_grupo is None
    datos = {"activity": "certified_diving", "edades": [7, 4]}
    assert await nx._con_el_lector_del_grupo(st, MADRE, datos) is datos and not llamadas


@pytest.mark.asyncio
async def test_lanzado_con_jev_se_usa_si_hace_falta(_lector_falso):
    from src.flows.state import ConversationState

    nx, llamadas = _lector_falso
    st = ConversationState(conversation_id="lector-usado")
    st._jev_companion = 0.9
    nx.lanzar_lector_grupo(st, MADRE)
    assert st._lector_grupo is not None
    nuevos = await nx._con_el_lector_del_grupo(st, MADRE, {"activity": "certified_diving", "edades": [7, 4]})
    assert nuevos["group_size"] == 4 and llamadas == [MADRE]


@pytest.mark.asyncio
async def test_lanzado_con_jev_se_tira_si_no_hace_falta(_lector_falso):
    from src.flows.state import ConversationState

    nx, _ = _lector_falso
    st = ConversationState(conversation_id="lector-tirado")
    st._jev_adds_person = 0.5
    nx.lanzar_lector_grupo(st, "somos 3 para snorkel")
    tarea = st._lector_grupo
    datos = {"group_size": 3, "group_allocation": {"snorkel": 3}}
    assert await nx._con_el_lector_del_grupo(st, "somos 3 para snorkel", datos) is datos
    await asyncio.sleep(0)
    assert tarea.cancelled() or tarea.done()


@pytest.mark.asyncio
async def test_jev_seguro_de_que_no_no_lo_lanza(_lector_falso):
    from src.flows.state import ConversationState

    nx, _ = _lector_falso
    st = ConversationState(conversation_id="lector-jev-no")
    st._jev_companion, st._jev_adds_person = 0.05, 0.1
    nx.lanzar_lector_grupo(st, MADRE)
    assert st._lector_grupo is None


@pytest.mark.asyncio
async def test_la_madre_buzo_con_el_lector_en_el_turno_entero(extractor_dice, monkeypatch, _lector_falso):
    from unittest.mock import AsyncMock

    from src.agents.nucleo import extraction as core_extraction
    from src.agents.nucleo import routing as core_routing
    from src.agents.supervisor import route_message
    from src.flows.state import ConversationState

    senales = AsyncMock(return_value={})
    monkeypatch.setattr(core_routing, "detect_special_signals", senales)
    monkeypatch.setattr(core_extraction, "detect_special_signals", senales)
    monkeypatch.setattr(core_extraction, "resolve_slot_answer", AsyncMock(return_value={}))
    extractor_dice({MADRE: {"activity": "certified_diving", "is_certified": True, "quiere_bucear": True,
                            "edades": [7, 4], "otro_sin_certificar": True}})
    st = ConversationState(conversation_id="lector-turno")
    await route_message(st, MADRE)
    assert st.detected_group_size == 4 and st.detected_activity == "certified_diving"
    assert st.detected_group_allocation == {"certified_diving": 1} and st.pending_undecided_qty == 3


def test_un_mensaje_que_nombra_a_una_parte_no_cambia_el_total_sabido():
    """g29 (medida del paso 2): «yo el minicurso, la de 14 también y la pequeña Bubble Makers» no habla del suegro."""
    lectura = {"total_dicho": None, "personas": [_p(actividad="minicourse", cita="Yo tengo el Open Water"),
                                                 _p(quien="hija", cantidad=3, cita="vamos con los niños, de 7 y 4 años")]}
    nuevos, cambios = lg.completar({"activity": "minicourse"}, lectura, total_sabido=5)
    assert "group_size" not in nuevos and "group_allocation" not in nuevos and not cambios


def test_el_buzo_inactivo_no_pierde_el_buceo_aunque_el_lector_diga_no_certificado():
    """s03 (medida del paso 2): «he hasn't been diving in 3 years» leído como no certificado."""
    from src.agents import conversational_core as core
    from src.flows.state import ConversationState

    st = ConversationState(conversation_id="lector-s03")
    st.sin_decidir_certificados = False
    assert "certified_diving" not in core._companion_activity_options(st)
    st.acompanante_certificado_inactivo = True
    assert "certified_diving" in core._companion_activity_options(st)
