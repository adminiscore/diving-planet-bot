"""Lectura del grupo (3-nov, #2786 Gonzalo + #2798/#2809 Gadea): cómo lee el extractor (con sus reglas de código) el
total y el reparto en frases con bebés, «1 buzo avanzado y 2 para bautismo» (R8) y CALN4-05. ×N por frase, a la vez.
Correr desde un worktree con ENV_FILE apuntando a .env.dev:
    ENV_FILE=.env.dev python scripts/sonda_lectura_grupo.py 10 docs/robustness/caln/sonda-lectura-grupo-3nov.jsonl
"""
import asyncio
import json
import sys
from collections import Counter

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from src.agents import extractor_turno as et  # noqa: E402

FRASES = [
    ("bebe-t1", "Hola, voy con mi esposo que es buzo y nuestro bebé de 2 años. ¿Puedo ir en la lancha con el bebé "
                "mientras él bucea?", "es", {}),
    ("bebe-t2", "Desde Cartagena, el domingo 8. Somos colombianos, de Medellín. Él hace las 2 inmersiones y yo voy de "
                "acompañante con el bebé. ¿Cuánto es lo mío? ¿El bebé paga?", "es",
     {"group_size": 3, "is_certified": True, "edades": [2]}),
    ("bebe-somos2", "Somos 2 y llevamos a nuestro bebé de 1 año, queremos hacer snorkel. ¿Precio?", "es", {}),
    ("bebe-couple", "We're a couple with our 3-year-old son. My husband wants to dive, I'll just come along with the "
                    "little one.", "en", {}),
    ("bebe-somos4", "Somos 4: mi esposa, yo y nuestros hijos de 8 y 3 años. Queremos snorkel.", "es", {}),
    ("r8", "Vamos en família a Cartagena. 1 buzo avanzado y 2 para bautismo", "es", {}),
    ("caln4-05", "Yo tengo el Open Water y quiero bucear. Mi esposo no bucea y vamos con los niños, de 7 y 4", "es", {}),
]
CAMPOS = ("group_size", "group_allocation", "activity", "is_certified", "edades")


async def main(n: int, salida: str):
    filas = []
    for nombre, m, lang, sabido in FRASES:
        ds = await asyncio.gather(*(et.extraer_turno(m, history=[], sabido=sabido, lang=lang) for _ in range(n)),
                                  return_exceptions=True)
        errores = sum(isinstance(d, Exception) for d in ds)
        ds = [d for d in ds if isinstance(d, dict)]
        lecturas = Counter(json.dumps({c: d.get(c) for c in CAMPOS}, ensure_ascii=False, sort_keys=True) for d in ds)
        print(f"{nombre} ({len(ds)} de {n}, errores {errores})")
        for lectura, veces in lecturas.most_common():
            print(f"   {veces}× {lectura}")
        filas.append({"frase": nombre, "n": n, "errores": errores, "lecturas": dict(lecturas)})
    with open(salida, "w", encoding="utf-8") as f:
        for fila in filas:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")


asyncio.run(main(int(sys.argv[1]), sys.argv[2]))
