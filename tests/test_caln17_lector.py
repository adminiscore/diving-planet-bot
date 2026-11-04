"""CALN-17 (4-nov, plan de Álvaro, #2911): la lectura del grupo en el lector, no en el prompt del extractor (allí cada frase
movía otras lecturas). El regalo: quien escribe y dice que no va no cuenta. El bebé: quien no tiene edad para ninguna
actividad no cuenta, no paga ni es «sin elegir» (`policies.babies_onboard`)."""
import pytest

from src.agents import lector_grupo as lg


def _p(quien, cantidad, cita, actividad=None, edades=None, certificado=None):
    return {"quien": quien, "cantidad": cantidad, "cita": cita, "actividad": actividad, "edades": edades or [],
            "certificado": certificado}


def _lectura(mensaje, *personas, total=None):
    return lg.validar({"total_dicho": total, "personas": list(personas)}, mensaje)


def test_la_edad_minima_sale_del_registro():
    assert lg.edad_para_alguna_actividad() == 6


def test_el_regalo_quien_escribe_no_cuenta_y_el_total_es_uno():
    """g46: «the mini course for my sister as a gift… I won't be joining» daba minicurso ×2 y total 2."""
    msg = "I'd like to book the mini course for my sister as a gift. I'm Dutch and I won't be joining."
    lectura = _lectura(msg, _p("cliente", 0, "I won't be joining"),
                       _p("sister", 1, "the mini course for my sister", actividad="minicourse"))
    assert lectura["escritor_no_va"] and [p["quien"] for p in lectura["personas"]] == ["sister"]
    # El extractor da la actividad a quien escribe: con la regla de g19 volvía a contarlo.
    datos, _ = lg.completar({"activity": "minicourse"}, lectura)
    assert datos["group_size"] == 1 and datos["group_allocation"] == {"minicourse": 1}


def test_el_no_va_sin_cita_comprobada_no_vale():
    lectura = _lectura("Quiero el minicurso para mi hermana.", _p("cliente", 0, "yo no voy"),
                       _p("hermana", 1, "para mi hermana", actividad="minicourse"))
    assert not lectura["escritor_no_va"]


def test_quien_escribe_habla_solo_de_otro_sigue_contando():
    """g19: «I'd like to do the mini course. My husband is certified…»: el regalo no cambia esto."""
    msg = "my husband is certified, he'd like to dive"
    lectura = _lectura(msg, _p("husband", 1, msg, actividad="certified_diving", certificado=True))
    datos, _ = lg.completar({"activity": "minicourse"}, lectura)
    assert datos["group_size"] == 2 and datos["group_allocation"] == {"minicourse": 1, "certified_diving": 1}


@pytest.mark.parametrize("extractor", [
    {"group_size": 3, "group_allocation": {"snorkel": 2, "companion": 1}},  # lo cuenta como acompañante
    {"group_size": 3},
    {},
])
def test_el_bebe_no_cuenta_aunque_el_extractor_lo_cuente(extractor):
    """g38/g39: la pareja con el bebé salía {snorkel: 2, companion: 1}: la tarjeta cobraba al bebé."""
    msg = "Somos una pareja y llevamos a nuestro bebé de 2 años; nosotros dos queremos hacer snorkel"
    lectura = _lectura(msg, _p("cliente", 2, "nosotros dos queremos hacer snorkel", actividad="snorkel"),
                       _p("bebé", 1, "nuestro bebé de 2 años", edades=[2]))
    assert lectura["bebes"] == 1 and len(lectura["personas"]) == 1
    datos, _ = lg.completar({**extractor, "edades": [2]}, lectura)
    assert datos["group_size"] == 2 and datos["group_allocation"] == {"snorkel": 2}
    assert datos["edades"] == [2]  # la edad se sabe: el bebé no desaparece de lo que se le contesta


