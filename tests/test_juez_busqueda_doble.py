"""1-oct (análisis del juez, `docs/robustness/juez/README.md`): búsqueda con la pregunta original Y la reescrita
(flag `rag_busqueda_doble`), y la regla de moneda del catálogo sin ambigüedad.

La reescritura metía el servicio de la conversación y se comía el tema: "great, how do i pay" -> "How do I pay for
the Fun Dives?" traía fichas de Fun Dives y ninguna de las 6 piezas de pago que trae la pregunta tal cual. Y la frase
"NO existe precio ni descuento especial para colombianos" hacía que el juez rechazara el precio COP correcto.
"""
from unittest.mock import AsyncMock

import pytest

from src.agents import rag_agent
from src.config import settings
from src.flows.catalog import catalog_facts


def _docs(prefijo, n=8):
    return [{"id": f"{prefijo}{i}", "content": f"{prefijo} {i}", "metadata": {"source": "faqs"}} for i in range(n)]


def test_fusionar_mantiene_la_reescrita_intacta_y_anade_lo_que_solo_trae_la_original():
    reescrita, original = _docs("fun_dives"), _docs("pago")
    out = rag_agent.fusionar_busquedas(reescrita, original)
    assert out[:8] == reescrita  # nunca se pierde lo de hoy
    assert [d["id"] for d in out[8:]] == ["pago0", "pago1", "pago2", "pago3"]  # hasta 4, en su orden


def test_fusionar_no_repite_lo_que_ya_trae_la_reescrita():
    comun = {"id": "faq:114", "content": "pagos", "metadata": {}}
    out = rag_agent.fusionar_busquedas(_docs("a")[:7] + [comun], [comun] + _docs("b")[:7])
    assert len({d["id"] for d in out}) == len(out) == 12
    assert out[8]["id"] == "b0"


@pytest.mark.asyncio
async def test_rag_answer_busca_tambien_con_la_pregunta_original_solo_con_el_flag(monkeypatch):
    buscar = AsyncMock(return_value=[])
    monkeypatch.setattr(rag_agent, "search_knowledge_base", buscar)
    monkeypatch.setattr(rag_agent, "condense_query", AsyncMock(return_value="How do I pay for the Fun Dives?"))
    for flag, consultas in ((False, {"How do I pay for the Fun Dives?"}),
                            (True, {"How do I pay for the Fun Dives?", "great, how do i pay"})):
        monkeypatch.setattr(settings, "rag_busqueda_doble", flag)
        buscar.reset_mock()
        await rag_agent.rag_answer("great, how do i pay", lang="en", verify_grounding=False)
        assert {c.args[0] for c in buscar.await_args_list} == consultas


@pytest.mark.asyncio
async def test_si_la_reescritura_no_cambia_nada_se_busca_una_vez(monkeypatch):
    buscar = AsyncMock(return_value=[])
    monkeypatch.setattr(rag_agent, "search_knowledge_base", buscar)
    monkeypatch.setattr(rag_agent, "condense_query", AsyncMock(side_effect=lambda q, **k: q))
    monkeypatch.setattr(settings, "rag_busqueda_doble", True)
    await rag_agent.rag_answer("what is included in the snorkel tour?", lang="en", verify_grounding=False)
    assert buscar.await_count == 1


@pytest.mark.parametrize("lang, dice", [("es", "el precio en COP de cada plan es el que pagan los colombianos"),
                                       ("en", "each plan's COP price is what Colombians pay")])
def test_la_regla_de_moneda_dice_que_el_precio_cop_es_el_de_los_colombianos(lang, dice):
    """El juez leía "NO existe precio especial para colombianos" como "no hay precio para colombianos". Primera
    redacción ("decir 'para colombianos cuesta X COP' es correcto"): el bot dejaba de corregir el mito (1/4)."""
    hechos = catalog_facts(lang)
    assert dice in hechos
    assert "NO existe precio ni descuento especial" not in hechos and "There is NO special price" not in hechos


@pytest.mark.parametrize("lang, islas", [("es", "Acompañante - ya en las islas"), ("en", "Companion - already on the islands")])
def test_el_acompanante_sale_en_los_dos_origenes_con_lo_que_incluye(lang, islas):
    hechos = catalog_facts(lang)
    assert islas in hechos
    assert ("almuerzo NO incluido" if lang == "es" else "lunch NOT included") in hechos


@pytest.mark.parametrize("lang", ["es", "en"])
def test_el_juez_ve_la_regla_de_moneda_como_hecho_y_el_resto_igual(lang):
    """El que redacta necesita la instrucción (corregir el mito); el juez, el hecho: con la instrucción rechazaba el
    precio COP correcto "para colombianos" (14 de 54 rechazos)."""
    from src.flows.catalog import para_el_juez

    hechos = catalog_facts(lang)
    juez = para_el_juez(hechos, lang)
    assert ("es correcta" if lang == "es" else "is correct") in juez
    assert ("díselo claramente" if lang == "es" else "say so clearly") not in juez
    assert ("díselo claramente" if lang == "es" else "say so clearly") in hechos
    distintas = [a for a, b in zip(hechos.splitlines(), juez.splitlines(), strict=True) if a != b]
    assert len(distintas) == 1 and distintas[0].startswith(("Moneda:", "Currency:"))


@pytest.mark.asyncio
async def test_con_la_reescrita_igual_la_marca_de_origen_no_dispara_la_busqueda_doble(monkeypatch):
    """rag_piezas (1-oct): con la reescrita idéntica, la única diferencia era la marca de origen del resumen, y la
    búsqueda sin ella sacaba del top-8 una pieza buena (grupos mixtos)."""
    buscar = AsyncMock(return_value=[])
    monkeypatch.setattr(rag_agent, "search_knowledge_base", buscar)
    monkeypatch.setattr(rag_agent, "condense_query", AsyncMock(side_effect=lambda q, **k: q))
    monkeypatch.setattr(settings, "rag_busqueda_doble", True)
    await rag_agent.rag_answer("¿podemos ir juntos el mismo día?", lang="es", verify_grounding=False,
                               extra_context="El cliente saldra desde Cartagena.")
    assert buscar.await_count == 1


@pytest.mark.asyncio
async def test_la_original_lleva_la_misma_marca_de_origen(monkeypatch):
    buscar = AsyncMock(return_value=[])
    monkeypatch.setattr(rag_agent, "search_knowledge_base", buscar)
    monkeypatch.setattr(rag_agent, "condense_query", AsyncMock(return_value="¿Cómo pago los Fun Dives?"))
    monkeypatch.setattr(settings, "rag_busqueda_doble", True)
    await rag_agent.rag_answer("listo, como pago", lang="es", verify_grounding=False,
                               extra_context="El cliente saldra desde Cartagena.")
    consultas = {c.args[0] for c in buscar.await_args_list}
    assert any(q.startswith("listo, como pago") and q.endswith("[origen_cliente]=desde Cartagena") for q in consultas)
