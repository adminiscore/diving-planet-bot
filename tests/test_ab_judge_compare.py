"""G-9 (14-oct): el comparador A/B separa el ruido del juez de las regresiones reales (sin llamar a la API)."""
from scripts import ab_judge_compare as ab


def _res(*criterios):
    return {"dialogues": [{"id": "d", "criteria": [{"id": c, "verdict": v, "evidencia_bot": e} for c, v, e in criterios]}]}


def test_cumple_no_aplica_no_es_regresion_ni_mejora():
    cambios = ab.comparar(_res(("x", "cumple", None), ("y", "no_aplica", None)),
                          _res(("x", "no_aplica", None), ("y", "cumple", None)))
    assert not cambios["regresiones"] and not cambios["mejoras"]
    assert len(cambios["no_comparables"]) == 2


def test_regresion_y_mejora():
    cambios = ab.comparar(_res(("x", "cumple", None), ("y", "no_cumple", "z")),
                          _res(("x", "no_cumple", "z"), ("y", "cumple", None)))
    assert [k for k, *_ in cambios["regresiones"]] == [("d", "x")]
    assert [k for k, *_ in cambios["mejoras"]] == [("d", "y")]


def test_veredicto_mayoritario():
    assert ab._veredicto_mayoritario(["no_cumple", "cumple", "cumple"]) == "cumple"
    assert ab._veredicto_mayoritario(["cumple", "revisar", "no_cumple"]) == "no_cumple"  # revisar no aprueba
    assert ab._veredicto_mayoritario(["no_cumple", "cumple"]) == "no_cumple"  # empate: el original


def test_misma_cita_en_la_otra_ronda():
    otra = [{"turn": 1, "reply": "Hola, el paquete de 3 inmersiones sale a las 8"}]
    assert ab._misma_cita_en_la_otra({"evidencia_bot": "el paquete de 3 inmersiones"}, otra)
    assert not ab._misma_cita_en_la_otra({"evidencia_bot": "otra cosa"}, otra)
    assert not ab._misma_cita_en_la_otra({"evidencia_bot": None}, otra)
