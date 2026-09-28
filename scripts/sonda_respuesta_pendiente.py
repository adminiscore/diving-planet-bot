"""Banco de calibración de la pregunta de Jev `pending_answer` (u3-7, paso 7).

Respuestas no canónicas a la pregunta pendiente (las que hoy interpreta el LLM `resolve_slot_answer`)
y mensajes que NO contestan a esa pregunta. Lo que importa: ninguna respuesta EQUIVOCADA con
confianza >= PENDING_ANSWER_MIN (esas se aplican sin el LLM); las dudosas van al LLM como hoy.

    python -m scripts.sonda_respuesta_pendiente
"""
import asyncio
import os
import sys

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx  # noqa: E402

from src.agents import jev_router  # noqa: E402
from src.config import settings  # noqa: E402

CASOS = [
    ("safety", "uf, hace muchísimo", True),
    ("safety", "la última fue en enero", False),
    ("safety", "no me acuerdo, hace años", True),
    ("safety", "este año ya fui dos veces", False),
    ("safety", "¿cuánto cuesta el refresher?", None),
    ("nationality", "vivo en bogotá", True),
    ("nationality", "soy de españa", False),
    ("nationality", "somos argentinos pero vivimos en medellín", True),
    ("nationality", "just visiting from Canada", False),
    ("nationality", "¿aceptan tarjeta?", None),
    ("certification", "tengo el open water", True),
    ("certification", "nunca he buceado", False),
    ("certification", "sí, advanced de SSI", True),
    ("certification", "todavía no", False),
    ("certification", "¿qué incluye el plan?", None),
    ("refresher", "sí, no estaría mal", True),
    ("refresher", "mejor no, gracias", False),
    ("refresher", "claro que sí", True),
    ("refresher", "¿a qué hora salimos?", None),
    ("location", "estamos en el hotel San Pedro de Majagua", "island"),
    ("location", "salimos de la ciudad amurallada", "cartagena"),
    ("location", "nos quedamos en el centro de Cartagena", "cartagena"),
    ("location", "¿dónde queda el muelle?", None),
    ("course_level", "el avanzado", "padi_advanced"),
    ("course_level", "el básico, para empezar", "padi_open_water"),
    ("course_level", "nitrox", "specialty_nitrox"),
    ("cert_or_course", "ya lo tengo", "already_certified"),
    ("cert_or_course", "quiero sacarlo con ustedes", "wants_course"),
    ("stay_duration", "solo un día", "single_day"),
    ("stay_duration", "vamos a estar tres días", "multi_day"),
]


async def main() -> None:
    min_conf = jev_router.PENDING_ANSWER_MIN
    ok = wrong_conf = doubt = 0
    async with httpx.AsyncClient() as cli:
        for slot, msg, expected in CASOS:
            q = jev_router.pending_answer_question(slot)
            r = await cli.post(
                jev_router.JEV_URL,
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                json={"model": settings.jev_model, "state": f"{jev_router._CONTEXT}\n\nCustomer message: {msg}",
                      "questions": {"q": q}},
                timeout=15.0,
            )
            r.raise_for_status()
            got = jev_router.pending_answer_value(slot, r.json()["answers"]["q"])
            sure = got["confidence"] >= min_conf
            right = got["value"] == expected
            tag = "ok" if right and sure else ("DUDA" if not sure else "MAL")
            ok += tag == "ok"
            wrong_conf += tag == "MAL"
            doubt += tag == "DUDA"
            print(f"{tag:4} {got['confidence']:.2f} {slot:14} {msg[:45]:45} -> {got['value']!r} (esperado {expected!r})")
    print(f"\ncon confianza >= {min_conf}: acierta {ok}/{len(CASOS)}, EQUIVOCADAS {wrong_conf}, al LLM {doubt}")


if __name__ == "__main__":
    asyncio.run(main())
