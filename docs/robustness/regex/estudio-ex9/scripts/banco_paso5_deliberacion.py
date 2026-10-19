"""Deliberación entre opciones: la función de hoy (regex de duda + anclas + comparing) frente a "decide Jev"."""
# Con red (Jev por OpenRouter). Desde la raíz: ENV_FILE=<repo>/.env.dev python docs/robustness/regex/estudio-ex9/scripts/banco_paso5_deliberacion.py

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
from src.agents.escalation import detect_routing_signals  # noqa: E402
from src.agents.nucleo.routing import (  # noqa: E402
    _is_deliberation_between_options,
    _mentioned_offerings,
)

CASOS = [
    ("no sé si buceo o snorkel", True), ("somos 2, no sé si buceo o snorkel", True),
    ("mi pareja duda entre buceo y minicurso", True), ("qué diferencia hay entre el minicurso y el snorkel", True),
    ("cuál me recomiendas, el minicurso o el open water", True), ("not sure if diving or snorkeling", True),
    ("which is better, snorkel or the discover scuba?", True), ("estamos entre el minicurso y el snorkel", True),
    ("somos 3 y no tenemos claro si hacer snorkel o el minicurso", True),
    ("2 bucean, mis amigos hacen snorkel y uno hace el minicurso", False), ("quiero buceo y snorkel para los dos", False),
    ("mi esposa hace snorkel y yo buceo", False), ("queremos el minicurso, no el snorkel", False),
    ("reservamos el minicurso para mí y snorkel para los niños", False), ("I'll take the 2 dives and my wife snorkel", False),
    ("mejor el minicurso o el snorkel, cualquiera de los dos nos sirve, reserva el que tenga hueco", False),
]


async def main():
    hoy = jev = 0
    for msg, quiero in CASOS:
        s = await detect_routing_signals(msg, lang="es")
        h = _is_deliberation_between_options(msg, s)
        comp = s.get("comparing_options")
        j = bool(s) and len(_mentioned_offerings(msg)) >= 2 and bool(isinstance(comp, dict) and comp.get("comparing"))
        hoy += h == quiero
        jev += j == quiero
        print(f"{msg[:62]!r:66} quiero={quiero!s:5} hoy={h!s:5} jev={j!s:5} ofertas={len(_mentioned_offerings(msg))}"
              f"{'' if h == quiero else '  <-- hoy MAL'}{'' if j == quiero else '  <-- jev MAL'}")
    print(f"hoy {hoy}/{len(CASOS)} · solo Jev {jev}/{len(CASOS)}")


asyncio.run(main())
