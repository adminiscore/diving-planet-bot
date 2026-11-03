"""Sparring s30e (30-oct): la regla del extractor «el residente con cédula de extranjería no hace mixto al grupo»
(`extractor_turno._RESIDENTE_NO_MEZCLA`) sin ella (A) y con ella (B), intercalados, con el método de CALN-8 (4):
(1) frases propias ×N, mirando mixed_nationality e is_colombian; (2) el banco ex0 de diseño ×3 por variante para
encontrar los casos que cambian (inventados, equivocados, perdidos); (3) esos casos ×10.
DESCARTADA el 30-oct (`docs/robustness/caln/sonda-residente-mixto-30oct.txt`): el venezolano mixed 10 → 7/10, el alemán
con cédula 10 → 10, y en los 16 casos que cambian ×10 aciertos 142 → 133, equivocados 6 → 11, inventados 34 → 40. La
regla ya no está en el código: para volver a medirla, ponerla en `extractor_turno` (el mismo `replace` que las demás).
    ENV_FILE=.env.dev python scripts/sonda_residente_mixto.py [N_frases=10] [N_ex0=3] [N_cambian=10]"""
import asyncio
import sys
from collections import Counter

sys.path.insert(0, ".")
from scripts.run_extraction_eval import casos_ex0, puntuar_ex0
from src.agents import extractor_turno as et

N_FRASES, N_EX0, N_CAMBIAN = (int(a) for a in (sys.argv[1:4] + ["10", "3", "10"][len(sys.argv[1:4]):]))
REGLA = getattr(et, "_RESIDENTE_NO_MEZCLA", ())
FRASES = [  # (id, mensaje, mixed esperado)
    ("venezolano-cedula", "Hola, soy venezolano, vivo en Cartagena hace 5 años y tengo cédula de extranjería. Mi esposa es "
     "colombiana. Queremos hacer el minicurso los dos. ¿Cuánto es y podemos pagar con Nequi?", False),
    ("aleman-cedula", "I'm German but I have a cédula de extranjería, I live in Medellín. My girlfriend is Colombian. How "
     "much is snorkeling for us?", False),
    ("mixto-de-verdad", "Somos 6: 4 colombianos y 2 alemanes que vienen de visita. ¿Cuánto cuesta el snorkel?", True),
    ("pareja-espanol", "Mi esposa es colombiana y yo soy español, estoy de turista. ¿Cuánto es el minicurso para los dos?",
     True),
    ("todos-colombianos", "Somos de Bogotá, 3 personas, queremos bucear. ¿Precio?", False),
]


async def leer(caso: dict, con_regla: bool, sem: asyncio.Semaphore) -> dict:
    async with sem:
        et._RESIDENTE_NO_MEZCLA = REGLA if con_regla else ()
        d = await et.extraer_turno(caso["message"], history=caso.get("history"), sabido=caso.get("sabido") or {},
                                   lang=caso.get("lang", "es"))
        return d or {}


async def pasadas(casos: list[dict], n: int) -> dict:
    """{(id, variante): [lecturas]} con A y B intercalados, 8 a la vez. La regla se pone justo antes de cada llamada y
    `extraer_turno` arma el prompt antes de su primer await, así que dos llamadas a la vez no se mezclan."""
    sem = asyncio.Semaphore(8)
    orden = [(c, v) for _ in range(n) for c in casos for v in ("A", "B")]
    lecturas = await asyncio.gather(*(leer(c, v == "B", sem) for c, v in orden))
    salida: dict = {}
    for (c, v), d in zip(orden, lecturas, strict=True):
        salida.setdefault((c["id"], v), []).append(d)
    return salida


def totales(casos: list[dict], lecturas: dict, v: str) -> Counter:
    t = Counter()
    for c in casos:
        for d in lecturas[(c["id"], v)]:
            for tipo, campos in puntuar_ex0(d, c["expected"], c.get("sabido")).items():
                t[tipo] += len(campos)
    return t


async def main() -> int:
    frases = [{"id": i, "message": m, "lang": "en" if m.startswith("I'm") else "es", "mixto": x} for i, m, x in FRASES]
    lf = await pasadas(frases, N_FRASES)
    print("== frases propias")
    for f in frases:
        for v in "AB":
            ds = lf[(f["id"], v)]
            print(f"  {f['id']:20} {v} mixed {dict(Counter(d.get('mixed_nationality') for d in ds))}  "
                  f"is_colombian {dict(Counter(d.get('is_colombian') for d in ds))}  (esperado mixed {f['mixto']})")
    casos = casos_ex0("diseño")
    le = await pasadas(casos, N_EX0)
    print("== ex0 diseño ×", N_EX0, {v: dict(totales(casos, le, v)) for v in "AB"})
    cambian = [c for c in casos if Counter(map(repr, le[(c["id"], "A")])) != Counter(map(repr, le[(c["id"], "B")]))
               and totales([c], le, "A") != totales([c], le, "B")]
    print("   casos que cambian:", len(cambian))
    if cambian:
        l10 = await pasadas(cambian, N_CAMBIAN)
        print("== los que cambian ×", N_CAMBIAN, {v: dict(totales(cambian, l10, v)) for v in "AB"})
        for c in cambian:
            print(f"   {c['id']:55} A {dict(totales([c], l10, 'A'))}  B {dict(totales([c], l10, 'B'))}")
    et._RESIDENTE_NO_MEZCLA = REGLA
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
