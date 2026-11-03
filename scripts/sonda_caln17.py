"""CALN-17 (3-nov, Gadea #2864): la lectura del grupo en el prompt del extractor, por escalones, con el método de CALN-8 (4).
A = el prompt de hoy; B = el escalón (cambia la DEFINICIÓN de los campos que ya hay, sin campos nuevos ni ejemplos), los
dos intercalados en el mismo proceso. (1) las frases de grupo (los primeros turnos de g37-g47 y la sonda del 3-nov) ×N;
(2) el banco ex0 de diseño ×3 por variante; (3) los que cambian ×10; (4) los 4 que se movieron con el nocturno, ×20
siempre (sonda-plan-nocturno-3nov.md).
    ENV_FILE=.env.dev python scripts/sonda_caln17.py <escalon> [N_frases=10] [N_ex0=3] [N_cambian=10] [N_fijos=20]
    DETALLE=id1,id2 ENV_FILE=.env.dev python scripts/sonda_caln17.py <escalon> [N=10]   # qué campo se mueve
"""
import asyncio
import json
import os
import sys
from collections import Counter

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")
from scripts.run_extraction_eval import casos_ex0, puntuar_ex0  # noqa: E402
from src.agents import extractor_turno as et  # noqa: E402

ESCALON = sys.argv[1]
N_FRASES, N_EX0, N_CAMBIAN, N_FIJOS = (int(a) for a in (sys.argv[2:6] + ["10", "3", "10", "20"][len(sys.argv[2:6]):]))
SIS_ES, SIS_EN = et.SISTEMA_ES, et.SISTEMA_EN

# (texto de hoy, texto del escalón): cada uno está una sola vez en su prompt
ESCALONES = {
    "1": [  # solo cuentan quienes van; el bebé (menor de 6, regla de Gadea) no entra en el reparto ni en el total
        ('Hablar en primera persona ("yo", "quiero") no dice el tamaño del grupo.',
         'Hablar en primera persona ("yo", "quiero") no dice el tamaño del grupo. Cuentan solo quienes van: quien escribe '
         'no cuenta si dice que no va (reserva para otra persona). Un bebé o un niño menor de 6 años no cuenta en '
         'group_size.'),
        ("contando a quien escribe (con lo que ya sabemos de él)",
         "contando a quien escribe si va (con lo que ya sabemos de él)"),
        ("el bot preguntará cuántos son.",
         "el bot preguntará cuántos son. Un bebé o un niño menor de 6 años va en la lancha sin actividad y no paga: no lo "
         "pongas en ninguna actividad del reparto, tampoco en companion ni en undecided (su edad sí va en edades)."),
        ('Speaking in first person ("I", "I want") does not give the group size.',
         'Speaking in first person ("I", "I want") does not give the group size. Only the people going count: the writer '
         'does not count if they say they are not going (booking for someone else). A baby or a child under 6 does not '
         'count in group_size.'),
        ("counting the writer (with what we already know about them)",
         "counting the writer if they are going (with what we already know about them)"),
        ("the bot will ask how many.",
         "the bot will ask how many. A baby or a child under 6 rides on the boat with no activity and does not pay: do not "
         "put them in any activity of the split, not in companion nor in undecided (their age does go in edades)."),
    ],
}


def _con_escalon(texto: str) -> str:
    for hoy, nuevo in ESCALONES[ESCALON]:
        if hoy in texto:
            assert texto.count(hoy) == 1, hoy
            texto = texto.replace(hoy, nuevo)
    return texto


B_ES, B_EN = _con_escalon(SIS_ES), _con_escalon(SIS_EN)
assert B_ES != SIS_ES and B_EN != SIS_EN

FRASES = [  # (id, mensaje, lang, sabido, total esperado, reparto esperado sin undecided; None = no se mira)
    ("g37", "Mi marido es buzo certificado y quiere bucear; yo voy en la lancha con nuestra hija de 1 año, sin hacer nada",
     "es", {}, 2, {"certified_diving": 1, "companion": 1}),
    ("g38", "Somos una pareja y llevamos a nuestro bebé de 2 años; nosotros dos queremos hacer snorkel", "es", {}, 2, None),
    ("g39", "My wife and I want to go snorkeling and we're bringing our 3-year-old", "en", {}, 2, None),
    ("g40", "Somos 4: mi pareja, yo y los niños de 9 y 4 años. Queremos hacer snorkel", "es", {}, 3, None),
    ("g42", "Vamos 3: 1 buzo certificado que quiere bucear y 2 que harán el bautismo", "es", {}, 3,
     {"certified_diving": 1, "minicourse": 2}),
    ("g44", "Tengo el Advanced y quiero bucear. Vienen dos amigos que todavía no saben qué hacer", "es", {}, 3, None),
    ("g45", "Soy buzo certificada y quiero bucear. Viene mi marido, que no bucea, y nuestros hijos de 11 y 13", "es", {},
     4, None),
    ("g46", "Hi! I'd like to book the mini course for my sister as a gift. She is Colombian; I'm Dutch and I won't be "
            "joining.", "en", {}, 1, None),
    ("g47", "Hola, quiero reservarles el snorkel a mis padres por su aniversario. Ellos son colombianos; yo vivo en España "
            "y no voy.", "es", {}, 2, None),
    ("regalo", "Hi! I want to give my girlfriend the mini course as a birthday present. Can I book it in her name? She is "
               "Colombian, I'm German, and I won't dive or come along.", "en", {}, 1, None),
    ("bebe-t2", "Desde Cartagena, el domingo 8. Somos colombianos, de Medellín. Él hace las 2 inmersiones y yo voy de "
                "acompañante con el bebé. ¿Cuánto es lo mío? ¿El bebé paga?", "es",
     {"group_size": 3, "is_certified": True, "edades": [2]}, None, {"certified_diving": 1, "companion": 1}),
    ("somos2-bebe", "Somos 2 y llevamos a nuestro bebé de 1 año, queremos hacer snorkel. ¿Precio?", "es", {}, 2, None),
    ("couple-3yo", "We're a couple with our 3-year-old son. My husband wants to dive, I'll just come along with the "
                   "little one.", "en", {}, 2, None),
    ("r8", "Vamos en família a Cartagena. 1 buzo avanzado y 2 para bautismo", "es", {}, 3,
     {"certified_diving": 1, "minicourse": 2}),
]
FIJOS = ("ex0-desde-islas-buzo-certificado-t1", "ex0-reserva-solo-link-t1",
         "ex0-familia-mixta-precio-descuento-refresher-t4", "ex0-open-water-precio-para-colombianos-corrige-mito-t1")


