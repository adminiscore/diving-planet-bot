"""Calibra dos preguntas nuevas de Jev (ex-9b paso 5): "¿eres un bot?" y "cambia el idioma de la conversación"."""
# Con red (Jev por OpenRouter, ~0,0001 $ por llamada). Desde la raíz del repo:
#   ENV_FILE=<repo>/.env.dev python docs/robustness/regex/estudio-ex9/scripts/banco_paso5_ia_idioma.py

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
from src.agents.nucleo.setup import _SWITCH_TO_EN_RE, _SWITCH_TO_ES_RE  # noqa: E402
from src.agents.rutas.deflection import _AI_IDENTITY_RE  # noqa: E402

PREGUNTA_IA = {"type": "noul", "instructions": (
    "The customer asks whether they are chatting with a bot, an AI, a machine or a real person, or asks which AI, "
    "model, technology or company is behind this chat assistant. It is FALSE for questions about diving equipment "
    "(models or brands of regulators, computers, wetsuits, boats), about the instructors or staff, and about anything "
    "that is not this chat assistant itself.")}
PREGUNTA_IDIOMA = {"type": "choice", "instructions": (
    "Does the customer ask to change the language in which THIS chat conversation is written?"), "criteria": {
    "english": "They ask us to write to them in English from now on, or say they do not understand Spanish.",
    "spanish": "They ask us to write to them in Spanish from now on, or say they do not understand English.",
    "none": "They do not ask to change the language of this chat: they ask in which language a course, class, guide, "
            "instructor or material is given, mention a language for any other reason, or just write in a language.",
}}
IA = [("eres un bot?", True), ("¿hablo con una persona real o con una máquina?", True), ("are you an AI?", True),
      ("qué inteligencia artificial usas", True), ("is this chatgpt?", True), ("¿me atiende un robot?", True),
      ("estoy hablando con alguien de verdad?", True),
      ("qué modelo de regulador usan?", False), ("what model of dive computer do you rent?", False),
      ("¿los instructores son reales profesionales PADI?", False), ("¿la lancha es un modelo nuevo?", False),
      ("¿qué tecnología usan para las fotos bajo el agua?", False), ("is the instructor a real PADI pro?", False)]
IDIOMA = [("can we continue in english please", "english"), ("puedes escribirme en inglés? mi español es malo", "english"),
          ("I don't speak spanish", "english"), ("switch to english", "english"),
          ("podemos hablar en español?", "spanish"), ("in spanish please", "spanish"),
          ("prefiero que me escribas en español", "spanish"),
          ("¿el curso es en inglés?", "none"), ("is the instructor fluent in english?", "none"),
          ("¿tienen guías que hablen alemán?", "none"), ("do you have the course material in spanish?", "none"),
          ("mi esposo solo habla inglés, ¿el instructor habla inglés?", "none"), ("el libro del curso viene en español?", "none")]


def regex_idioma(m):
    return "english" if _SWITCH_TO_EN_RE.search(m) else "spanish" if _SWITCH_TO_ES_RE.search(m) else "none"


async def jev(msg, q):
    r = await j._http().post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                             json={"model": settings.jev_model, "state": j._estado_para_jev(msg, None),
                                   "questions": {"q": q}}, timeout=15)
    return r.json()["answers"]["q"]


async def main():
    print("== ¿eres un bot?")
    br = bj = 0
    for msg, quiero in IA:
        ps = [round((await jev(msg, PREGUNTA_IA)).get("noul", 0.0), 2) for _ in range(2)]
        ok = all((p >= 0.7) == quiero for p in ps)
        rg = bool(_AI_IDENTITY_RE.search(msg.lower()))
        br += rg == quiero
        bj += ok
        print(f"  {msg!r:55} quiero={quiero!s:5} regex={rg!s:5} jev={ps}{'' if ok else '  <-- MAL'}")
    print(f"  regex {br}/{len(IA)} · Jev {bj}/{len(IA)}")
    print("== idioma")
    br = bj = 0
    for msg, quiero in IDIOMA:
        rs = [await jev(msg, PREGUNTA_IDIOMA) for _ in range(2)]
        cs = [(r.get("choice"), round(r.get("confidence", 0), 2)) for r in rs]
        ok = all(c == quiero and (quiero == "none" or p >= 0.6) for c, p in cs)
        rg = regex_idioma(msg)
        br += rg == quiero
        bj += ok
        print(f"  {msg!r:55} quiero={quiero:8} regex={rg:8} jev={cs}{'' if ok else '  <-- MAL'}")
    print(f"  regex {br}/{len(IDIOMA)} · Jev {bj}/{len(IDIOMA)}")


asyncio.run(main())
