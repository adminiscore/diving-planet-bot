"""CALN-0 (27-oct): las comprobaciones por código de una ronda guardada (scripts/caln0_comprobaciones.py). Sin red."""
from scripts import caln0_comprobaciones as c


def _conv(*pares):
    return [{"turn": i + 1, "msg": m, "reply": r} for i, (m, r) in enumerate(pares)]


def test_repregunta_del_origen_tras_darlo():
    fallos = c.comprobar(_conv(
        ("quiero bucear, voy solo", "¡Perfecto! ¿Desde dónde saldrías?"),
        ("Desde cartagena porfi", "¡Genial! ¿Desde dónde saldrías? Puedes salir desde Cartagena…"),
    ))
    assert [f["dato"] for f in fallos["repregunta"]] == ["origen"]


def test_la_pregunta_pendiente_que_vuelve_sin_respuesta_va_aparte():
    fallos = c.comprobar(_conv(
        ("quiero bucear", "¿Desde dónde saldrías?"),
        ("¿qué hoteles recomiendan?", "San Pedro de Majagua y Cocoliso. ¿Desde dónde saldrías?"),
    ))
    assert not fallos["repregunta"] and [f["dato"] for f in fallos["repite_sin_respuesta"]] == ["origen"]


def test_afirmar_el_origen_no_es_preguntarlo():
    fallos = c.comprobar(_conv(
        ("quiero bucear", "¿Desde dónde saldrías?"),
        ("cartagena", "¡Perfecto, sales desde Cartagena! ¿Eres buzo certificado?"),
    ))
    assert not fallos["repregunta"] and not fallos["repite_sin_respuesta"]


def test_grupo_distinto_del_dicho():
    tarjeta = "🤿 *Minicurso*\n💰 2 × 655.000 COP p.p. = *1.310.000 COP*"
    assert c.comprobar(_conv(("somos 3, colombianos", tarjeta)))["grupo"][0]["tarjeta"] == 2
    assert not c.comprobar(_conv(("somos una pareja de colombianos", tarjeta)))["grupo"]
    assert not c.comprobar(_conv(("somos 6: 2 bucean certificados, 2 hacen minicurso y 2 snorkel", tarjeta)))["grupo"]


def test_moneda_que_no_toca():
    usd = "💰 2 × 178 USD p.p. = *356 USD* (reservando online)"
    assert c.comprobar(_conv(("somos colombianos", usd)))["moneda"]
    assert not c.comprobar(_conv(("ninguno colombiano, somos extranjeros", usd)))["moneda"]


def test_un_solo_origen_sin_saberlo():
    solo = "La salida desde Cartagena cuesta *630.000 COP por persona*."
    los_dos = "Desde Cartagena, 630.000 COP; si ya estás en las islas, 445.000 COP."
    assert c.comprobar(_conv(("¿cuánto cuesta bucear?", solo)))["origen"]
    assert not c.comprobar(_conv(("¿cuánto cuesta bucear?", los_dos)))["origen"]
    assert not c.comprobar(_conv(("estoy en Cartagena, ¿cuánto cuesta?", solo)))["origen"]
