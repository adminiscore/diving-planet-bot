"""gen-4 (21-oct): ¿el extractor lee bien quién paga en pesos? Banco propio (frases nuestras; no sale del examen).

La regla del negocio (data/knowledge_base/policies.json, colombian_pricing; decisión de Álvaro del 17-oct, sin cédula =
USD): pagan en COP los colombianos, vivan donde vivan, y los residentes en Colombia, que es tener cédula de extranjería.
VIVIR en Colombia sin decir que es colombiano ni que tiene cédula no dice nada de la moneda (G9, causa 6: "vivir en
Colombia ≠ residente con cédula"). El resto paga en USD.

Cada caso: (mensaje, última pregunta del bot o None, idioma, is_colombian esperado: True, False o None = no lo dice).

    ENV_FILE=.env.dev python docs/robustness/gen/banco_gen4_moneda.py [--pasadas 3] [--flag X]
"""
import argparse
import asyncio
import os
import sys

os.environ.setdefault("ENV_FILE", ".env.dev")
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

P_ES = "Última cosa para darte el precio y el link correctos: ¿eres colombiano o residente en Colombia?"
P_EN = "One last thing so I can give you the right price and link: are you Colombian or a resident of Colombia?"
P_ES_CEDULA = ("Última cosa para darte el precio y el link correctos: ¿eres de nacionalidad colombiana o tienes cédula "
               "de extranjería?")
P_EN_CEDULA = ("One last thing so I can give you the right price and link: are you a Colombian national, or do you have "
               "a Colombian *cédula de extranjería* (Colombia's ID card for foreigners)?")
CASOS = [
    # Colombianos, vivan donde vivan: COP.
    ("soy colombiana pero vivo en Madrid hace años", None, "es", True),
    ("I'm Colombian but I live in Miami", None, "en", True),
    ("sí, soy paisa", P_ES, "es", True),
    ("yes, both of us are Colombian", P_EN, "en", True),
    # Residentes con cédula de extranjería: COP.
    ("no soy colombiano pero tengo cédula de extranjería", P_ES, "es", True),
    ("I'm Venezuelan and I have a cédula de extranjería", None, "en", True),
    ("soy español, pero tengo cédula de extranjería desde hace años", None, "es", True),
    ("I'm French and I hold a Colombian resident ID", P_EN, "en", True),
    # arq-1r (22-oct): extranjero CON cédula de extranjería (chocaba con «extranjero o turista: false»).
    ("sí, soy alemana pero tengo cédula de extranjería", P_ES, "es", True),
    ("I hold a cédula de extranjería.", P_EN, "en", True),
    # Viven en Colombia sin decir nacionalidad ni cédula: no lo dice (None).
    ("vivo en Medellín hace dos años", None, "es", None),
    ("I live in Bogotá", P_EN, "en", None),
    ("we live in Cartagena, we're expats", None, "en", None),
    ("estoy viviendo en Colombia por trabajo", P_ES, "es", None),
    ("sí, vivo aquí", P_ES, "es", None),
    # Nacer en Colombia no da la nacionalidad sola (Gadea, 21-oct: no se deduce; se pregunta).
    ("nací en Bogotá, aunque ahora vivo en Chile", None, "es", None),
    # gen-14: la ciudad o el gentilicio de Colombia, aunque diga dónde se aloja o adónde viaja (frases propias, distintas
    # de los ejemplos de la regla).
    ("Hola! Somos de Cali y ya estamos alojados en Isla Grande, ¿cuánto vale la salida de 2 inmersiones?", None, "es", True),
    ("Buenas, soy paisa y tengo Advanced, ¿qué precio tiene el paquete de 5 inmersiones?", None, "es", True),
    ("mi familia y yo somos de Pereira, estamos de vacaciones en Cartagena", None, "es", True),
    ("I'm from Bucaramanga originally, now on holiday in Cartagena", None, "en", True),
    ("sí, soy santandereano", P_ES, "es", True),
    # arq-1f (22-oct, decisión de Gadea): «soy de <ciudad>» en singular y sin hablar del alojamiento (banco arq-1d p6:
    # «Soy de Medellín…» salía null). Frases propias, con otras ciudades.
    ("Soy de Barranquilla, ¿cuánto cuesta el snorkel?", None, "es", True),
    ("soy de Manizales y quiero hacer el minicurso", None, "es", True),
    ("I'm from Cali, how much is the mini course?", None, "en", True),
    ("Soy de Bogotá pero vivo en Madrid, ¿qué vale el Open Water?", None, "es", True),
    ("vivo en Barranquilla, ¿cuánto cuesta el snorkel?", None, "es", None),
    # Controles: alojarse o viajar no dice nada; una ciudad de OTRO país no es Colombia.
    ("estamos de vacaciones en Bogotá esta semana", None, "es", None),
    ("we're staying in Medellín for a month", None, "en", None),
    ("somos de Lima y estamos alojados en Cartagena", None, "es", "no_true"),
    # Extranjeros (sin cédula o turistas): USD.
    ("soy gringo, vivo en Medellín pero no tengo cédula", None, "es", False),
    ("I'm American, living in Bogotá on a tourist visa", P_EN, "en", False),
    ("no, soy de Argentina y vivo en Cali, pero no tengo cédula", P_ES, "es", False),
    ("no, we're Canadian", P_EN, "en", False),
]


async def main(pasadas: int, flags: list[str], pregunta_vieja: bool = False) -> int:
    from src.agents.extractor_turno import extraer_turno
    from src.config import settings

    for f in flags:
        setattr(settings, f, True)
    bien = total = 0
    por_tipo: dict[str, list[int]] = {}
    for mensaje, pregunta, lang, esperado in CASOS:
        if pregunta and settings.vivir_no_es_residir and not pregunta_vieja:  # con el flag, el bot pregunta por la nacionalidad o la cédula
            pregunta = P_ES_CEDULA if pregunta == P_ES else P_EN_CEDULA
        historia = [{"role": "assistant", "content": pregunta}] if pregunta else []
        salidas = await asyncio.gather(*[extraer_turno(mensaje, history=historia, sabido={}, lang=lang)
                                         for _ in range(pasadas)])
        leidos = [(s or {}).get("is_colombian") for s in salidas]
        ok = sum(1 for v in leidos if (v is not True) if esperado == "no_true") if esperado == "no_true" else             sum(1 for v in leidos if v is esperado)
        bien, total = bien + ok, total + pasadas
        tipo = {True: "COP", False: "USD", None: "no lo dice", "no_true": "USD"}[esperado]
        por_tipo.setdefault(tipo, [0, 0])
        por_tipo[tipo][0] += ok
        por_tipo[tipo][1] += pasadas
        marca = "ok " if ok == pasadas else "MAL"
        print(f"{marca} {ok}/{pasadas} espera {esperado!s:5} lee {leidos} | {lang} {mensaje!r}")
    print(f"RESUMEN flags={flags}: {bien}/{total} | " + " · ".join(f"{t} {b}/{n}" for t, (b, n) in por_tipo.items()))
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pasadas", type=int, default=3)
    p.add_argument("--flag", action="append", default=[])
    p.add_argument("--pregunta-vieja", action="store_true", help="con el flag, la pregunta del bot de antes")
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.pasadas, a.flag, a.pregunta_vieja)))
