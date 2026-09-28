"""Banco de calibración de la pregunta de Jev `companion_joins` (u3-6, paso 7).

El filtro solo SALTA el LLM de señales cuando Jev está seguro de que el mensaje no mete a otra persona
(p < COMPANION_NONE_MAX). Lo que importa: ningún positivo por debajo del umbral (se perdería un
acompañante); los negativos por debajo son el ahorro. Positivos: los ejemplos del propio detector y
de sus tests; negativos: turnos normales del golden y el "Si cuantos días son?" que el LLM leyó como
acompañante en la ronda B del paso 5.

    python -m scripts.sonda_acompanante
"""
import asyncio
import os
import sys

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx  # noqa: E402

from scripts.sonda_afirma_vs_pregunta import _preguntar  # noqa: E402
from src.agents import jev_router  # noqa: E402

POSITIVOS = [
    "hay un amigo que quiere hacer snorkel",
    "viene mi primo a bucear",
    "2 y uno hace snorkel",
    "también mi novia",
    "mi acompañante quiere hacer buceo pero no es certificado",
    "mi parce también quiere bucear",
    "my wife wants to try diving too",
    "mi amigo bucea y mi otra amiga hace snorkel",
    "ocho personas hacen snorkel y yo buceo",
    "mis amigos hacen snorkel",
    "Mi madre también quiere venir pero no puede hacer deporte",
    "quiero regalarle a mi esposo una experiencia de buceo",
    "somos 3, dos bucean y uno hace el minicurso",
    "my friend isn't certified",
]
NEGATIVOS = [
    "Si cuantos días son?",
    "gracias",
    "desde cartagena",
    "no soy colombiano",
    "no, buceé hace poco",
    "¿Cuánto cuesta el curso Open Water?",
    "mejor snorkel",
    "en realidad quiero el minicurso",
    "my family always talks about diving here",
    "El curso que te he pedido cuánto tiempo dura ?",
    "We are leaving tomorrow before noon",
    "perfecto, como pago",
    "Exactamente entre el 20 y 22 de julio",
    "sí, claro",
]
N = 2


async def main() -> None:
    q = jev_router._COMPANION_JOINS_Q["instructions"]
    async with httpx.AsyncClient() as cli:
        async def score(m):
            vals = [await _preguntar(cli, m, q) for _ in range(N)]
            return max(vals)  # conservador: el peor caso de las repeticiones
        pos = await asyncio.gather(*(score(m) for m in POSITIVOS))
        neg = await asyncio.gather(*(score(m) for m in NEGATIVOS))
    for label, msgs, vals in (("POS", POSITIVOS, pos), ("NEG", NEGATIVOS, neg)):
        for m, v in sorted(zip(msgs, vals), key=lambda x: x[1]):
            print(f"{label} {v:.2f}  {m[:90]}")
    t = jev_router.COMPANION_NONE_MAX
    print(f"\nse salta el LLM por debajo de {t}: positivos perdidos {sum(v < t for v in pos)}/{len(pos)}, "
          f"negativos ahorrados {sum(v < t for v in neg)}/{len(neg)}")


if __name__ == "__main__":
    asyncio.run(main())
