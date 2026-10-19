"""Calibra la pregunta de Jev "¿pide el precio de nuestras actividades?" frente a _PIDE_PRECIO_RE y no _PRECIO_AJENO_RE."""
# Con red (Jev). Desde la raíz: ENV_FILE=<repo>/.env.dev python docs/robustness/regex/estudio-ex9/scripts/banco_paso5_pide_precio.py "<instrucciones>"

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
os.chdir(REPO)
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")
from scripts.check_deploy import expected_from_compose  # noqa: E402
from src.config import settings  # noqa: E402

for k, v in expected_from_compose().items():
    if hasattr(settings, k):
        setattr(settings, k, v)
from src.agents import jev_router as j  # noqa: E402
from src.agents.conversational_core import _PIDE_PRECIO_RE, _PRECIO_AJENO_RE  # noqa: E402

Q = {"type": "noul", "instructions": sys.argv[1]}
CASOS = [
    ("¿cuánto cuesta el minicurso?", True), ("precio del open water", True), ("how much for 2 dives?", True),
    ("¿y en pesos?", True), ("y para 3 personas cuánto sería?", True),
    ("cuánto me sale el plan de 2 inmersiones? me quedo en el hotel Caribe", True),
    ("what's the rate for snorkeling per person", True), ("valor del paquete de 5 buceos", True),
    ("hola, quisiera cotizar buceo para 4 personas", True),
    ("¿cuánto cuesta la noche en el hotel de la isla?", False), ("¿aceptan dólares?", False),
    ("¿cuánto dura el minicurso?", False), ("¿cuántas inmersiones son?", False),
    ("¿cuánto cuesta un taxi al muelle?", False), ("¿se puede pagar con tarjeta?", False),
    ("perfecto, ¿cómo reservo?", False),
]


async def main():
    hoy = jev = 0
    for msg, quiero in CASOS:
        rg = bool(_PIDE_PRECIO_RE.search(msg)) and not _PRECIO_AJENO_RE.search(msg)
        ps = []
        for _ in range(2):
            r = await j._http().post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                                     json={"model": settings.jev_model, "state": j._estado_para_jev(msg, None),
                                           "questions": {"q": Q}}, timeout=15)
            ps.append(round(r.json()["answers"]["q"].get("noul", 0.0), 2))
        ok = all((p >= 0.7) == quiero for p in ps)
        hoy += rg == quiero
        jev += ok
        print(f"{msg[:64]!r:68} quiero={quiero!s:5} regex={rg!s:5} jev={ps}{'' if ok else '  <-- MAL'}")
    print(f"regex {hoy}/{len(CASOS)} · Jev {jev}/{len(CASOS)}")


asyncio.run(main())
