"""EX-EST-2 (14-oct): banco del acuse (la frase "Entendido, …" que el bot pone antes de la pregunta).

En las rondas del 13-14 oct ~15 de 53 inventos que marcó el juez eran del acuse: ante mensajes sin nada que reconocer
("Muchas gracias!", "May 3rd", "Para el sábado 30/05") rellenaba con el resumen de la reserva y afirmaba cosas que el
cliente no dijo ("tienes una reserva para el sábado", "has reservado dos minicursos", "tu actividad de PADI Advanced").
Aquí, los mensajes reales (con un resumen como el que recibía) y controles que hoy salen bien; N pasadas por caso, y un
juez (gpt-4.1) que dice si la frase afirma algo que el cliente no dijo.

    ENV_FILE=.env.dev python -m scripts.banco_acuse [--pasadas 5] [--flag acuse_solo_el_mensaje]
"""
import argparse
import asyncio
import json
import sys

CASOS = [
    # (mensaje, resumen de la reserva que recibía el acuse, idioma, ¿caso real con invento?)
    ("or Playa Tranquila on Isla Barú", "actividad principal: minicourse", "en", True),
    ("Muchas gracias!", "personas: 1; ubicación: cartagena; actividad principal: padi_advanced", "es", True),
    ("MINI CURSOS\nRecogida en su hotel en la isla, entrenamiento en piscina y 1 inmersión en los arrecifes.",
     "acaba de responder que NO es colombiano/residente; reparto: minicourse x2", "es", True),
    ("Para el sabado, 30/05", "actividad principal: certified_diving; ubicación: cartagena", "es", True),
    ("Exactamente entre el 20 y 22 de julio", "actividad principal: padi_open_water; personas: 2", "es", True),
    ("OK I will check thanks", "actividad principal: minicourse; personas: 1", "en", True),
    ("May 3rd", "reparto: certified_diving x3, snorkel x3", "en", True),
    ("Frances", "acaba de responder que NO es colombiano/residente; actividad principal: padi_open_water; personas: 2; "
                "ubicación: cartagena", "es", True),
    # controles (hoy bien)
    ("somos 3 y salimos desde cartagena", "actividad principal: certified_diving; personas: 3; ubicación: cartagena",
     "es", False),
    ("voy solo", "actividad principal: snorkel; personas: 1", "es", False),
    ("no, hace poco buceé", "acaba de responder que NO ha pasado más de 2 años desde la última inmersión", "es", False),
    ("my friend will join for snorkeling", "reparto: certified_diving x1, snorkel x1", "en", False),
    ("ninguno colombiano", "acaba de responder que NO es colombiano/residente; personas: 4", "es", False),
]

_JUEZ = (
    "Te doy el MENSAJE de un cliente y la FRASE con la que un asistente lo reconoce. ¿La frase afirma algún hecho sobre "
    "el cliente que el mensaje NO dice (que tiene o hizo una reserva, qué actividad hará, su experiencia, cuántos son, "
    "de dónde sale…)? Repetir o parafrasear lo que SÍ dice el mensaje no cuenta, y tampoco la cortesía. Una frase vacía "
    "no inventa. Responde SOLO 'si' o 'no'."
)


async def main_async(pasadas: int, flags: list[str]) -> int:
    from openai import AsyncOpenAI

    from src.agents.llm_extractor import compose_acknowledgement
    from src.config import settings

    for f in flags:
        setattr(settings, f, True)
    juez = AsyncOpenAI(api_key=settings.openai_api_key)

    async def inventa(mensaje: str, frase: str) -> bool:
        if not frase.strip():
            return False
        r = await juez.chat.completions.create(model="gpt-4.1", temperature=0, max_tokens=3, messages=[
            {"role": "system", "content": _JUEZ},
            {"role": "user", "content": f"MENSAJE: {mensaje}\nFRASE: {frase}"}])
        return (r.choices[0].message.content or "").strip().lower().startswith("s")

    tot_real = tot_ctrl = inv_real = inv_ctrl = vacias = 0
    for mensaje, resumen, lang, real in CASOS:
        frases = await asyncio.gather(*[compose_acknowledgement(mensaje, state_summary=resumen, lang=lang)
                                        for _ in range(pasadas)])
        juicios = await asyncio.gather(*[inventa(mensaje, f) for f in frases])
        n_inv = sum(juicios)
        vacias += sum(1 for f in frases if not f.strip())
        if real:
            tot_real += pasadas
            inv_real += n_inv
        else:
            tot_ctrl += pasadas
            inv_ctrl += n_inv
        ejemplo = next((f for f, j in zip(frases, juicios, strict=True) if j), frases[0])
        print(f"{'REAL' if real else 'CTRL'} inventa {n_inv}/{pasadas} | {mensaje[:40]!r} -> {ejemplo[:90]!r}")
    print(json.dumps({"flags": flags, "inventos_casos_reales": f"{inv_real}/{tot_real}",
                      "inventos_controles": f"{inv_ctrl}/{tot_ctrl}", "frases_vacias": vacias}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pasadas", type=int, default=5)
    p.add_argument("--flag", action="append", default=[])
    a = p.parse_args(argv)
    return asyncio.run(main_async(a.pasadas, a.flag))


if __name__ == "__main__":
    sys.exit(main())
