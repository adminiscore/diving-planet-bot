"""ex-9b paso 6: los últimos regex de "entender al cliente" (clase E del estudio) dejan de decidir; campos nuevos del
extractor, cada uno con su flag (APAGADO = la llamada y la conducta de hoy):

1. `duracion_por_extractor`: los días de buceo y de estancia (manda lo que dice de bucear; decisión de Gadea, 19-oct);
   fuera los falsos positivos de `_detect_duration` ("embarazada de 4 meses", "3 días esperando");
2. `edades_por_extractor`: las edades con su cita (el regex solo valida la cifra; `fill_gaps` ya no las supone);
3. `plan_elegido_por_extractor`: aceptar el paquete que el bot acaba de proponer ("perfecto, ese me sirve");
4. `reparto_al_sumarse_alguien`: alguien que se suma a un grupo ya sabido (el extractor ve el reparto sabido; el atajo
   de "reparto completo" deja pasar la red si Jev está seguro de que entra alguien);
5. `notas_rag_desde_estado`: las notas del RAG sobre otra persona del grupo salen del estado.
Cada uno: apagado = hoy; encendido = lee el extractor; extractor caído = como hoy. Sin red: `extractor_dice`.
"""
import json
from unittest.mock import AsyncMock

import pytest

from src.agents import conversational_core as core
from src.agents import extractor_turno as ex
from src.agents import supervisor
from src.agents.conversational_core import SLOT_AGES, SLOT_COMPANION_ACTIVITY
from src.agents.intent_detector import DetectedIntent
from src.agents.nucleo import extraction as core_extraction
from src.agents.nucleo import extractor as core_extractor
from src.agents.nucleo import routing as core_routing
from src.agents.rutas.contexto_rag import _build_extra_context
from src.config import settings
from src.flows.state import ConversationState

FLAGS6 = ("duracion_por_extractor", "edades_por_extractor", "plan_elegido_por_extractor", "reparto_al_sumarse_alguien",
          "notas_rag_desde_estado")
PROPUESTA = ("Te propongo el *paquete de 5 inmersiones en 2 días*: sales desde Cartagena, duermes en la isla y vuelves "
             "al día siguiente. ¿Te encaja?")


@pytest.fixture(autouse=True)
def _apagados(monkeypatch):
    for f in FLAGS6:
        monkeypatch.setattr(settings, f, False)
    # Los campos en la MISMA llamada (lo que prueban estos tests); la llamada aparte la encienden los suyos (sección 7).
    monkeypatch.setattr(settings, "paso6_en_llamada_aparte", False)


@pytest.fixture
def encender(monkeypatch):
    return lambda *flags: [monkeypatch.setattr(settings, f, True) for f in flags]


@pytest.fixture
def extractor_caido(monkeypatch):
    """El extractor (y su respaldo) falla: `extraer_turno` devuelve None."""
    monkeypatch.setattr(ex, "extraer_turno", AsyncMock(return_value=None))


def _estado(**campos) -> ConversationState:
    st = ConversationState(conversation_id="ex9b-6", language="es")
    for k, v in campos.items():
        setattr(st, k, v)
    return st


async def _entender(mensaje: str, state: ConversationState | None = None) -> ConversationState:
    state = state or _estado()
    await core._understand(state, mensaje)
    return state


def _cliente(datos: dict, llamadas: list):
    class _C:
        async def create(self, **kw):
            llamadas.append(kw)
            msg = type("M", (), {"content": json.dumps(datos)})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()], "usage": None})()

    return type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})()


async def _llamada(mensaje: str, datos: dict, *, history=None, sabido=None) -> tuple[dict, dict]:
    llamadas: list = []
    out = await ex.extraer_turno(mensaje, history=history, sabido=sabido or {}, client=_cliente(datos, llamadas))
    return out, llamadas[0]


def _campos_del_esquema(llamada: dict) -> set:
    return set(llamada["response_format"]["json_schema"]["schema"]["properties"])


# --- 0. el extractor: con los flags apagados, la llamada de siempre --------------------------------------------------


