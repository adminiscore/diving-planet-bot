"""APARCADO (3-nov, decisión de Gadea; docs/robustness/caln/sonda-plan-nocturno-3nov.md): el campo ya no está en el
código; para volver a medirlo, recuperar ef2a94f1 y `campos_paso6(history, sabido)`.

Sparring s03h (3-nov): el campo `plan_nocturno` del extractor sin él (A) y con él (B), intercalados, con el método de
CALN-8 (4): (1) frases propias ×N, mirando plan_nocturno; (2) el banco ex0 de diseño ×3 por variante para encontrar los
casos que cambian (inventados, equivocados, perdidos); (3) esos casos ×10. 1.ª medida (3-nov), con el campo en TODAS
las llamadas: frases 60/70 (la 70.ª, «no lo quiere», da false), ×10 de los que cambian aciertos 131 → 136, perdidos
72 → 54, equivocados 7 → 20, inventados 16 → 19 («island» en «stay one day longer in rosario» 0 → 3-4/10). Por eso
ahora va solo en la apertura o con el buceo certificado en juego (`campos_paso6`).
    ENV_FILE=.env.dev python scripts/sonda_plan_nocturno.py [N_frases=10] [N_ex0=3] [N_cambian=10]"""
import asyncio
import sys
from collections import Counter

sys.path.insert(0, ".")
from scripts.run_extraction_eval import casos_ex0, puntuar_ex0
from src.agents import extractor_turno as et

N_FRASES, N_EX0, N_CAMBIAN = (int(a) for a in (sys.argv[1:4] + ["10", "3", "10"][len(sys.argv[1:4]):]))
CON = et.campos_paso6
OFERTA = [{"role": "assistant", "content": "The night-dive option is a 3-dive package. Would you like to switch your plan "
                                          "to the night-dive package?"}]
CERT = {"activity": "certified_diving", "is_certified": True}  # a mitad de charla, el buceo certificado ya en juego
FRASES = [  # (id, mensaje, historial, plan_nocturno esperado)
    ("quiere-en", "Hey, I'm a certified diver and I'd love to do a night dive. Is that possible? How much?", None, True),
    ("si-el-nocturno-en", "Yes, I want the night dive package, that's why I asked.", OFERTA, True),  # con CERT
    ("quiere-es", "Somos buzos certificados y queremos hacer una inmersión nocturna. ¿Qué plan es?", None, True),
    ("que-es-es", "¿Qué es el buceo nocturno? ¿Da miedo?", None, None),
    ("no-lo-quiere-en", "We don't want the night dive, just the 2 daytime dives.", OFERTA, None),
    ("dos-buceos-es", "Quiero las 2 inmersiones del sábado, soy Advanced.", None, None),
    ("noche-hotel-es", "Llegamos por la noche al hotel, ¿mañana podemos bucear?", None, None),
]


def _sin_nocturno(history, sabido=None):
    campos = CON(history, sabido)
    campos.pop("plan_nocturno", None)
    return campos


async def leer(caso: dict, con_campo: bool, sem: asyncio.Semaphore) -> dict:
    async with sem:
        et.campos_paso6 = CON if con_campo else _sin_nocturno
        d = await et.extraer_turno(caso["message"], history=caso.get("history"), sabido=caso.get("sabido") or {},
                                   lang=caso.get("lang", "es"))
        return d or {}


async def pasadas(casos: list[dict], n: int) -> dict:
    """{(id, variante): [lecturas]} con A y B intercalados, 8 a la vez. El campo se pone justo antes de cada llamada y
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
    frases = [{"id": i, "message": m, "history": h, "lang": "es" if i.endswith("-es") else "en", "esperado": x,
               "sabido": CERT if h else {}} for i, m, h, x in FRASES]
    lf = await pasadas(frases, N_FRASES)
    print("== frases propias (B, con el campo)")
    for f in frases:
        ds = lf[(f["id"], "B")]
        print(f"  {f['id']:18} plan_nocturno {dict(Counter(d.get('plan_nocturno') for d in ds))}  (esperado "
              f"{f['esperado']})")
    casos = casos_ex0("diseño")
    le = await pasadas(casos, N_EX0)
    print("== ex0 diseño ×", N_EX0, {v: dict(totales(casos, le, v)) for v in "AB"})
    print("   plan_nocturno en B:", sum(d.get("plan_nocturno") is True for c in casos for d in le[(c["id"], "B")]))
    cambian = [c for c in casos if totales([c], le, "A") != totales([c], le, "B")]
    print("   casos que cambian:", len(cambian))
    if cambian:
        l10 = await pasadas(cambian, N_CAMBIAN)
        print("== los que cambian ×", N_CAMBIAN, {v: dict(totales(cambian, l10, v)) for v in "AB"})
        for c in cambian:
            print(f"   {c['id']:55} A {dict(totales([c], l10, 'A'))}  B {dict(totales([c], l10, 'B'))}")
    et.campos_paso6 = CON
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
