"""Sparring s03h (3-nov): ¿cuenta el extractor al bebé en el total del grupo? Resultado ×5 (3-nov): «voy con mi esposo…
y nuestro bebé de 2 años» → sin total; «Somos 2 y llevamos a nuestro bebé de 1 año» → 2 (NO lo cuenta); «a couple with
our 3-year-old son» → 3 (sí); «Somos 4: … hijos de 8 y 3» → 4 (sí). Por eso restar al bebé del total por código rompe
el segundo caso: la cuenta va donde se lee el grupo (hallazgos CALN-S03H, grave 2).
    ENV_FILE=.env.dev python scripts/sonda_bebes_grupo.py"""
import asyncio
import sys
from collections import Counter

sys.path.insert(0, ".")
from src.agents import extractor_turno as et

FRASES = [
    ("Hola, voy con mi esposo que es buzo y nuestro bebé de 2 años. ¿Puedo ir en la lancha con el bebé mientras él bucea?", "es"),
    ("Somos 2 y llevamos a nuestro bebé de 1 año, queremos hacer snorkel. ¿Precio?", "es"),
    ("We're a couple with our 3-year-old son. My husband wants to dive, I'll just come along with the little one.", "en"),
    ("Somos 4: mi esposa, yo y nuestros hijos de 8 y 3 años. Queremos snorkel.", "es"),
]

async def main():
    for m, lang in FRASES:
        ds = await asyncio.gather(*(et.extraer_turno(m, history=[], sabido={}, lang=lang) for _ in range(5)))
        print(m[:70])
        print("   group_size", dict(Counter(d.get("group_size") for d in ds)), "| edades", dict(Counter(str(d.get("edades")) for d in ds)))
        print("   reparto", dict(Counter(str(d.get("group_allocation")) for d in ds)))

asyncio.run(main())