@pytest.mark.asyncio
async def test_apagados_ni_campos_ni_reglas():
    out, llamada = await _llamada("estaré una semana, solo quiero bucear un día", {
        "dias_de_buceo": {"valor": 1, "cita": "solo quiero bucear un día"}}, history=[{"role": "assistant", "content": PROPUESTA}],
        sabido={"group_size": 2})
    nuevos = {"dias_de_buceo", "dias_de_estancia", "edades", "acepta_propuesta", "otro_sin_certificar",
              "otro_certificado_inactivo"}
    assert not (_campos_del_esquema(llamada) & nuevos)
    sistema = llamada["messages"][0]["content"]
    for regla in (ex.REGLA_DURACION_ES, ex.REGLA_EDADES_ES, ex.REGLA_ACEPTA_ES, ex.REGLA_OTRAS_PERSONAS_ES,
                  ex.REGLA_SUMARSE_ES):
        assert regla not in sistema
    assert "dias_de_buceo" not in out


@pytest.mark.asyncio
@pytest.mark.parametrize("flag, campos, regla", [
    ("duracion_por_extractor", {"dias_de_buceo", "dias_de_estancia"}, ex.REGLA_DURACION_ES),
    ("edades_por_extractor", {"edades"}, ex.REGLA_EDADES_ES),
    ("notas_rag_desde_estado", {"otro_sin_certificar", "otro_certificado_inactivo"}, ex.REGLA_OTRAS_PERSONAS_ES),
])
async def test_cada_flag_su_campo_y_su_regla(encender, flag, campos, regla):
    encender(flag)
    _, llamada = await _llamada("hola", {})
    esquema = llamada["response_format"]["json_schema"]["schema"]
    assert campos <= set(esquema["properties"]) and campos <= set(esquema["required"])
    assert regla in llamada["messages"][0]["content"]


@pytest.mark.asyncio
async def test_acepta_propuesta_solo_si_el_bot_propuso_un_paquete(encender):
    encender("plan_elegido_por_extractor")
    _, sin = await _llamada("perfecto, ese me sirve", {}, history=[{"role": "assistant", "content": "¿Cuántos sois?"}])
    assert "acepta_propuesta" not in _campos_del_esquema(sin)
    out, con = await _llamada("perfecto, ese me sirve", {"acepta_propuesta": {"valor": True, "cita": "perfecto, ese me sirve"}},
                              history=[{"role": "assistant", "content": PROPUESTA}])
    assert "acepta_propuesta" in _campos_del_esquema(con) and ex.REGLA_ACEPTA_ES in con["messages"][0]["content"]
    assert out["acepta_propuesta"] is True
    # Comparar varios paquetes no es proponer uno.
    assert ex.plan_que_propone_el_bot([{"role": "assistant", "content": "el de 5 inmersiones en 2 días o el de 7 inmersiones en 3 días"}]) is None


@pytest.mark.asyncio
async def test_la_regla_de_sumarse_solo_con_el_grupo_sabido(encender):
    encender("reparto_al_sumarse_alguien")
    _, sin_grupo = await _llamada("mi hermano también viene", {})
    assert ex.REGLA_SUMARSE_ES not in sin_grupo["messages"][0]["content"]
    _, con_grupo = await _llamada("mi hermano también viene", {}, sabido={"group_size": 2})
    assert ex.REGLA_SUMARSE_ES in con_grupo["messages"][0]["content"]


@pytest.mark.asyncio
async def test_las_edades_se_validan_con_su_cita(encender):
    encender("edades_por_extractor")
    out, _ = await _llamada("mis hijos tienen 8 y nueve", {"edades": {"valor": [8, 9, 12], "cita": "mis hijos tienen 8 y nueve"}})
    assert out["edades"] == [8, 9]  # el 12 no está en la cita
    out, _ = await _llamada("tengo dos hijos", {"edades": {"valor": [7], "cita": "tengo dos hijos"}})
    assert "edades" not in out
    assert ex.extraer_turno.ultimo_motivo["edades"].startswith("ninguna edad")


@pytest.mark.asyncio
async def test_los_dias_tienen_que_ser_un_numero_y_con_cita(encender):
    encender("duracion_por_extractor")
    out, _ = await _llamada("una semana en las islas", {"dias_de_estancia": {"valor": 7, "cita": "una semana"},
                                                       "dias_de_buceo": {"valor": 0, "cita": "una semana"}})
    assert out["dias_de_estancia"] == 7 and "dias_de_buceo" not in out
    out, _ = await _llamada("hola", {"dias_de_buceo": {"valor": 2, "cita": "dos días de buceo"}})
    assert "dias_de_buceo" not in out


