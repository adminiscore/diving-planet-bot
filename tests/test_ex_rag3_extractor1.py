"""EX-RAG-3 (el juez de grounding pide la cita antes de rechazar) y EX-EXTRACTOR-1 (aclaraciones del extractor), 14-oct."""
import asyncio
import json
from types import SimpleNamespace

from src.agents import juez_segunda_opinion as j2
from src.config import settings

CONTEXTO = ("Pagan en pesos colombianos (COP) los colombianos (vivan donde vivan) y los residentes en Colombia. "
            "El precio es el mismo: solo cambia la moneda. Minicurso: 178 USD online.")


def _cliente(respaldos: list[dict]):
    class _Cliente:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**_):
                    msg = SimpleNamespace(content=json.dumps({"respaldos": respaldos}))
                    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    return _Cliente()


def _con(monkeypatch, respaldos):
    import src.agents.juez_segunda_opinion  # noqa: F401
    monkeypatch.setattr("openai.AsyncOpenAI", lambda **_: _cliente(respaldos))
    monkeypatch.setattr("src.llm_client.trace_openai", lambda c: c)


def test_frase_con_cita_real_pasa(monkeypatch):
    frase = "Si son colombianos, pagan en pesos; el precio es el mismo, solo cambia la moneda."
    _con(monkeypatch, [{"frase": frase, "cita": "El precio es el mismo: solo cambia la moneda"}])
    assert asyncio.run(j2.respaldadas_con_cita([frase], CONTEXTO))


def test_cita_que_no_esta_en_el_contexto_no_pasa(monkeypatch):
    frase = "Los colombianos tienen un 20% de descuento."
    _con(monkeypatch, [{"frase": frase, "cita": "los colombianos tienen descuento"}])
    assert not asyncio.run(j2.respaldadas_con_cita([frase], CONTEXTO))


def test_una_cifra_que_no_esta_en_el_contexto_no_pasa_aunque_la_cita_sea_real(monkeypatch):
    frase = "El minicurso cuesta 150 USD online."
    _con(monkeypatch, [{"frase": frase, "cita": "Minicurso: 178 USD online"}])
    assert not asyncio.run(j2.respaldadas_con_cita([frase], CONTEXTO))


def test_sin_cita_no_pasa(monkeypatch):
    frase = "El minicurso incluye almuerzo de langosta."
    _con(monkeypatch, [{"frase": frase, "cita": None}])
    assert not asyncio.run(j2.respaldadas_con_cita([frase], CONTEXTO))


def test_cifras_y_enlaces():
    assert j2._cifras_y_enlaces("cuesta 1.429.000 COP, mira https://book.divingplanet.org/x.") == {
        "1429000", "https://book.divingplanet.org/x"}


def test_aclaraciones_del_extractor_con_el_flag(monkeypatch):
    from src.agents import extractor_turno as ex

    capturado = {}

    class _Cliente:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kw):
                    capturado["sistema"] = kw["messages"][0]["content"]
                    raise RuntimeError("solo miramos el prompt")

    monkeypatch.setattr(settings, "extractor_aclaraciones", True)
    asyncio.run(ex.extraer_turno("Va quiero comprar sin ir de cartagena", client=_Cliente()))
    assert ex.ACLARACIONES_ES in capturado["sistema"]
    monkeypatch.setattr(settings, "extractor_aclaraciones", False)
    asyncio.run(ex.extraer_turno("Va quiero comprar sin ir de cartagena", client=_Cliente()))
    assert ex.ACLARACIONES_ES not in capturado["sistema"]
