"""Simplificar, V2: la puerta del código sobre V1 (docs/robustness/caln/diseno-puerta-v2.md). Banco sin IA."""
import hashlib
import json

import pytest

from scripts import simple_v1 as v1
from scripts import simple_v2 as v2

URL_2_CTG = "https://book.divingplanet.org/book/salidas-de-buceo/1?language=es"


def _ent(**campos) -> dict:
    return {**v2.ENTENDIDO_VACIO, **campos}


# --- V1 no cambia; V2 solo cambia el esquema ------------------------------------------------------------------------------------

def test_v1_queda_como_se_midio():
    assert "«mixta»" not in v1.INSTRUCCIONES and '"actividad": texto o null' in v1.INSTRUCCIONES
    assert "mixta" in v2.INSTRUCCIONES_V2 and "reparto" in v2.INSTRUCCIONES_V2
    antes, despues = v1.INSTRUCCIONES.split(v2._INICIO)[0], v2.INSTRUCCIONES_V2.split(v2._INICIO)[0]
    assert antes == despues and v2.INSTRUCCIONES_V2.endswith(v1.INSTRUCCIONES.split(v2._FIN, 1)[1])


# --- La decisión ------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("campos", "forma"), [
    ({}, v2.ORIGEN_PRIMERO),
    ({"nacionalidad": "colombiana"}, v2.ORIGEN_PRIMERO),  # P5: primero el origen
    ({"origen": "islas"}, v2.HOTEL_PRIMERO),
    ({"origen": "islas", "plan": "4_dives_2_days"}, v2.HOTEL_PRIMERO),  # el hotel antes que el plan sin enlace
    ({"origen": "cartagena", "plan": "2_dives_1_day"}, v2.ENLACE),
    ({"origen": "cartagena", "nacionalidad": "mixta", "plan": "2_dives_1_day"}, v2.ENLACE),  # grupo mixto: USD con el enlace
    ({"origen": "cartagena", "nacionalidad": "residente"}, v2.ASESOR),
    ({"origen": "islas", "hotel": "Villa Marea"}, v2.ASESOR),  # recogida por confirmar
    ({"origen": "islas", "hotel": "Hotel Cocoliso", "plan": "2_dives_1_day"}, v2.ENLACE),
    ({"origen": "cartagena", "reparto": {"snorkel": 6}}, v2.ASESOR),  # grupo de 5 o más
    ({"origen": "cartagena", "reparto": {"padi_open_water": 6}}, v2.ENLACE),  # los cursos PADI no tienen descuento de grupo
    ({"origen": "cartagena", "reparto": {"certified_diving": 2, "companion": 1}}, v2.ASESOR),  # una parte sin enlace
    ({"origen": "cartagena", "plan": "4_dives_2_days"}, v2.ASESOR),  # el plan no tiene enlace
    ({"origen": "cartagena", "plan": "2_dives_1_day", "equipo_propio": True}, v2.ASESOR),
    ({"origen": "cartagena", "plan": "2_dives_1_day", "a_nombre_de_otro": True}, v2.ASESOR),
    ({"ya_reservo": True}, v2.POSVENTA),
])
def test_decision(campos, forma):
    assert v2.decision(_ent(**campos))[0] == forma


def test_el_plan_de_las_islas_y_un_plan_que_no_es_del_catalogo():
    assert v2.servicio_del_plan(_ent(origen="islas", plan="2_dives_1_day")) == "2_dives_1_day_already_on_island"
    assert v2.servicio_del_plan(_ent(origen="cartagena", plan="paquete_4_buceos_diurnos")) is None  # no cuenta como sin enlace
    assert v2.enlace_que_toca(_ent(origen="cartagena", plan="2_dives_1_day", idioma="en")).endswith("language=en")


# --- Los importes --------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("texto", "esperado"), [
    ("Cuesta 178 USD por persona.", [(178.0, "USD")]),
    ("USD 178 online", [(178.0, "USD")]),  # con la moneda delante (V1, 53 veces)
    ("Normal 197,29 USD", [(197.29, "USD")]),
    ("630.000 COP o COP 700.000", [(630000.0, "COP"), (700000.0, "COP")]),
    ("448 mil pesos", [(448000.0, "COP")]),
    ("$178 o $630.000", [(178.0, "USD"), (630000.0, "COP")]),
    (f"Reserva: {URL_2_CTG}", []),  # el «1» del enlace no es un importe
])
def test_importes(texto, esperado):
    assert v2.importes(texto) == esperado


def _fallos(ent, texto, pasar=None, pregunta=None, veces=None, p1b=False):
    return v2.comprobar(ent, pasar, pregunta, texto, veces or {}, p1b)


