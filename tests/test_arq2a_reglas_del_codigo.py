"""arq-2a (22-oct): fuera del prompt del RAG las reglas que el código ya pone en el contexto que el RAG lee siempre
(catálogo y políticas). Desde lat-9 paso 1 (26-oct) los recortes están escritos en `RAG_BODY_*` (antes se aplicaban al
vuelo con `RAG_SIN_REGLAS_DEL_CODIGO_*`). Se fija: (1) lo que se quitó no vuelve; (2) el dato que lo sustituye sigue en
el contexto; (3) las reglas que solo vigila un guarda se quedan."""
import pytest

from src.agents.rag_agent import build_system_prompt
from src.flows.catalog import catalog_facts, policies_facts
from src.prompts import info

# Lo que se quitó del cuerpo: la viñeta del tono que repite brand_tone, las dos de la moneda por nacionalidad (la regla
# va UNA vez, en las reglas del escritor, desde decisiones.json) y la vieja de «no confirmes cupos».
QUITADAS = {
    "es": ("Habla como un cartagenero amigable", "Usa el contexto de extra_context para adaptar la moneda",
           "Evita mezclar muchas monedas", "NUNCA confirmes disponibilidad o cupo"),
    "en": ("Use the extra_context to adapt currency", "Avoid mixing several currencies",
           "NEVER confirm availability or open slots"),
}
# Lo que dice el contexto en lugar de lo quitado (catálogo + políticas).
EN_EL_CONTEXTO = {
    "es": ("Moneda:", "25 de diciembre", "suspend"),
    "en": ("Currency:", "December 25", "weather"),
}
# Reglas con un guarda en rag_agent (importes, enlaces, teléfono, datos personales): se quedan. Las dos de descuentos
# también: el catálogo solo dice "no calcules totales" y sin la regla el guarda de importes tiraba el precio por persona
# con el descuento (test_rag_safety, 17-jul).
SE_QUEDAN = {
    "es": ("NUNCA des un número de teléfono", "No inventes ni reconstruyas links", "Nunca inventes precios",
           "NUNCA gestiones la reserva recogiendo datos", "nombra las opciones con su precio", "equipo parcial",
           "NUNCA calcules ni afirmes el precio final"),
    "en": ("NEVER give a phone or WhatsApp number", "Do not invent or reconstruct payment", "Never invent prices",
           "NEVER process a booking by collecting data", "name the options with their price", "partial gear",
           "NEVER calculate or state the final discounted price"),
}


@pytest.mark.parametrize("lang", ["es", "en"])
def test_lo_quitado_no_vuelve_y_el_dato_sigue_en_el_contexto(lang):
    prompt = build_system_prompt(lang)
    for quitada in QUITADAS[lang]:
        assert quitada not in prompt, quitada
    contexto = catalog_facts(lang) + policies_facts(lang)
    for dato in EN_EL_CONTEXTO[lang]:
        assert dato in contexto, dato
    for regla in SE_QUEDAN[lang]:
        assert regla in prompt, regla
    corta = info.RAG_DISPONIBILIDAD_CORTA_ES if lang == "es" else info.RAG_DISPONIBILIDAD_CORTA_EN
    assert corta in prompt
