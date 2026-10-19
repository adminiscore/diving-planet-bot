"""Banco del paso 6 de ex-9b (3 llamadas a Jev, config de PRE): las dos señales de Jev que usa `reparto_al_sumarse_alguien`
en tres frases del bloque de reparto de `banco_paso6_extractor.py`: `companion_joins` (el atajo de "reparto completo"
deja pasar la red si es >= 0,8) y `adds_person` (si es < 0,2, Jev está seguro de que la persona ya estaba contada y no se
suma a nadie aunque el extractor amplíe el reparto). El resultado se añade al JSON del banco (`jev_suma`).

    ENV_FILE=<repo>/.env.dev python docs/robustness/regex/estudio-ex9/scripts/banco_paso6_jev_suma.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
os.chdir(REPO)
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")
from scripts.check_deploy import expected_from_compose  # noqa: E402
from src.config import settings  # noqa: E402

for _k, _v in expected_from_compose().items():
    if hasattr(settings, _k):
        setattr(settings, _k, _v)
from src.agents.jev_router import detect_routing_signals_jev_full  # noqa: E402

DATOS = Path(__file__).resolve().parents[1] / "banco-paso6-extractor.json"
HIST = [{"role": "user", "content": "somos 2 buzos certificados, salimos de cartagena"},
        {"role": "assistant", "content": "¡Genial! Son 2 buzos certificados saliendo desde Cartagena. "
                                         "¿Alguno lleva más de 2 años sin bucear?"}]
FRASES = ["mi hermano también viene, él quiere hacer snorkel",       # se suma
          "se apunta mi cuñada, ella prefiere el minicurso",          # se suma
          "mi amigo, el que ya te dije que viene, quiere snorkel"]    # ya contado


async def main() -> None:
    out = {}
    for msg in FRASES:
        senales, extras = await detect_routing_signals_jev_full(msg, lang="es", pending_slot="safety", history=HIST)
        todo = {**(senales if isinstance(senales, dict) else {}), **(extras or {})}
        out[msg] = {"companion_joins": todo.get("companion_joins"), "adds_person": todo.get("adds_person")}
        print(msg, "->", out[msg])
    banco = json.loads(DATOS.read_text(encoding="utf-8"))
    banco["jev_suma"] = out
    banco["llamadas"] = (banco.get("llamadas") or 0) + len(FRASES)
    DATOS.write_text(json.dumps(banco, ensure_ascii=False, indent=1, default=list), encoding="utf-8")


asyncio.run(main())