# --- 1. duración ---------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duracion_apagado_el_regex_decide(extractor_dice):
    extractor_dice({"hola, tengo 5 meses de embarazo, ¿puedo bucear?": {}})
    st = await _entender("hola, tengo 5 meses de embarazo, ¿puedo bucear?")
    assert st.detected_duration == "multi_day"  # el falso positivo de hoy


@pytest.mark.asyncio
@pytest.mark.parametrize("mensaje", ["hola, tengo 5 meses de embarazo, ¿puedo bucear?",
                                     "hace 2 semanas que espero respuesta",
                                     "a lo mejor vamos dentro de unos meses"])
async def test_duracion_encendido_sin_dias_dichos_no_hay_duracion(encender, extractor_dice, mensaje):
    encender("duracion_por_extractor")
    extractor_dice({mensaje: {}})
    st = await _entender(mensaje)
    assert st.detected_duration is None


@pytest.mark.asyncio
async def test_duracion_mandan_los_dias_de_buceo(encender, extractor_dice):
    encender("duracion_por_extractor")
    msg = "estaré del 5 al 9 en cartagena, pero solo quiero bucear un día"
    extractor_dice({msg: {"dias_de_buceo": 1, "dias_de_estancia": 5}})
    st = await _entender(msg)
    assert st.detected_duration == "single_day" and st.duracion_de_buceo is True


@pytest.mark.asyncio
async def test_duracion_la_estancia_recomienda_y_los_dias_de_buceo_la_cambian(encender, extractor_dice):
    encender("duracion_por_extractor")
    extractor_dice({"vamos a estar una semana": {"dias_de_estancia": 7},
                    "pero solo queremos bucear un día": {"dias_de_buceo": 1},
                    "nos quedamos 3 días en total": {"dias_de_estancia": 3}})
    st = await _entender("vamos a estar una semana")
    assert st.detected_duration == "multi_day" and st.duracion_de_buceo is False
    await _entender("pero solo queremos bucear un día", st)
    assert st.detected_duration == "single_day" and st.duracion_de_buceo is True
    await _entender("nos quedamos 3 días en total", st)
    assert st.detected_duration == "single_day"  # la estancia no cambia lo que dijo de bucear


@pytest.mark.asyncio
async def test_duracion_un_paquete_de_varios_dias_del_catalogo(encender, extractor_dice):
    encender("duracion_por_extractor")
    extractor_dice({"me interesa el paquete de 5 inmersiones": {},
                    "alguien que conozco hizo el paquete con ustedes": {}})
    assert (await _entender("me interesa el paquete de 5 inmersiones")).detected_duration == "multi_day"
    # La palabra "paquete" sola ya no es "varios días" (era `_MULTI_DAY_PRODUCT_RE`).
    assert (await _entender("alguien que conozco hizo el paquete con ustedes")).detected_duration is None


@pytest.mark.asyncio
async def test_duracion_extractor_caido_como_hoy(encender, extractor_caido):
    encender("duracion_por_extractor")
    st = await _entender("hola, tengo 5 meses de embarazo, ¿puedo bucear?")
    assert st.detected_duration == "multi_day"


@pytest.mark.asyncio
async def test_duracion_respuesta_corta_a_un_dia_o_varios(encender, extractor_dice):
    encender("duracion_por_extractor")
    extractor_dice({"llegamos el jueves y nos vamos el domingo": {"dias_de_estancia": 4}})
    st = _estado(core_pending_slot=SLOT_COMPANION_ACTIVITY)
    ia = await core_routing._lectura_de_la_ia(st, "llegamos el jueves y nos vamos el domingo", {}, SLOT_COMPANION_ACTIVITY)
    assert ia is not None
    assert core_routing._apply_short_answer(st, "llegamos el jueves y nos vamos el domingo", ia=ia) is True
    assert st.detected_duration == "multi_day"
    # El botón o el número de la opción son formato: sin IA.
    st = _estado(core_pending_slot=SLOT_COMPANION_ACTIVITY)
    assert await core_routing._lectura_de_la_ia(st, "1", {}, SLOT_COMPANION_ACTIVITY) is None


# --- 2. edades -----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edades_apagado_el_regex_decide(extractor_dice):
    extractor_dice({"el pequeño tiene 6 y el grande 10": {}})
    st = await _entender("el pequeño tiene 6 y el grande 10")
    assert st.detected_ages == []  # hoy el regex no lo lee


