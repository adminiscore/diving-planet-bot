"""gen-8 (21-oct): ¿el acuse habla en plural a quien va solo? Banco propio (no sale del examen).

Hallazgo de textos-B (Gadea, 20-oct): el acuse le dijo «none of you are Colombian» a quien iba solo. Sus instrucciones
le dan esa frase en plural como ejemplo de cómo reconocer una nacionalidad, y la copia.

Cada caso: el mensaje, el contexto que recibe el acuse en la reserva (`_booking_context_summary` tras la pregunta de
nacionalidad), el idioma y si el grupo es de UNA persona. Cuenta, en las frases de quien va solo, las que hablan en
plural (marcas de la lista de abajo; es una comprobación de la medida, no una regla del bot).

    ENV_FILE=.env.dev python docs/robustness/gen/banco_gen8_acuse.py [--pasadas 5] [--flag acuse_en_su_numero]
"""
import argparse
import asyncio
import os
import re
import sys

os.environ.setdefault("ENV_FILE", ".env.dev")
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NO_ES = "acaba de responder que NO es colombiano/residente; actividad principal: certified_diving"
CASOS = [
    # (mensaje, contexto, idioma, solo)
    ("no", NO_ES + "; personas: 1; ubicación: cartagena", "en", True),
    ("I'm not Colombian", NO_ES + "; personas: 1", "en", True),
    ("no, I'm from Canada", NO_ES + "; personas: 1; ubicación: cartagena", "en", True),
    ("nope, just me and I'm not from Colombia", NO_ES + "; personas: 1", "en", True),
    ("no", NO_ES + "; personas: 1; ubicación: cartagena", "es", True),
    ("no soy colombiano", NO_ES + "; personas: 1", "es", True),
    ("no, soy de España", NO_ES + "; personas: 1; ubicación: cartagena", "es", True),
    # Grupos: el plural es correcto.
    ("none of us are Colombian", NO_ES + "; personas: 2", "en", False),
    ("ninguno colombiano", NO_ES + "; personas: 3; ubicación: cartagena", "es", False),
]
_PLURAL = {
    "en": re.compile(r"\b(none of you|any of you|neither of you|you all|you both|all of you|you're all|you are all)\b",
                     re.IGNORECASE),
    "es": re.compile(r"\b(ustedes|ninguno|ninguna|ambos|ambas|todos ustedes|son colombian|sois)\b", re.IGNORECASE),
}


async def main(pasadas: int, flags: list[str]) -> int:
    from src.agents.llm_extractor import compose_acknowledgement
    from src.config import settings

    for f in flags:
        setattr(settings, f, True)
    plural_solo = total_solo = 0
    for mensaje, contexto, lang, solo in CASOS:
        frases = await asyncio.gather(*[compose_acknowledgement(mensaje, state_summary=contexto, lang=lang)
                                        for _ in range(pasadas)])
        en_plural = [f for f in frases if _PLURAL[lang].search(f)]
        if solo:
            total_solo += pasadas
            plural_solo += len(en_plural)
        marca = ("SOLO " if solo else "GRUPO") + f" plural {len(en_plural)}/{pasadas}"
        print(f"{marca} | {lang} {mensaje!r:42} -> {frases[0]!r}")
    print(f"RESUMEN modelo={settings.acuse_model} flags={flags}: frases en plural a quien va solo {plural_solo}/{total_solo}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pasadas", type=int, default=5)
    p.add_argument("--flag", action="append", default=[])
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.pasadas, a.flag)))