def test_de_dos_ninos_solo_cuenta_el_que_tiene_edad():
    """g30: «hijos de 6 y 3»: total 3, y el de 6 sin elegir."""
    msg = "soy buzo certificada y quiero bucear. Mi marido no se mete al agua y vienen nuestros hijos de 6 y 3 años"
    lectura = _lectura(msg, _p("cliente", 1, "soy buzo certificada y quiero bucear", certificado=True),
                       _p("marido", 1, "Mi marido no se mete al agua", actividad="companion"),
                       _p("hijos", 2, "nuestros hijos de 6 y 3 años", edades=[6, 3]))
    assert lectura["bebes"] == 1 and lectura["personas"][-1]["cantidad"] == 1 and lectura["personas"][-1]["edades"] == [6]
    datos, _ = lg.completar({"group_size": 4, "activity": "certified_diving", "edades": [6, 3]}, lectura)
    assert datos["group_size"] == 3
    assert datos["group_allocation"] == {"certified_diving": 1, "companion": 1, "undecided": 1}


@pytest.mark.parametrize("total, entradas, queda", [
    (4, [("cliente", 2, "mi pareja, yo"), ("niños", 2, "los niños de 9 y 4", [9, 4])], 3),  # «Somos 4» los contaba
    (2, [("cliente", 2, "Somos 2"), ("bebé", 1, "nuestro bebé de 2 años", [2])], 2),  # «Somos 2» no lo contaba
])
def test_el_total_dicho_solo_baja_si_los_contaba(total, entradas, queda):
    msg = "Somos 4: mi pareja, yo y los niños de 9 y 4. Somos 2 y llevamos a nuestro bebé de 2 años"
    lectura = _lectura(msg, *[_p(e[0], e[1], e[2], edades=e[3] if len(e) > 3 else None) for e in entradas], total=total)
    assert lectura["total_dicho"] == queda


def test_el_bebe_en_otro_turno_no_cambia_el_grupo_sabido():
    msg = "También viene nuestro bebé de 2 años"
    lectura = _lectura(msg, _p("bebé", 1, "nuestro bebé de 2 años", edades=[2]))
    datos, cambios = lg.completar({"group_size": 3, "group_allocation": {"snorkel": 2, "companion": 1}, "edades": [2]},
                                  lectura, total_sabido=2)
    assert datos["group_size"] is None and datos["group_allocation"] is None and cambios


def test_con_una_edad_sin_actividad_hace_falta_la_lectura():
    cuadra = {"group_size": 3, "group_allocation": {"snorkel": 2, "companion": 1}}
    assert lg.por_completar({**cuadra, "edades": [2]})
    assert not lg.por_completar({**cuadra, "edades": [9]})


def test_sin_bebe_ni_regalo_lo_del_extractor_no_se_toca():
    msg = "Somos 3 y hacemos snorkel; mi hijo tiene 9"
    lectura = _lectura(msg, _p("cliente", 2, "Somos 3 y hacemos snorkel", actividad="snorkel"),
                       _p("hijo", 1, "mi hijo tiene 9", edades=[9]))
    datos, _ = lg.completar({"group_size": 3, "group_allocation": {"snorkel": 3}, "edades": [9]}, lectura)
    assert datos["group_size"] == 3 and datos["group_allocation"] == {"snorkel": 3}


def test_si_el_reparto_del_extractor_cuadra_con_quienes_cuentan_se_queda():
    """g37: el extractor ya da al marido buzo y a la acompañante; el lector dejaba al marido sin actividad."""
    msg = "Mi marido es buzo certificado y quiere bucear; yo voy en la lancha con nuestra hija de 1 año, sin hacer nada"
    lectura = _lectura(msg, _p("marido", 1, "Mi marido es buzo certificado", certificado=True),
                       _p("cliente", 1, "yo voy en la lancha", actividad="companion"),
                       _p("hija", 1, "nuestra hija de 1 año", edades=[1]))
    reparto = {"certified_diving": 1, "companion": 1}
    datos, _ = lg.completar({"group_allocation": reparto, "edades": [1]}, lectura)
    assert datos["group_size"] == 2 and datos["group_allocation"] == reparto


def test_el_regalo_sin_actividad_en_la_entrada_lleva_la_del_mensaje():
    """g46 y g47: el lector nombra a quienes van sin actividad; la del extractor es de ellos, no de quien escribe."""
    msg = "Quiero reservarles el snorkel a mis padres por su aniversario; yo vivo en España y no voy."
    lectura = _lectura(msg, _p("cliente", 0, "yo vivo en España y no voy"), _p("padres", 2, "a mis padres"))
    datos, _ = lg.completar({"activity": "snorkel"}, lectura)
    assert datos["group_size"] == 2 and datos["group_allocation"] == {"snorkel": 2}
