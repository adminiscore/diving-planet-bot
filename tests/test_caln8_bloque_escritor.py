"""CALN-8 (3) (28-oct): las políticas enteras ya no van en el prompt del escritor del RAG (le llegan en los hechos las que
el caso exige, CALN-7); el juez de grounding sí las ve, para respaldar una política citada. El catálogo y los enlaces
se quedan en los dos: sin el catálogo se perdían los precios del plan sin decidir (banco-precios 29 → 25/36)."""
import pytest

_POLITICAS = {"es": "Políticas de Diving Planet:", "en": "Diving Planet policies:"}
_ENLACES = {"es": "LINKS DE RESERVA ONLINE", "en": "ONLINE BOOKING LINKS"}


class _Completions:
    def __init__(self):
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        msg = type("M", (), {"content": "El snorkel incluye lancha, equipo y almuerzo."})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()],
                              "usage": type("U", (), {"total_tokens": 10})()})()


class _Client:
    def __init__(self):
        self.chat = type("Chat", (), {"completions": _Completions()})()

    def __call__(self, *args, **kwargs):
        return self


async def _escritor_y_juez(monkeypatch, lang: str) -> tuple[str, str]:
    from src.agents import rag_agent

    client = _Client()
    monkeypatch.setattr(rag_agent, "AsyncOpenAI", client)
    vistos: list[str] = []

    async def _sin_docs(*args, **kwargs):
        return []

    async def _juez(answer, context, lang="es"):
        vistos.append(context)
        return True, "ok"

    monkeypatch.setattr(rag_agent, "search_knowledge_base", _sin_docs)
    monkeypatch.setattr(rag_agent, "_verify_grounding", _juez)

    await rag_agent.rag_answer("¿qué incluye el snorkel?" if lang == "es" else "what does snorkeling include?", lang=lang,
                               extra_context=f"Idioma: {lang}.")
    return client.chat.completions.calls[0]["messages"][0]["content"], vistos[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("lang", ["es", "en"])
async def test_las_politicas_las_ve_el_juez_y_no_el_escritor(monkeypatch, lang):
    from src.flows.catalog import catalog_facts

    sistema, juez = await _escritor_y_juez(monkeypatch, lang)
    assert _POLITICAS[lang] not in sistema
    assert _POLITICAS[lang] in juez
    primera_del_catalogo = catalog_facts(lang).splitlines()[0]
    assert primera_del_catalogo in sistema and _ENLACES[lang] in sistema