@pytest.mark.asyncio
async def test_edades_encendido_las_del_extractor(encender, extractor_dice, monkeypatch):
    encender("edades_por_extractor")
    relleno = AsyncMock(return_value={})
    monkeypatch.setattr(core_extraction, "fill_gaps", relleno)
    extractor_dice({"el pequeño tiene 6 y el grande 10": {"edades": [6, 10]},
                    "soy residente hace 3 años": {}})
    st = await _entender("el pequeño tiene 6 y el grande 10", _estado(kids_mention_detected=True))
    assert st.detected_ages == [6, 10]
    relleno.assert_not_awaited()  # el relleno con el historial ya no supone edades
    st = await _entender("soy residente hace 3 años")
    assert st.detected_ages == []


@pytest.mark.asyncio
async def test_edades_extractor_caido_como_hoy(encender, extractor_caido, monkeypatch):
    encender("edades_por_extractor")
    relleno = AsyncMock(return_value={})
    monkeypatch.setattr(core_extraction, "fill_gaps", relleno)
    st = await _entender("los niños tienen 6 y 9 años", _estado(kids_mention_detected=True))
    assert st.detected_ages == [6, 9]  # el regex de siempre


@pytest.mark.asyncio
async def test_edades_respuesta_corta(encender, extractor_dice):
    encender("edades_por_extractor")
    extractor_dice({"el mayor 12 y la menor 8": {"edades": [12, 8]}})
    st = _estado(core_pending_slot=SLOT_AGES)
    ia = await core_routing._lectura_de_la_ia(st, "el mayor 12 y la menor 8", {}, SLOT_AGES)
    assert core_routing._apply_short_answer(st, "el mayor 12 y la menor 8", ia=ia) is True
    assert st.detected_ages == [8, 12]
    # Solo cifras: formato, la lectura de siempre.
    st = _estado(core_pending_slot=SLOT_AGES)
    assert await core_routing._lectura_de_la_ia(st, "6 y 9", {}, SLOT_AGES) is None
    assert core_routing._apply_short_answer(st, "6 y 9") is True and st.detected_ages == [6, 9]


# --- 3. plan elegido -----------------------------------------------------------------------------------------------


def _con_propuesta(**campos) -> ConversationState:
    st = _estado(**campos)
    st.history = [{"role": "user", "content": "queremos bucear varios días"}, {"role": "assistant", "content": PROPUESTA}]
    st.mixed_cart = [{"type": "certified_diving", "qty": 2}]
    return st


@pytest.mark.asyncio
async def test_plan_apagado_solo_la_frase(extractor_dice):
    extractor_dice({"perfecto, ese me sirve": {"acepta_propuesta": True}})
    st = _con_propuesta()
    await core_routing._paquete_confirmado(st, "perfecto, ese me sirve")
    assert st.detected_cert_dives is None
    await core_routing._paquete_confirmado(st, "quiero este paquete")
    assert st.detected_cert_dives == 5 and st.mixed_cart == []


@pytest.mark.asyncio
async def test_plan_encendido_aceptar_la_propuesta_la_elige(encender, extractor_dice):
    encender("plan_elegido_por_extractor")
    extractor_dice({"perfecto, ese me sirve": {"acepta_propuesta": True}, "¿y cuánto cuesta?": {}})
    st = _con_propuesta()
    await core_routing._paquete_confirmado(st, "¿y cuánto cuesta?")
    assert st.detected_cert_dives is None and st.mixed_cart  # preguntar el precio no es elegir
    core_extractor.cancelar_extraccion_adelantada(st)  # fin del turno
    await core_routing._paquete_confirmado(st, "perfecto, ese me sirve")
    assert st.detected_cert_dives == 5 and st.mixed_cart == []


@pytest.mark.asyncio
async def test_plan_sin_propuesta_no_espera_al_extractor(encender, monkeypatch):
    encender("plan_elegido_por_extractor")
    leer = AsyncMock(return_value={"acepta_propuesta": True})
    monkeypatch.setattr(core_extractor, "lectura_del_extractor", leer)
    st = _estado()
    st.history = [{"role": "assistant", "content": "¿Desde dónde saldrías?"}]
    await core_routing._paquete_confirmado(st, "perfecto")
    leer.assert_not_awaited()


