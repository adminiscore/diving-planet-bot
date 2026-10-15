"""ex-7 (fase EX, 13-oct): escalón 0 del GRUPO con el banco `docs/robustness/regex/banco-ex7/banco.json`.

Cada frase pasa por la parte del turno de producción que ENTIENDE (`run_extraction_eval._turno_ex0`, modo `actual`:
señales del enrutador con Jev encendido como en PRE, lector de respuestas cortas y `_understand`), arrancando con lo
que la conversación ya sabía (`sabido`) y la última pregunta del bot; se puntúa como el banco ex0 (`puntuar_ex0`).
Dos modos: `hoy` (EXTRACCION_LLM_GRUPO apagado) y `ex7` (encendido).

    ENV_FILE=.env.dev python -m scripts.banco_grupo [--pasadas 2] [--out fichero.json]

Gasta céntimos: enrutador (Jev por OpenRouter; si duda, gpt-4o-mini), redes LLM del camino viejo y el extractor.
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

from scripts.run_extraction_eval import CAMPOS_EX0, _turno_ex0, puntuar_ex0  # noqa: E402
from src.agents.intent_detector import IntentDetector  # noqa: E402
from src.config import settings  # noqa: E402

BANCO = Path(__file__).resolve().parent.parent / "docs" / "robustness" / "regex" / "banco-ex7" / "banco.json"
_INGLES = re.compile(r"\b(the|i|i'm|we|we're|you|is|my|our|of|and|will|are|us)\b", re.IGNORECASE)


def _caso(c: dict) -> dict:
    lang = "en" if len(_INGLES.findall(c["texto"])) >= 2 else "es"
    history = [{"role": "assistant", "content": c["pregunta"]}] if c.get("pregunta") else []
    return {"id": c["id"], "message": c["texto"], "history": history, "slot": c.get("slot"), "lang": lang,
            "sabido": c.get("sabido") or {}, "grupo": "ex7"}


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pasadas", type=int, default=1)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    settings.jev_router_enabled = True
    casos = json.loads(BANCO.read_text(encoding="utf-8"))["casos"]
    detector = IntentDetector()
    filas = []
    for pasada in range(a.pasadas):
        # ex-9 (15-oct): el camino viejo ("hoy") ya no existe: el grupo lo decide siempre el extractor.
        for modo in ("ex7",):
            for c in casos:
                caso = _caso(c)
                try:
                    producido = await _turno_ex0(caso, "actual", detector)
                except Exception as exc:  # noqa: BLE001 — se apunta y se sigue
                    producido = {"ERROR": repr(exc)}
                r = puntuar_ex0({k: v for k, v in producido.items() if k in CAMPOS_EX0}, c["esperado"], caso["sabido"])
                filas.append({"id": c["id"], "modo": modo, "pasada": pasada, "texto": c["texto"],
                              "esperado": c["esperado"], "producido": producido, **r})
    for modo in ("ex7",):
        fs = [x for x in filas if x["modo"] == modo]
        por = {f: {t: sum(f in x[t] for x in fs) for t in ("acierto", "equivocado", "perdido", "inventado")}
               for f in ("group_size", "group_allocation", "activity", "is_certified")}
        mal = [x for x in fs if any(x[t] for t in ("equivocado", "perdido", "inventado"))]
        print(f"\n== {modo}: {len(fs)} turnos · casos con algún fallo {len(mal)}")
        for f, v in por.items():
            print(f"   {f:18s} acierto {v['acierto']:3d} · equivocado {v['equivocado']:2d} · perdido {v['perdido']:2d}"
                  f" · inventado {v['inventado']:2d}")
        for x in mal:
            fallos = {t: x[t] for t in ("equivocado", "perdido", "inventado") if x[t]}
            print(f"   MAL p{x['pasada']} {x['id']} {fallos} | {x['texto'][:60]!r} esperado={x['esperado']} "
                  f"producido={ {k: v for k, v in x['producido'].items() if k in CAMPOS_EX0 or k == 'ERROR'} }")
    if a.out:
        Path(a.out).write_text(json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n(detalle en {a.out})")


if __name__ == "__main__":
    asyncio.run(main())
