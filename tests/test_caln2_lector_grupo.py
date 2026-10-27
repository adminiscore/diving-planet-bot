"""CALN-2 (27-oct): el lector del grupo, paso 1 (sin enchufar). Lo que el código acepta de su lectura."""
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