@pytest.mark.asyncio
async def test_plan_extractor_caido_como_hoy(encender, extractor_caido):
    encender("plan_elegido_por_extractor")
    st = _con_propuesta()
    await core_routing._paquete_confirmado(st, "perfecto, ese me sirve")
    assert st.detected_cert_dives is None
    await core_routing._paquete_confirmado(st, "quiero ese paquete")
    assert st.detected_cert_dives == 5


# --- 4. alguien que se suma al grupo -------------------------------------------------------------------------------


def _dos_buzos(**campos) -> ConversationState:
    return _estado(detected_activity="certified_diving", is_certified=True, detected_is_certified=True,
                   detected_group_size=2, location="cartagena", detected_location="cartagena", **campos)


def test_reparto_lo_sabido_lleva_el_reparto_aunque_no_este_guardado(encender):
    assert "group_allocation" not in core_extractor._sabido_para_extractor(_dos_buzos())
    encender("reparto_al_sumarse_alguien")
    assert core_extractor._sabido_para_extractor(_dos_buzos())["group_allocation"] == {"certified_diving": 2}


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", [False, True])
async def test_reparto_ampliado_por_el_extractor_suma_sin_preguntar(encender, extractor_dice, flag):
    if flag:
        encender("reparto_al_sumarse_alguien")
    msg = "mi hermano también viene, él quiere hacer snorkel"
    extractor_dice({msg: {"group_size": 3, "group_allocation": {"certified_diving": 2, "snorkel": 1}}})
    st = await _entender(msg, _dos_buzos())
    assert st.detected_group_size == 3
    assert st.detected_group_allocation == {"certified_diving": 2, "snorkel": 1}


@pytest.mark.asyncio
async def test_reparto_jev_seguro_de_que_ya_estaba_contado(encender, extractor_dice):
    encender("reparto_al_sumarse_alguien")
    msg = "mi amigo, el que ya venía, quiere snorkel"
    extractor_dice({msg: {"group_size": 3, "group_allocation": {"certified_diving": 2, "snorkel": 1}}})
    st = _dos_buzos()
    st._jev_adds_person = 0.05
    await core._understand(st, msg)
    assert st.detected_group_size == 2  # dos lectores en contra: no se suma a nadie aquí


@pytest.mark.parametrize("flag, joins, ambiguo, pasa", [
    (False, 0.97, True, False),   # hoy: el atajo se salta la red
    (True, 0.97, True, True),     # Jev seguro de que entra alguien: la red corre
    (True, 0.5, True, False),     # Jev duda: el atajo, como hoy
    (True, None, True, False),    # Jev calla: el atajo, como hoy
    (True, 0.97, False, False),   # el turno ya resolvió el grupo (o no nombra a nadie)
])
def test_reparto_el_atajo_deja_pasar_si_jev_esta_seguro(encender, flag, joins, ambiguo, pasa):
    if flag:
        encender("reparto_al_sumarse_alguien")
    st = _dos_buzos(detected_group_allocation={"certified_diving": 2})
    st._jev_companion = joins
    assert core_extraction._jev_seguro_de_que_se_suma(st, ambiguo) is pasa


@pytest.mark.asyncio
async def test_reparto_turno_entero_la_red_ya_no_se_salta(encender, extractor_dice, monkeypatch):
    """Grupo con reparto guardado {buceo: 2} y el extractor sin leer al hermano: hoy el atajo se salta la red y la
    persona se pierde; con el flag y Jev seguro (companion_joins 0,97), la red la suma."""
    msg = "mi hermano también viene, él quiere hacer snorkel"
    extractor_dice({msg: {}})
    senales = AsyncMock(return_value={"mentions_other_person": True, "companion_activity": "snorkel"})
    monkeypatch.setattr(core_extraction, "detect_special_signals", senales)

    async def turno(flag: bool) -> ConversationState:
        monkeypatch.setattr(settings, "reparto_al_sumarse_alguien", flag)
        st = _dos_buzos(detected_group_allocation={"certified_diving": 2}, last_dive_over_2_years=False,
                        detected_last_dive_over_2_years=False)
        st._jev_companion = 0.97
        carry = await core_routing._routing_phase(st, msg, {"companion_joins": 0.97}, "")
        assert isinstance(carry, dict)
        await core_extraction._extraction_phase_body(st, msg, {"companion_joins": 0.97}, "", carry)
        return st

    assert (await turno(False)).detected_group_size == 2
    st = await turno(True)
    assert st.detected_group_size == 3 and (st.detected_group_allocation or {}).get("snorkel") == 1


