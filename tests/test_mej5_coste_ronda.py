"""mej-5 (21-oct): el coste de una ronda con sus métricas de tokens (`scripts/turn_metrics.coste`).

OpenRouter trae su coste en cada llamada ("usd"); OpenAI se calcula con la tabla de `scripts/precios_llm` (precios del
21-oct). Con la ronda core instrumentada de Gadea (uso-openai) sale OpenAI ~0,05 $ y OpenRouter ~0,31 $ por 100 turnos.
"""

import json

import pytest

from scripts import precios_llm, turn_metrics


def _turnos(*llamadas_por_turno, conv="1"):
    lineas = [turn_metrics.TAG + " " + json.dumps({"conv": conv, "start": f"2026-10-21T14:0{i}:00Z",
                                                   "llamadas": ll}) for i, ll in enumerate(llamadas_por_turno)]
    return turn_metrics.parse_lines(lineas)


def test_el_precio_de_openai_descuenta_la_cache():
    # 1.000 de entrada (400 en caché) y 200 de salida con gpt-5.4-nano: 600×0,20 + 400×0,02 + 200×1,25, por millón.
    assert precios_llm.coste_openai("gpt-5.4-nano", 1000, 400, 200) == pytest.approx((120 + 8 + 250) / 1e6)
    assert precios_llm.coste_openai("modelo-que-no-existe", 1000) is None


def test_coste_por_proveedor_pieza_y_conversacion():
    turnos = _turnos(
        [{"p": "rag_escritor", "m": "gpt-6-luna", "u": {"in": 10000, "ca": 0, "out": 1000}},
         {"p": "revisor", "m": "deepseek/deepseek-v4.1-flash", "u": {"in": 9000, "out": 300, "usd": 0.002}},
         {"p": "jev", "m": "typesafe/jev-1.13", "u": {"in": 6000, "out": 800, "usd": 0.00026}}],
        [{"p": "embedding", "m": "text-embedding-3-small", "u": {"in": 50}},
         {"p": "extractor", "m": "anthropic/claude-haiku-5.5", "e": 403}],  # un fallo no suma
    )
    c = turn_metrics.coste(turnos)
    luna = 10000 * 0.10 / 1e6 + 1000 * 0.50 / 1e6
    assert c["openai_usd"] == pytest.approx(luna + 50 * 0.02 / 1e6, abs=1e-4)
    assert c["openrouter_usd"] == pytest.approx(0.00226, abs=1e-4)
    assert set(c["por_pieza"]) == {"rag_escritor", "revisor", "jev", "embedding"}
    assert c["por_conversacion"]["n"] == 1
    assert c["usd_por_100_turnos"] == pytest.approx(c["usd"] * 50, abs=1e-4)


def test_un_modelo_sin_precio_se_cuenta_aparte():
    c = turn_metrics.coste(_turnos([{"p": "x", "m": "gpt-9-nuevo", "u": {"in": 100, "out": 10}}]))
    assert c["sin_precio"] == {"gpt-9-nuevo": 1} and c["usd"] == 0


def test_metricas_de_antes_sin_tokens_dan_coste_cero():
    c = turn_metrics.coste(_turnos([{"p": "rag_escritor", "m": "gpt-6-luna", "t": 0.1, "s": 2.0}]))
    assert c["usd"] == 0 and c["por_pieza"] == {}