def test_c2_solo_precios_del_catalogo():
    ctg = _ent(origen="cartagena", nacionalidad="extranjera", plan="2_dives_1_day")
    assert "C2" not in _fallos(ctg, "Cuesta 178 USD (normal 197,29 USD), 10 % menos online.")["fallos"]
    for malo in ("Con el descuento queda en 160,20 USD.", "Son 356 USD en total.", "USD 999", "Un 15 % menos."):
        assert "C2" in _fallos(ctg, malo)["fallos"], malo
    assert "C2" in _fallos(ctg, "Desde las islas son 124,20 USD.")["fallos"]  # el del otro origen, con el origen sabido
    assert "C2" not in _fallos(_ent(nacionalidad="extranjera", plan="2_dives_1_day"), "178 USD o 124,20 USD")["fallos"]
    assert "C2" in _fallos(_ent(origen="cartagena", nacionalidad="colombiana", plan="2_dives_1_day"), "178 USD")["fallos"]


# --- El enlace -----------------------------------------------------------------------------------------------------------------

def test_c3_ningun_enlace_sin_origen_ni_al_asesor():
    assert "C3" in _fallos(_ent(plan="2_dives_1_day"), f"Reserva: {URL_2_CTG}")["fallos"]  # sin origen
    assert "C3" in _fallos(_ent(origen="cartagena", reparto={"snorkel": 6}), f"Reserva: {URL_2_CTG}")["fallos"]
    assert "C3" not in _fallos(_ent(origen="cartagena", plan="2_dives_1_day"), f"Reserva: {URL_2_CTG}")["fallos"]


def test_c3_el_codigo_pone_el_enlace_si_quiere_reservar():
    hecho = _fallos(_ent(origen="cartagena", plan="2_dives_1_day", quiere_reservar=True), "Perfecto, te cuento.")
    assert hecho["enlace_que_falta"] == URL_2_CTG
    assert _fallos(_ent(origen="cartagena", plan="2_dives_1_day"), "Te cuento.")["enlace_que_falta"] is None  # no lo pidió


# --- El pase -------------------------------------------------------------------------------------------------------------------

def test_c1_el_grupo_pasa_cuando_quiere_reservar_y_no_antes():
    grupo = {"origen": "cartagena", "reparto": {"snorkel": 6}}
    pase = {"si": True, "motivo": "reservar_con_asesor"}
    assert "C1" in _fallos(_ent(**grupo), "Te paso con un asesor.", pase)["fallos"]  # P3: aún no quiere reservar
    assert "C1" not in _fallos(_ent(**grupo, quiere_reservar=True), "Te paso con un asesor.", pase)["fallos"]
    assert _fallos(_ent(**grupo, quiere_reservar=True), "Genial.")["pase_que_falta"]  # lo marca el código


def test_c1_lo_que_contesta_la_base_no_pasa():
    pase = {"si": True, "motivo": "la_base_no_lo_tiene", "tema": "precio del hotel"}
    assert "C1" in _fallos(_ent(origen="cartagena"), "Te paso.", pase)["fallos"]
    pase = {"si": True, "motivo": "la_base_no_lo_tiene", "tema": "guardar maletas"}  # P-a (#3766)
    assert "C1" not in _fallos(_ent(origen="cartagena"), "Te paso.", pase)["fallos"]


def test_c1_sin_hotel_no_pasa_aunque_quiera_reservar():
    pase = {"si": True, "motivo": "reservar_con_asesor"}
    assert "C1" in _fallos(_ent(origen="islas", plan="4_dives_2_days", quiere_reservar=True), "Te paso.", pase)["fallos"]


# --- La pregunta ---------------------------------------------------------------------------------------------------------------

def test_c4_la_pregunta_solo_si_la_reserva_la_necesita():
    assert "C4" in _fallos(_ent(origen="cartagena"), "¿Algo más?", pregunta={"tema": "otra"})["fallos"]
    assert "C4" not in _fallos(_ent(), "¿Desde dónde sales?", pregunta={"tema": "origen"})["fallos"]  # origen-y-precio
    assert "C4" in _fallos(_ent(origen="cartagena"), "¿Cuántos son?", pregunta={"tema": "personas"})["fallos"]  # no quiere reservar
    assert "C4" not in _fallos(_ent(origen="cartagena", quiere_reservar=True), "¿Cuántos son?",
                               pregunta={"tema": "personas"})["fallos"]
    assert "C4" in _fallos(_ent(), "¿Uno? ¿Dos?", pregunta={"tema": "origen"})["fallos"]  # una como mucho


def test_c4_nunca_una_tercera_vez_salvo_el_origen_al_reservar():
    veces = {"origen": 2}
    assert "C4" in _fallos(_ent(), "¿Desde dónde sales?", pregunta={"tema": "origen"}, veces=veces)["fallos"]
    assert "C4" not in _fallos(_ent(quiere_reservar=True), "Para darte el enlace, ¿desde dónde sales?",
                               pregunta={"tema": "origen"}, veces=veces)["fallos"]  # P1b, una vez
    assert "C4" in _fallos(_ent(quiere_reservar=True), "¿Desde dónde sales?", pregunta={"tema": "origen"}, veces=veces,
                           p1b=True)["fallos"]