# --- 5. notas del RAG desde el estado ------------------------------------------------------------------------------

NOTA_SIN_CERT = "minicurso de buceo es UNA experiencia"
NOTA_INACTIVO = "SIGUE SIENDO un buzo certificado"


def _contexto(state: ConversationState) -> str:
    return _build_extra_context(state) or ""


def test_notas_apagado_el_regex_sobre_lo_que_escribe():
    st = _estado(history=[{"role": "user", "content": "mi amigo no es certificado"}])
    assert NOTA_SIN_CERT in _contexto(st)


def test_notas_encendido_salen_del_estado(encender):
    encender("notas_rag_desde_estado")
    st = _estado(history=[{"role": "user", "content": "mi amigo no es certificado"}])
    assert NOTA_SIN_CERT not in _contexto(st)  # sin el dato del extractor, no hay nota
    st.acompanante_sin_certificar = True
    assert NOTA_SIN_CERT in _contexto(st)
    st = _estado(acompanante_certificado_inactivo=True)
    assert NOTA_INACTIVO in _contexto(st)


@pytest.mark.asyncio
async def test_notas_el_extractor_las_guarda(encender, extractor_dice):
    encender("notas_rag_desde_estado")
    extractor_dice({"yo sí, pero mi novia nunca ha buceado": {"otro_sin_certificar": True}})
    st = await _entender("yo sí, pero mi novia nunca ha buceado")
    assert st.acompanante_sin_certificar is True and st.acompanante_certificado_inactivo is False


@pytest.mark.asyncio
async def test_notas_extractor_caido_vuelve_el_regex(encender, extractor_caido):
    encender("notas_rag_desde_estado")
    st = _estado(history=[{"role": "user", "content": "mi amigo no es certificado"}])
    await core._understand(st, "mi amigo no es certificado")
    assert st.extractor_ha_fallado is True
    assert NOTA_SIN_CERT in _contexto(st)


def test_reexporta_lo_de_siempre():
    """El supervisor sigue dando el mismo `_build_extra_context` y `_apply_detected_intent` (sin flags, como hoy)."""
    st = _estado()
    intent = DetectedIntent(duration="single_day")
    supervisor._apply_detected_intent(intent, st, "un día")
    intent = DetectedIntent(duration="multi_day")
    supervisor._apply_detected_intent(intent, st, "varios días")
    assert st.detected_duration == "single_day"  # una sola escritura sin el flag


# --- 7. los campos del paso 6 en una SEGUNDA llamada (flag `paso6_en_llamada_aparte`, decisión de Gadea 19-oct) ----
# Ronda ex9b-4: con dos o más campos del paso 6 el esquema estricto no cabía en Haiku ("compiled grammar is too large")
# y contestaba siempre el respaldo. Con el flag, la llamada de siempre no cambia y los campos nuevos van aparte.

def _cliente_dos(principal: dict, paso6: dict | None, llamadas: list, falla: str | None = None):
    class _C:
        async def create(self, **kw):
            llamadas.append(kw)
            es_paso6 = "dias_de_buceo" in kw["response_format"]["json_schema"]["schema"]["properties"]
            if falla == ("paso6" if es_paso6 else "principal"):
                raise RuntimeError("400 grammar too large")
            msg = type("M", (), {"content": json.dumps(paso6 if es_paso6 else principal)})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()], "usage": None})()

    return type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})()


MENSAJE7 = "somos 2, estaré una semana pero solo quiero bucear un día"
PRINCIPAL7 = {"group_size": {"valor": 2, "cita": "somos 2"}}
PASO6_7 = {"dias_de_buceo": {"valor": 1, "cita": "solo quiero bucear un día"}, "dias_de_estancia": None}


@pytest.fixture
def aparte(monkeypatch, encender):
    encender("duracion_por_extractor")
    monkeypatch.setattr(settings, "paso6_en_llamada_aparte", True)
    monkeypatch.setattr(settings, "extractor_respaldo_modelo", "")


