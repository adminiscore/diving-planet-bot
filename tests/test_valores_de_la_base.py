"""lat-deuda-u (26-oct): los valores del negocio que se repiten en muchos textos (`data/knowledge_base/valores.json`).

Hay unas 450 horas escritas en las políticas, las fichas y las FAQ, y unas 20 frases con el umbral del refresh en la base
y en el código. No se cambian por marcadores (ver el `_about` de valores.json); este test vigila que no se desincronicen:
si alguien cambia una hora en un sitio y no en los demás, o escribe un horario que no es el oficial, falla aquí con la
lista de los textos que hay que revisar.
"""
import json
import re
from pathlib import Path

from src.domain import valores

RAIZ = Path(__file__).resolve().parents[1]
KB = RAIZ / "data" / "knowledge_base"
_HORA = re.compile(r"\b(\d{1,2}:\d{2})\b")


def _textos_de_la_base():
    for nombre in ("policies.json", "services.json", "curada/faqs.json", "activities.json", "avisos.json"):
        def recorrer(x, donde):
            if isinstance(x, str):
                yield donde, x
            elif isinstance(x, dict):
                for k, v in x.items():
                    yield from recorrer(v, f"{donde}.{k}")
            elif isinstance(x, list):
                for i, v in enumerate(x):
                    yield from recorrer(v, f"{donde}[{i}]")
        yield from recorrer(json.loads((KB / nombre).read_text(encoding="utf-8-sig")), nombre)


def test_toda_hora_de_la_base_es_del_horario_oficial():
    oficiales = valores.horas_oficiales()
    fuera = sorted({(h, donde) for donde, texto in _textos_de_la_base() for h in _HORA.findall(texto)
                    if h not in oficiales})
    assert not fuera, f"horas que no están en valores.json (¿cambió el horario en un sitio y no en los demás?): {fuera[:10]}"


def test_las_horas_clave_estan_en_su_politica():
    politicas = json.loads((KB / "policies.json").read_text(encoding="utf-8-sig"))["policies"]
    assert valores.hora("cierre_reservas") in politicas["booking_system_info"]["es"]
    assert valores.hora("salida_cartagena") in politicas["meeting_point"]["es"]
    horario = politicas["operating_hours"]["es"]
    for clave in ("regreso_desde_la_base", "llegada_a_cartagena", "recogida_islas"):
        assert valores.hora(clave) in horario, clave


# El umbral junto a una palabra de bucear (no «más de 30 años de experiencia», que es la empresa).
_ANOS = [re.compile(r"(?:más de|mas de|more than|over|últimos|last)\s+(\d+)\s+(?:años|years?)[^.\n]{0,40}?"
                    r"(?:buce|inmers|div)", re.I),
         re.compile(r"(?:buce|inmers|div)[^.\n]{0,40}?(?:más de|mas de|more than|over|últimos|last)\s+(\d+)\s+"
                    r"(?:años|years?)", re.I)]


def test_el_umbral_del_refresh_es_el_mismo_en_todas_partes():
    n = valores.anos_sin_bucear_refresh()
    textos = [t for _, t in _textos_de_la_base()]
    textos += [p.read_text(encoding="utf-8") for p in (RAIZ / "src").rglob("*.py")]
    # Los años de la empresa («centro de buceo con más de 30 años») no son el umbral, que es un número pequeño.
    hallados = [m for t in textos for patron in _ANOS for m in patron.findall(t) if int(m) < 10]
    assert len(hallados) >= 10, "el patrón ya no encuentra el umbral: revisarlo"
    distintos = sorted(set(hallados) - {str(n)})
    assert not distintos, f"umbral del refresh distinto de {n} años: {distintos}"


def test_el_codigo_lee_las_horas_de_los_valores():
    from src.flows import cart_render
    from src.flows.state import ConversationState
    from src.prompts import info

    assert f"cierra a las {valores.hora('cierre_reservas')} PM" in info.RAG_BODY_ES
    st = ConversationState(conversation_id="valores", language="es")
    st.mixed_cart = [{"type": "snorkel", "qty": 1, "label": "Snorkel"}]
    assert f"Bodeguita, {valores.hora('salida_cartagena')} a.m." in cart_render.goto_final_summary(st)
