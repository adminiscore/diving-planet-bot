"""CAL-D (16-oct): la consulta de búsqueda de un mensaje referido tiene que NOMBRAR el asunto.

Medido con `scripts/sonda_senales.py` dentro de PRE: el reescritor de consultas corre, pero arregla la gramática y
deja la elipsis.

| Mensaje del cliente | Reescritura de hoy | Lo que la búsqueda trae | Lo que faltaba |
|---|---|---|---|
| "And how much is per a day" (cal-42) | "How much is the price per day?" | la política del segundo día y los paquetes de varios días; la ficha del plan de 1 día no entra en el top-8 | un día de buceo, desde Cartagena, buzo certificado |
| "Vale, en concepto le coloco otros?" (cal-14) | "¿Le coloco otros en concepto?" | descuentos, formulario del seguro, hoteles | al pagar la reserva por el enlace |

El arreglo (flag `consulta_con_lo_sabido`) le da al reescritor lo que YA SABEMOS del cliente en campos estructurados
del estado (los mismos hechos que eligen los avisos de CAL-A5) y una regla para todas las preguntas: una consulta con
elipsis o pronombre no es autosuficiente. No es una lista de frases ni un caso.
"""

import pytest

from src.agents import query_rewriter as qr
from src.config import settings

_HECHOS = {"actividades": {"certified_diving"}, "origen": "cartagena", "nacionalidad": "extranjero"}


def test_lo_sabido_sale_de_campos_estructurados():
    es = qr.lo_sabido(_HECHOS, "es")
    assert "certified_diving" in es and "sale desde Cartagena" in es and "extranjero" in es
    en = qr.lo_sabido(_HECHOS, "en")
    assert "departs from Cartagena" in en


def test_sin_hechos_no_se_dice_nada():
    assert qr.lo_sabido(None, "es") == ""
    assert qr.lo_sabido({}, "es") == ""
    assert qr.lo_sabido({"actividades": set(), "origen": None, "nacionalidad": None}, "es") == ""


def test_lo_sabido_no_inventa_el_origen():
    """Solo los dos orígenes del catálogo; cualquier otro valor no se traduce a una frase."""
    assert qr.lo_sabido({"origen": "island"}, "es") == "ya está en las Islas del Rosario"
    assert qr.lo_sabido({"origen": "marte"}, "es") == ""


def _fake_openai(respuesta, llamadas):
    class _Completions:
        async def create(self, **kwargs):
            llamadas.append(kwargs)
            msg = type("M", (), {"content": respuesta})()
            return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()

    class _OpenAI:
        def __init__(self, api_key=None):
            self.chat = type("Chat", (), {"completions": _Completions()})()

    return _OpenAI


_HISTORIAL = [
    {"role": "user", "content": "Hi, I plan on being in Cartagena and do scuba diving on April 21 and 22"},
    {"role": "assistant", "content": "Great! Are you a certified diver?"},
    {"role": "user", "content": "PADI open water, advanced open water and deep diver certs"},
]


@pytest.mark.asyncio
async def test_con_el_flag_el_reescritor_recibe_lo_sabido_y_la_regla(monkeypatch):
    llamadas: list[dict] = []
    monkeypatch.setattr(qr, "AsyncOpenAI", _fake_openai("How much is one day of diving from Cartagena?", llamadas))
    monkeypatch.setattr(settings, "consulta_con_lo_sabido", True)
    salida = await qr.condense_query("And how much is per a day", history=_HISTORIAL, lang="en", hechos=_HECHOS)
    assert salida == "How much is one day of diving from Cartagena?"
    sistema = llamadas[0]["messages"][0]["content"]
    usuario = llamadas[0]["messages"][1]["content"]
    assert "must NAME what the question is about" in sistema
    assert "is NOT self-contained" in sistema
    assert "What we already know about the customer" in usuario
    assert "departs from Cartagena" in usuario


@pytest.mark.asyncio
async def test_sin_el_flag_la_llamada_es_la_de_siempre(monkeypatch):
    llamadas: list[dict] = []
    monkeypatch.setattr(qr, "AsyncOpenAI", _fake_openai("How much is the price per day?", llamadas))
    monkeypatch.setattr(settings, "consulta_con_lo_sabido", False)
    await qr.condense_query("And how much is per a day", history=_HISTORIAL, lang="en", hechos=_HECHOS)
    sistema = llamadas[0]["messages"][0]["content"]
    usuario = llamadas[0]["messages"][1]["content"]
    assert "must NAME what the question is about" not in sistema
    assert "already know about the customer" not in usuario


@pytest.mark.asyncio
async def test_un_mensaje_largo_no_se_reescribe(monkeypatch):
    """La regla de hoy: con 8 palabras o más, el mensaje se busca tal cual (no se toca)."""
    llamadas: list[dict] = []
    monkeypatch.setattr(qr, "AsyncOpenAI", _fake_openai("x", llamadas))
    monkeypatch.setattr(settings, "consulta_con_lo_sabido", True)
    largo = "quiero saber cuanto cuesta el plan de dos inmersiones saliendo desde Cartagena"
    assert await qr.condense_query(largo, history=_HISTORIAL, lang="es", hechos=_HECHOS) == largo
    assert not llamadas


@pytest.mark.asyncio
async def test_si_el_reescritor_falla_se_busca_el_mensaje_tal_cual(monkeypatch):
    class _Rompe:
        def __init__(self, api_key=None):
            class _C:
                async def create(self, **kwargs):
                    raise RuntimeError("sin red")
            self.chat = type("Chat", (), {"completions": _C()})()

    monkeypatch.setattr(qr, "AsyncOpenAI", _Rompe)
    monkeypatch.setattr(settings, "consulta_con_lo_sabido", True)
    assert await qr.condense_query("y por dia?", history=_HISTORIAL, lang="es", hechos=_HECHOS) == "y por dia?"