# --- La plantilla ----------------------------------------------------------------------------------------------------------------

def test_la_plantilla_pone_el_precio_y_la_entrega_del_codigo():
    texto = v2.plantilla(_ent(origen="cartagena", nacionalidad="extranjera", plan="2_dives_1_day"), "es")
    assert "178 USD" in texto and URL_2_CTG in texto
    assert "Cartagena o ya estás" in v2.plantilla(_ent(plan="2_dives_1_day"), "es")


# --- Lo que enseñó la prueba de verdad (visto-6898 y visto-6940) ----------------------------------------------------------------

def test_c2_acepta_el_precio_redondeado_como_lo_escribe_el_bot():
    islas = _ent(origen="islas", hotel="Hotel San Pedro de Majagua", nacionalidad="extranjera", plan="4_dives_2_days_already_on_island")
    assert "C2" not in _fallos(islas, "The 4-dive package costs 204 USD (regular 227 USD).")["fallos"]  # 204,3 en el catálogo


def test_c2_con_varias_actividades_valen_los_precios_de_cada_una():
    grupo = _ent(origen="cartagena", nacionalidad="colombiana", plan="2_dives_1_day",
                 reparto={"certified_diving": 3, "minicourse": 2, "snorkel": 2})
    assert "C2" not in _fallos(grupo, "El minicurso cuesta 655.000 COP y el snorkel 448.000 COP; el buceo, 630.000 COP.")["fallos"]
    assert "C2" in _fallos(grupo, "El minicurso cuesta 183 USD.")["fallos"]  # a colombianos, en pesos (moneda)


def test_la_plantilla_del_grupo_da_cada_precio_y_el_motivo_en_su_idioma():
    grupo = _ent(origen="cartagena", nacionalidad="colombiana", reparto={"certified_diving": 3, "minicourse": 2, "snorkel": 2})
    texto = v2.plantilla(grupo, "es")
    assert "655.000 COP" in texto and "448.000 COP" in texto and "asesor" in texto
    assert "630.000 COP" not in texto  # el buceo sin plan dicho tiene varios precios: no se adivina (revisión nº 11)
    assert "payment in pesos" in v2.plantilla({**grupo, "idioma": "en"}, "en")


def test_c2_el_buzo_certificado_puede_oir_todos_los_planes_de_buceo():
    islas = _ent(origen="islas", hotel="Hotel San Pedro de Majagua", nacionalidad="extranjera", reparto={"certified_diving": 1})
    assert "C2" not in _fallos(islas, "Hay paquetes de 4 inmersiones (204 USD) y de 5 (319 USD).")["fallos"]


def test_el_esquema_de_v2_dice_cuando_pasar():
    assert "solo cuando el cliente ya quiere reservar o pagar" in v2.INSTRUCCIONES_V2


# --- Tras la revisión del código (paso 5): V2m, la puerta de lo exacto (#3773, #3774) --------------------------------------------



def test_v1_no_cambia_huella_fijada():
    assert hashlib.sha256(v1.INSTRUCCIONES.encode()).hexdigest()[:16] == "9936ca42e9c5ccf9"


@pytest.mark.parametrize(("texto", "esperado"), [
    ("178 dólares", [(178.0, "USD")]),
    ("COP 630 mil", [(630000.0, "COP")]),
    ("$630 mil pesos", [(630000.0, "COP")]),
    ("1'154.000 COP", [(1154000.0, "COP")]),
    ("630.000,00 COP", [(630000.0, "COP")]),
    ("Brindamos con 2 Copas de vino", []),
])
def test_importes_formatos_de_la_revision(texto, esperado):
    assert v2.importes(texto) == esperado


def test_c2_los_precios_de_pricing_que_no_son_de_un_servicio_y_el_20():
    ctg = _ent(origen="cartagena", nacionalidad="extranjera")
    assert "C2" not in _fallos(ctg, "El acompañante, 80,44 USD; la nocturna, 84,6 USD; con online y grupo, un 20 %.")["fallos"]


def test_c3_el_enlace_en_ingles_vale():
    en = _ent(origen="cartagena", plan="2_dives_1_day", idioma="en")
    assert "C3" not in _fallos(en, f"Book here: {URL_2_CTG}")["fallos"]  # la base solo tiene los de language=es


