"""Banco del paso 5 (núcleo): ¿trae una pregunta? y ¿corrige un dato? — Jev (config de PRE) frente al regex."""
# Con red (Jev y el enrutador de respaldo por OpenRouter, ~0,0001 $ por llamada). Desde la raíz del repo:
#   ENV_FILE=<repo>/.env.dev python docs/robustness/regex/estudio-ex9/scripts/banco_paso5_nucleo.py

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
from src.agents import supervisor  # noqa: E402
from src.agents.jev_router import detect_routing_signals_jev_full  # noqa: E402

HIST = [{"role": "user", "content": "hola, somos 2 y queremos bucear"},
        {"role": "assistant", "content": "¡Genial! 2 personas para bucear. ¿Ya son buzos certificados?"}]
PREGUNTA = [  # (mensaje, ¿trae pregunta?)
    ("qué incluye el plan de 2 inmersiones", True), ("cuánto cuesta el minicurso para 2", True),
    ("perfecto, como pago", True), ("dónde es el punto de encuentro", True), ("what does the package include", True),
    ("me dices el horario de salida porfa", True), ("quisiera saber si incluye almuerzo", True),
    ("hay un niño de 5 años", False), ("cuando lleguemos te aviso", False), ("como te dije, somos 4", False),
    ("donde nos quedamos es en Bocagrande", False), ("que bien, gracias", False),
    ("somos 3 y queremos bucear el sábado", False), ("how nice, we are 4 adults", False),
]
CORRIGE = [  # (mensaje, ¿corrige un dato ya dado?)
    ("en realidad somos 5", True), ("me equivoqué, no somos 2, somos 3", True), ("esperate, somos 4 al final", True),
    ("actually we are 3, not 2", True), ("perdón, al final viene uno más, somos 3", True),
    ("perdón, ¿cuánto cuesta?", False), ("perdón la demora, ¿qué horarios tienen?", False),
    ("sorry for the late reply, what time do you leave?", False),
    ("realmente queremos ir el sábado", False), ("en realidad me interesa mucho bucear", False),
]


async def main():
    res = {"pregunta": [0, 0], "corrige": [0, 0]}
    for nombre, banco, clave, regex in (
        ("pregunta", PREGUNTA, "asks_question", lambda m: supervisor._looks_like_info_question(m) or "?" in m),
        ("corrige", CORRIGE, "corrects", lambda m: bool(supervisor._CORRECTION_CUE_RE.search(m))),
    ):
        print(f"== {nombre}")
        for msg, quiero in banco:
            jev = []
            for _ in range(2):
                _, extras = await detect_routing_signals_jev_full(msg, lang="es", history=HIST)
                jev.append(extras.get(clave))
            jev_final = [("?" in msg or bool(v)) if nombre == "pregunta" else bool(v) for v in jev]
            ok_j = all(v == quiero for v in jev_final)
            ok_r = regex(msg) == quiero
            res[nombre][0] += ok_r
            res[nombre][1] += ok_j
            marca = "" if ok_j else "  <-- Jev MAL"
            print(f"  {msg!r:52} quiero={quiero!s:5} regex={regex(msg)!s:5} jev={jev}{marca}")
        print(f"  {nombre}: regex {res[nombre][0]}/{len(banco)} · Jev {res[nombre][1]}/{len(banco)}")


asyncio.run(main())