async def leer(c: dict, v: str, sem: asyncio.Semaphore) -> dict:
    async with sem:
        # `extraer_turno` arma el prompt antes de su primer await: dos llamadas a la vez no se mezclan
        et.SISTEMA_ES, et.SISTEMA_EN = (B_ES, B_EN) if v == "B" else (SIS_ES, SIS_EN)
        d = await et.extraer_turno(c["message"], history=c.get("history"), sabido=c.get("sabido") or {},
                                   lang=c.get("lang", "es"))
        return d or {}


async def pasadas(casos: list[dict], n: int) -> dict:
    sem = asyncio.Semaphore(8)
    orden = [(c, v) for _ in range(n) for c in casos for v in ("A", "B")]
    lecturas = await asyncio.gather(*(leer(c, v, sem) for c, v in orden), return_exceptions=True)
    salida: dict = {}
    for (c, v), d in zip(orden, lecturas, strict=True):
        salida.setdefault((c["id"], v), []).append(d if isinstance(d, dict) else {"_error": repr(d)})
    return salida


def totales(casos: list[dict], lecturas: dict, v: str) -> Counter:
    t = Counter()
    for c in casos:
        for d in lecturas[(c["id"], v)]:
            for tipo, campos in puntuar_ex0(d, c["expected"], c.get("sabido")).items():
                t[tipo] += len(campos)
    return t


def bien(d: dict, total, reparto) -> bool:
    ok = total is None or d.get("group_size") == total
    if reparto is not None:
        r = {k: v for k, v in (d.get("group_allocation") or {}).items() if v and k != "undecided"}
        ok = ok and r == reparto
    return ok


async def detalle(ids: list[str], n: int) -> int:
    """Solo estos casos del ex0 ×n, con qué campo sale acertado, perdido, equivocado o inventado en A y en B."""
    casos = [c for c in casos_ex0("diseño") if c["id"] in ids]
    lecturas = await pasadas(casos, n)
    for c in casos:
        print(f"== {c['id']}  ({c['message'][:90]!r})")
        for v in "AB":
            por_campo = Counter()
            for d in lecturas[(c["id"], v)]:
                for tipo, campos in puntuar_ex0(d, c["expected"], c.get("sabido")).items():
                    por_campo.update(f"{tipo}:{campo}" for campo in campos)
            print(f"   {v} {dict(sorted(por_campo.items()))}")
    et.SISTEMA_ES, et.SISTEMA_EN = SIS_ES, SIS_EN
    return 0


async def main() -> int:
    if os.environ.get("DETALLE"):
        return await detalle(os.environ["DETALLE"].split(","), N_FRASES)
    frases = [{"id": i, "message": m, "lang": lang, "sabido": s, "total": t, "reparto": r}
              for i, m, lang, s, t, r in FRASES]
    lf = await pasadas(frases, N_FRASES)
    print(f"== escalón {ESCALON}: frases de grupo ×{N_FRASES} (bien A → B)")
    for f in frases:
        a = sum(bien(d, f["total"], f["reparto"]) for d in lf[(f["id"], "A")])
        b = sum(bien(d, f["total"], f["reparto"]) for d in lf[(f["id"], "B")])
        lect_b = Counter(json.dumps({"n": d.get("group_size"), "r": d.get("group_allocation")}, ensure_ascii=False,
                                    sort_keys=True) for d in lf[(f["id"], "B")]).most_common(2)
        print(f"  {f['id']:12} {a:2} → {b:2}   B: {lect_b}")
    casos = casos_ex0("diseño")
    le = await pasadas(casos, N_EX0)
    print(f"== ex0 diseño ×{N_EX0}", {v: dict(totales(casos, le, v)) for v in "AB"})
    errores = sum("_error" in d for ls in le.values() for d in ls)
    cambian = [c for c in casos if totales([c], le, "A") != totales([c], le, "B")]
    print(f"   errores {errores} · casos que cambian: {len(cambian)}")
    if cambian:
        l10 = await pasadas(cambian, N_CAMBIAN)
        print(f"== los que cambian ×{N_CAMBIAN}", {v: dict(totales(cambian, l10, v)) for v in "AB"})
        for c in cambian:
            print(f"   {c['id']:58} A {dict(totales([c], l10, 'A'))}  B {dict(totales([c], l10, 'B'))}")
    fijos = [c for c in casos if c["id"] in FIJOS]
    lfi = await pasadas(fijos, N_FIJOS)
    print(f"== los 4 de Gadea ×{N_FIJOS} ({len(fijos)} encontrados)")
    for c in fijos:
        print(f"   {c['id']:58} A {dict(totales([c], lfi, 'A'))}  B {dict(totales([c], lfi, 'B'))}")
    et.SISTEMA_ES, et.SISTEMA_EN = SIS_ES, SIS_EN
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