@pytest.mark.parametrize(("campos", "forma"), [
    ({"origen": "cartagena", "personas": 6, "plan": "open_water"}, v2.ENLACE),  # un curso PADI no tiene descuento de grupo
    ({"origen": "islas", "hotel": "todavía no sé"}, v2.HOTEL_PRIMERO),
    ({"origen": "islas", "hotel": "Isla Grande"}, v2.HOTEL_PRIMERO),
    ({"origen": "cartagena", "reparto": {"bubble_makers": 2}}, v2.ASESOR),
])
def test_decision_tras_la_revision(campos, forma):
    assert v2.decision(_ent(**campos))[0] == forma


# El bucle de un cliente, con las salidas de Luna simuladas (sin llamar a nadie).
def _luna(*salidas):
    cola = list(salidas)

    def _salida(clave, mensajes):
        datos = cola.pop(0)
        if isinstance(datos, Exception):
            raise datos
        return v2._limpio(datos), json.dumps(datos, ensure_ascii=False), {"s": 1.0, "u": {"in": 1, "ca": 0, "out": 1}}, None
    return _salida


def _salida_de(texto, pasar=None, pregunta=None, **ent):
    return {"entendido": {**ent}, "pasar": pasar or {"si": False}, "pregunta": pregunta, "texto": texto}


def _correr(monkeypatch, turnos, salidas, puerta=True):
    monkeypatch.setattr(v2, "_salida", _luna(*salidas))
    return v2.cliente("x", "BASE", {"id": "prueba", "turnos": turnos}, None, puerta)


_COL = {"origen": "cartagena", "nacionalidad": "colombiana", "plan": "2_dives_1_day", "quiere_reservar": True}


def test_un_importe_malo_se_rehace_y_la_plantilla_conserva_el_pase_bueno(monkeypatch):
    pase = {"si": True, "motivo": "reservar_con_asesor"}
    [fila] = _correr(monkeypatch, ["Quiero reservar"], [_salida_de("Total 1.260.000 COP.", pase, **_COL),
                                                        _salida_de("Son 1.260.000 COP en total.", pase, **_COL)])
    assert fila["estado"]["puerta"]["rehecho"] and fila["estado"]["puerta"]["plantilla"]
    assert "630.000 COP" in fila["reply"] and fila["estado"]["pasar"]["si"]  # el pase era bueno: se queda
    assert len(fila["metricas"][0]["llamadas"]) == 2


def test_el_pase_y_el_enlace_del_codigo_no_se_repiten(monkeypatch):
    grupo = {"origen": "cartagena", "nacionalidad": "extranjera", "reparto": {"snorkel": 6}, "quiere_reservar": True}
    filas = _correr(monkeypatch, ["Reservamos", "Gracias", "Ok"], [_salida_de("Genial.", **grupo)] * 3)
    assert [("Te paso" in f["reply"]) for f in filas] == [True, False, False]
    ctg = {"origen": "cartagena", "nacionalidad": "extranjera", "plan": "2_dives_1_day", "quiere_reservar": True}
    filas = _correr(monkeypatch, ["¿El link?", "Gracias", "Ok"], [_salida_de("Claro.", **ctg)] * 3)
    assert [f["reply"].count("book.divingplanet.org") for f in filas] == [1, 0, 0]


def test_el_pase_y_la_pregunta_solo_se_cuentan_en_v2m(monkeypatch):
    grupo = {"origen": "cartagena", "nacionalidad": "extranjera", "reparto": {"snorkel": 6}}
    [fila] = _correr(monkeypatch, ["Hola"], [_salida_de("Te paso con un asesor.", {"si": True, "motivo": "reservar_con_asesor"},
                                                       {"tema": "otra"}, **grupo)])
    assert {"C1"} <= set(fila["estado"]["puerta"]["fallos_1"]) and not fila["estado"]["puerta"].get("rehecho")


def test_v1r_no_rehace_ni_pone_nada(monkeypatch):
    [fila] = _correr(monkeypatch, ["Hola"], [_salida_de("Son 999 USD en total.", **_COL)], puerta=False)
    assert fila["reply"] == "Son 999 USD en total." and not fila["estado"]["puerta"].get("rehecho")
    assert fila["metricas"][0]["turn_type"] == "simple-v1r"


def test_si_la_segunda_llamada_falla_se_queda_la_primera(monkeypatch):
    [fila] = _correr(monkeypatch, ["Hola"], [_salida_de("Son 999 USD.", **_COL), RuntimeError("HTTP 500")])
    assert "rehacer_fallo" in fila["estado"]["puerta"] and not fila["reply"].startswith("ERROR")


def test_una_salida_rara_no_tumba_la_tirada(monkeypatch):
    raro = {"entendido": {"personas": "6", "reparto": ["snorkel"], "hotel": ["x"]}, "pasar": True, "pregunta": "origen",
            "texto": "Hola"}
    [fila] = _correr(monkeypatch, ["Hola"], [raro])
    assert fila["reply"] and fila["metricas"][0]["llm_errores"] == 0
