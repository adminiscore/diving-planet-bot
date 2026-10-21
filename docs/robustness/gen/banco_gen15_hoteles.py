"""gen-15 (21-oct): ¿los dos lectores del lugar (extractor y Jev) entienden que el cliente se aloja en las islas cuando
nombra un hotel de las islas? Banco propio (frases nuestras; no sale del examen).

Causas de G10/G9 que pasó Gadea por tipos (Coral #999): (a) hotel de la lista de islas no reconocido → repregunta el
origen (Majagua, Eco Hotel Las Palmeras); (b) hotel reconocido (Ubuntu) sin aplicar el plan «ya en las islas». Los
hoteles salen de data/knowledge_base/policies.json (other_island_hotels: base en Majagua y Cocoliso; además Rosario de
Mar, Secreto, Ubuntu, Mulata y Eco Hotel Las Palmeras). Con LUGAR_CON_DOS_LECTORES, un «none» seguro de Jev tumba lo
que diga el extractor, así que se miran los dos.

Cada caso: (mensaje, idioma, lugar esperado: "island", "cartagena" o None = no dice desde dónde sale).

    ENV_FILE=.env.dev python docs/robustness/gen/banco_gen15_hoteles.py [--pasadas 3] [--flag X]
"""
import argparse
import asyncio
import os
import sys

os.environ.setdefault("ENV_FILE", ".env.dev")
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CASOS = [
    ("Hola, nos alojamos en el Majagua tres noches, ¿qué planes de buceo tienen?", "es", "island"),
    ("we're staying at Eco Hotel Las Palmeras next week, how much is snorkeling?", "en", "island"),
    ("vamos a estar en Las Palmeras, ¿cuánto vale el minicurso?", "es", "island"),
    ("we booked 2 nights at Mulata, can we do a dive from there?", "en", "island"),
    ("estaremos en Rosario de Mar con mi novia, ¿qué nos recomiendas?", "es", "island"),
    ("Hi, we're at Ubuntu, what does the 2-dive trip include?", "en", "island"),
    ("estamos en Coral Sand en Isla Grande", "es", "island"),
    ("estaremos en islas del rosario en junio y quiero regalarle un bautizo a mi esposo", "es", "island"),
    # Controles: un hotel de Cartagena, Barú (sale de Cartagena, gen-6) y las islas como sitio donde se bucea.
    ("nos quedamos en el Hotel Caribe en Bocagrande", "es", "cartagena"),
    ("estamos alojados en Barú", "es", "cartagena"),
    ("queremos ir a las islas del Rosario a bucear", "es", None),
]


async def main(pasadas: int, flags: list[str]) -> int:
    from src.agents.extractor_turno import extraer_turno
    from src.agents.jev_router import detect_routing_signals_jev_full
    from src.config import settings

    for f in flags:
        setattr(settings, f, True)
    bien_ex = bien_jev = total = 0
    for mensaje, lang, esperado in CASOS:
        ex = await asyncio.gather(*[extraer_turno(mensaje, history=[], sabido={}, lang=lang) for _ in range(pasadas)])
        jev = await asyncio.gather(*[detect_routing_signals_jev_full(mensaje, lang=lang) for _ in range(pasadas)])
        lugares = [(d or {}).get("location") for d in ex]
        places = []
        for resultado, extras in jev:
            senales = resultado if isinstance(resultado, dict) else {}
            lugar = (senales.get("customer_place") or extras.get("customer_place") or {})
            places.append(f"{lugar.get('choice')}:{lugar.get('confidence', 0):.2f}" if lugar else "—")
        jev_esperado = {"island": "islands", "cartagena": "cartagena", None: "none"}[esperado]
        ok_ex = sum(1 for v in lugares if v == esperado)
        ok_jev = sum(1 for p in places if p.startswith(jev_esperado + ":"))
        bien_ex, bien_jev, total = bien_ex + ok_ex, bien_jev + ok_jev, total + pasadas
        marca = "ok " if ok_ex == pasadas and ok_jev == pasadas else "MAL"
        print(f"{marca} extractor {ok_ex}/{pasadas} {lugares} · Jev {ok_jev}/{pasadas} {places} | {mensaje[:70]!r}")
    print(f"RESUMEN flags={flags}: extractor {bien_ex}/{total} · Jev {bien_jev}/{total}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pasadas", type=int, default=3)
    p.add_argument("--flag", action="append", default=[])
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.pasadas, a.flag)))
