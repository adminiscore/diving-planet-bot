"""u3-5 / paso 1c: el control de correcciones cubre TODOS los campos que filtra Jev.

Con `ANSWER_AND_CONTINUE`, `_route_contradictions` descarta el cambio de un dato guardado si Jev dice
que el mensaje no afirma ese campo, y ese filtro va antes que la señal "ah no / perdón". El banco
(`python -m scripts.sonda_afirma_vs_pregunta corr`) comprueba contra Jev que las correcciones
explícitas pasan; este test, sin red, que el banco no se quede atrás: si alguien añade un campo a
`_AFFIRMS_SIGNAL_FIELDS` sin sus correcciones de control, falla aquí.
"""

import json
from pathlib import Path

from src.agents.conversational_core import _AFFIRMS_SIGNAL_FIELDS, _CORRECTABLE_FIELDS

BANCO = Path(__file__).resolve().parent.parent / "docs" / "robustness" / "u3-4" / "banco-correcciones.json"
MIN_POR_CAMPO = 3


def _casos() -> list[dict]:
    return json.loads(BANCO.read_text(encoding="utf-8"))["casos"]


def _filtrados() -> set[str]:
    """Campos a los que se aplica el filtro de Jev en `_route_contradictions`: con pregunta de Jev Y
    corregibles. Si alguien hace corregible un campo con pregunta de Jev (o al revés), entra aquí solo."""
    return {campo for campo, _ in _AFFIRMS_SIGNAL_FIELDS} & set(_CORRECTABLE_FIELDS)


def test_hay_campos_filtrados():
    assert _filtrados() >= {"location", "is_certified", "group_size", "group_allocation", "is_colombian"}


def test_cada_campo_que_filtra_jev_tiene_correcciones_de_control():
    por_campo: dict[str, int] = {}
    for c in _casos():
        por_campo[c["campo"]] = por_campo.get(c["campo"], 0) + 1
    faltan = {campo: por_campo.get(campo, 0) for campo in _filtrados() if por_campo.get(campo, 0) < MIN_POR_CAMPO}
    assert not faltan, f"campos filtrados por Jev con menos de {MIN_POR_CAMPO} correcciones en el banco: {faltan}"


def test_el_banco_solo_usa_campos_que_existen_y_no_repite_mensajes():
    campos = {campo for campo, _ in _AFFIRMS_SIGNAL_FIELDS}
    casos = _casos()
    assert {c["campo"] for c in casos} <= campos
    mensajes = [c["mensaje"] for c in casos]
    assert len(mensajes) == len(set(mensajes))