@pytest.mark.asyncio
async def test_aparte_dos_llamadas_y_se_juntan(aparte):
    llamadas: list = []
    out = await ex.extraer_turno(MENSAJE7, history=None, sabido={}, client=_cliente_dos(PRINCIPAL7, PASO6_7, llamadas))
    assert len(llamadas) == 2
    principal, paso6 = sorted(llamadas, key=lambda k: "dias_de_buceo" in _campos_del_esquema(k))
    assert "dias_de_buceo" not in _campos_del_esquema(principal) and "group_size" in _campos_del_esquema(principal)
    assert _campos_del_esquema(paso6) == {"dias_de_buceo", "dias_de_estancia"}
    assert ex.REGLA_DURACION_ES not in principal["messages"][0]["content"]
    assert ex.REGLA_DURACION_ES in paso6["messages"][0]["content"]
    assert out["group_size"] == 2 and out["dias_de_buceo"] == 1


@pytest.mark.asyncio
async def test_aparte_si_falla_la_del_paso6_quedan_los_demas_datos(aparte):
    out = await ex.extraer_turno(MENSAJE7, history=None, sabido={},
                                 client=_cliente_dos(PRINCIPAL7, PASO6_7, [], falla="paso6"))
    assert out is not None and out["group_size"] == 2 and "dias_de_buceo" not in out


@pytest.mark.asyncio
async def test_aparte_si_falla_la_principal_el_extractor_falla(aparte):
    out = await ex.extraer_turno(MENSAJE7, history=None, sabido={},
                                 client=_cliente_dos(PRINCIPAL7, PASO6_7, [], falla="principal"))
    assert out is None


@pytest.mark.asyncio
async def test_aparte_sin_campos_del_paso6_una_sola_llamada(monkeypatch):
    monkeypatch.setattr(settings, "paso6_en_llamada_aparte", True)
    monkeypatch.setattr(settings, "extractor_respaldo_modelo", "")
    llamadas: list = []
    await ex.extraer_turno(MENSAJE7, history=None, sabido={}, client=_cliente_dos(PRINCIPAL7, None, llamadas))
    assert len(llamadas) == 1


@pytest.mark.asyncio
async def test_aparte_la_llamada_lenta_del_paso6_no_bloquea_el_turno(aparte, monkeypatch):
    """Ronda ex9b-6: el respaldo de la llamada del paso 6 tardó 6-8 s y el turno lo esperaba."""
    import asyncio
    import time

    monkeypatch.setattr(ex, "PASO6_ESPERA_MAX", 0.1)

    class _C:
        async def create(self, **kw):
            if "dias_de_buceo" in kw["response_format"]["json_schema"]["schema"]["properties"]:
                await asyncio.sleep(3)
            msg = type("M", (), {"content": json.dumps(PRINCIPAL7)})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()], "usage": None})()

    cliente = type("O", (), {"chat": type("Ch", (), {"completions": _C()})()})()
    t0 = time.perf_counter()
    out = await ex.extraer_turno(MENSAJE7, history=None, sabido={}, client=cliente)
    assert time.perf_counter() - t0 < 1.5
    assert out["group_size"] == 2 and "dias_de_buceo" not in out


# --- 8. quien se suma al grupo: por el punto único del acompañante y con Jev (ex-9b, punto 2 de Gadea) -------------

def test_adds_person_viaja_con_las_senales_del_turno():
    from src.agents import jev_router as j

    assert j.ADDS_PERSON in j._TURN_SIGNALS


@pytest.mark.parametrize("encendido, jev, pregunta", [
    (False, 0.22, False),  # hoy: "viene" casa la lista de palabras y se suma sin preguntar (cuenta dos veces)
    (True, 0.22, True),    # con el flag decide Jev: duda -> se pregunta el total
    (True, 0.9, False),    # Jev seguro de que es nueva -> se suma
    (True, None, False),   # Jev calla -> la lista de siempre
])
def test_quien_se_suma_lo_decide_jev(monkeypatch, encendido, jev, pregunta):
    monkeypatch.setattr(settings, "reparto_al_sumarse_alguien", encendido)
    st = _estado()
    st.detected_activity, st.detected_group_size = "certified_diving", 2
    st._jev_adds_person = jev
    core_extraction._add_or_ask_companion(st, "mi amigo, el que ya te dije que viene, quiere snorkel", "snorkel", 1)
    assert bool(st.pending_companion_in_group) is pregunta
    if not pregunta:
        assert st.detected_group_size == 3
