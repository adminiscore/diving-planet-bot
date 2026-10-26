"""ex-2 (fase EX, 12-oct): escalón 0 del escalado por tema sensible con el banco `docs/robustness/escalado/banco-ex2.json`.

Para cada frase mira lo que decide hoy el enrutador sobre "pasar a un asesor por tema sensible" y lo que decidiría con
`escalado_solo_emergencias` (la lista de palabras clave se queda con las emergencias y las incidencias en tiempo real;
lo médico, el tiempo y las quejas los decide Jev). Una frase escala si la lista la caza (salvo DIVE TO HEAL, como en `router.classify_route`) o si las señales del enrutador traen
`sensitive_topic` o `needs_staff`. Las señales salen de `escalation.detect_routing_signals` con Jev encendido (como en
PRE; si Jev duda, el router LLM), una llamada por frase y pasada.

    ENV_FILE=.env.dev python -m scripts.banco_escalado [--pasadas 2]

Cuenta PERDIDAS (debía escalar y no) y FALSAS (escala sin deber). Jev va por OpenRouter; el router LLM de respaldo,
por OpenAI (céntimos).
"""
import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")

from src.agents import escalation  # noqa: E402

BANCO = Path(__file__).resolve().parent.parent / "docs" / "robustness" / "escalado" / "banco-ex2.json"
_INGLES = re.compile(r"\b(the|i|i'm|we|you|is|my|it|can|there)\b", re.IGNORECASE)


def _idioma(texto: str) -> str:
    return "en" if len(_INGLES.findall(texto)) >= 2 else "es"


def _por_lista(texto: str, lang: str, variante: str) -> str | None:
    """La categoría que caza la lista de palabras clave (la entera de antes, o la de ex-2), o None. mej-1d: ex-2 ya
    no lleva interruptor; la lista entera se reproduce sustituyendo un momento `_active_rules`."""
    activas = escalation._active_rules
    if variante == "hoy":
        escalation._active_rules = lambda: escalation.SENSITIVE_RULES
    try:
        found = escalation.detect_sensitive_escalation(texto, lang)
    finally:
        escalation._active_rules = activas
    return found[0] if found else None


def _escala(lista: str | None, senales: dict) -> str | None:
    """Por qué pasa a un asesor (como `router.classify_route`), o None."""
    if lista and not senales.get("adaptive_diving_topic"):
        return f"lista:{lista}"
    if senales.get("sensitive_topic"):
        return f"jev:{senales['sensitive_topic']}"
    if senales.get("needs_staff") is True:
        return "jev:needs_staff"
    return None


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pasadas", type=int, default=1)
    ap.add_argument("--out", default=None, help="guarda el detalle en este JSON")
    a = ap.parse_args()
    frases = json.loads(BANCO.read_text(encoding="utf-8"))["frases"]
    filas = []
    for pasada in range(a.pasadas):
        for f in frases:
            lang = _idioma(f["texto"])
            senales = await escalation.detect_routing_signals(f["texto"], lang=lang)
            fila = {"id": f["id"], "pasada": pasada, "esperado": f["esperado"],
                    "senales": {k: senales.get(k) for k in ("sensitive_topic", "needs_staff", "adaptive_diving_topic",
                                                            "wants_human") if senales.get(k)}}
            for v in ("hoy", "ex2"):
                fila[v] = _escala(_por_lista(f["texto"], lang, v), senales)
            filas.append(fila)
    print(f"{len(frases)} frases ({sum(f['esperado'] == 'escalar' for f in frases)} deben escalar) x {a.pasadas} pasadas")
    for v, nombre in (("hoy", "hoy (lista entera)"), ("ex2", "ex-2 (emergencias e incidencias por lista; el resto, Jev)")):
        perdidas = [x for x in filas if x["esperado"] == "escalar" and not x[v]]
        falsas = [x for x in filas if x["esperado"] == "no" and x[v]]
        print(f"\n== {nombre}: perdidas {len(perdidas)} · falsas {len(falsas)}")
        for x in perdidas:
            print(f"   PERDIDA p{x['pasada']} {x['id']}  señales={x['senales']}")
        for x in falsas:
            print(f"   FALSA   p{x['pasada']} {x['id']}  por {x[v]}")
    if a.out:
        Path(a.out).write_text(json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n(detalle en {a.out})")


if __name__ == "__main__":
    asyncio.run(main())
