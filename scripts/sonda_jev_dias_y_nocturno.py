"""CALN-25 y CALN-20 (4-nov, decisiones de Gadea), sonda de Jev. (a) `son_dias_de_buceo`: «two dives» no son 2 días, y hoy lo deciden
2 regex (se escapa «two dives on Saturday and Sunday»). (b) `pide_nocturno`: pedir el nocturno elige el paquete que lo lleva; como
campo del extractor, 6 versiones movían otras lecturas. Jev contesta cada pregunta sin ver las demás; aquí se comprueba además que
las señales de siempre no se mueven: mismas preguntas con y sin las dos nuevas, misma lectura. Corre en dp-pre-bot con el código
local (`ENV_FILE=.env.dev python -m scripts.sonda_jev_dias_y_nocturno [N] [salida]`)."""
import json
import sys
from collections import defaultdict

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

# (mensaje, son_dias_de_buceo, pide_nocturno); None: da igual
CASOS = [
    # varios días de buceo
    ("We'd like to dive on two different days and do one night dive.", True, True),
    ("Quiero bucear tres días seguidos", True, False),
    ("We want two dives on Saturday and two dives on Sunday. How much is it?", True, False),
    ("I want to do two dives on Saturday and Sunday", True, False),
    ("Somos dos buzos certificados, estamos en Cartagena y queremos bucear 3 días. ¿Cuánto cuesta?", True, False),
    ("I'd like 4 dives over 2 days, how much is it?", True, False),
    ("Queremos dos días de buceo", True, False),
    ("We're looking to dive for 4 days during our stay", True, False),
    ("Quiero 2 inmersiones en 2 días", True, False),
    # inmersiones o estancia, no días de buceo
    ("Can you pick us up for two dives?", False, False),
    ("Somos dos buzos certificados, estamos en Cartagena y queremos hacer dos inmersiones. ¿Cuánto cuesta?", False, False),
    ("Thanks, but how much is just the two-dive trip? That's what we want.", False, False),
    ("As I said, five of us will do the two dives and two the mini course. Please send both links.", False, False),
    ("Quiero las 2 inmersiones del sábado, soy Advanced.", False, False),
    ("We're in Cartagena for 3 days, can we do a dive?", False, False),
    ("Estaré en Cartagena cinco días y quiero bucear un día", False, False),
    ("Me interesa el paquete de 5 inmersiones", None, False),
    # el nocturno
    ("Hey, I'm a certified diver and I'd love to do a night dive. Is that possible? How much?", False, True),
    ("Yes, I want the night dive package, that's why I asked.", None, True),
    ("Somos buzos certificados y queremos hacer una inmersión nocturna. ¿Qué plan es?", False, True),
    ("Me gustaría incluir el buceo nocturno en el plan", None, True),
    ("Can we add a night dive on the second day?", None, True),
    # no lo pide
    ("¿Qué es el buceo nocturno? ¿Da miedo?", None, False),
    ("We don't want the night dive, just the 2 daytime dives.", False, False),
    ("Llegamos por la noche al hotel, ¿mañana podemos bucear?", False, False),
    ("Does the 5-dive package include a night dive?", None, False),
    ("Solo queremos bucear de día", False, False),
    ("We'll stay one night on the island", False, False),
]
DIAS = (
    "The customer says they want to go diving on two or more separate days ('dive on two different days', 'bucear tres "
    "días', 'on Saturday and Sunday', '4 dives over 2 days'). It is FALSE when the number counts dives and not days ('two "
    "dives', 'dos inmersiones', 'the two-dive trip', 'the 2 dives on Saturday'), when the days are only how long they stay "
    "('we're here for 3 days'), or when they say nothing about diving on several days."
)
NOCTURNO = (
    "The customer wants to do a night dive, or a plan or package because it has one: they ask for it, ask to add it, or "
    "ask how much it costs. It is FALSE if they only ask what a night dive is, whether a plan includes one, or say they "
    "do not want it, and when 'night' refers to their stay or arrival ('one night on the island', 'llegamos por la noche')."
)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3

REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg, con):
    q = j._questions_for_turn(None)
    if con:
        q["son_dias_de_buceo"] = {"type": "noul", "instructions": DIAS}
        q["pide_nocturno"] = {"type": "noul", "instructions": NOCTURNO}
    r = await client.post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                          json={"model": settings.jev_model, "state": j._estado_para_jev(msg, None), "questions": q},
                          timeout=30)
    r.raise_for_status()
    a = r.json()["answers"]
    return {k: (v.get("noul") if "noul" in v else v.get("choice")) for k, v in a.items()}

async def main():
    async with httpx.AsyncClient() as c:
        for msg in MENSAJES:
            for rep in range(N):
                for con in (False, True):
                    try:
                        print(json.dumps({"msg": msg, "rep": rep, "con": con, "a": await una(c, msg, con)}, ensure_ascii=False), flush=True)
                    except Exception as e:
                        print(json.dumps({"msg": msg, "rep": rep, "error": str(e)[:200]}), flush=True)
asyncio.run(main())
'''

MENSAJES = [c[0] for c in CASOS]
script = (f"import json\nMENSAJES = json.loads({json.dumps(MENSAJES, ensure_ascii=False)!r})\n"
          f"DIAS = {DIAS!r}\nNOCTURNO = {NOCTURNO!r}\nN = {N}\n{REMOTO}")
r = pre_ssh(docker_python(None, codigo_local=subir_codigo_local()), input_text=script, timeout=1500)
filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
if r.stderr:
    print(r.stderr[-800:], file=sys.stderr)
out = sys.argv[2] if len(sys.argv) > 2 else "sonda-jev-dias-nocturno.jsonl"
open(out, "w", encoding="utf-8").write("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas))

por = defaultdict(list)
for f in filas:
    if f.get("con") and "a" in f:
        por[f["msg"]].append(f["a"])
b_d = c_d = b_n = c_n = 0
for msg, dias, noct in CASOS:
    vs = por.get(msg) or []
    a = [v.get("son_dias_de_buceo") or 0 for v in vs]
    b = [v.get("pide_nocturno") or 0 for v in vs]
    if dias is not None:
        b_d += sum((x >= 0.7) == dias for x in a)
        c_d += len(a)
    b_n += sum((x >= 0.7) == noct for x in b)
    c_n += len(b)
    print(f"dias {dias!s:5} {min(a, default=0):.2f}-{max(a, default=0):.2f} | noct {noct!s:5} "
          f"{min(b, default=0):.2f}-{max(b, default=0):.2f} | {msg[:62]}")
print(f"TOTAL dias {b_d}/{c_d}; nocturno {b_n}/{c_n}")

# ¿Se mueven las otras señales? Lado a lado, con y sin las dos nuevas: cuántas cruzan el umbral de 0,5 o cambian de opción.
sin, con = defaultdict(list), defaultdict(list)
for f in filas:
    if "a" in f:
        (con if f.get("con") else sin)[f["msg"]].append(f["a"])
cruces, total = 0, 0
for msg in sin:
    for x, y in zip(sin[msg], con[msg]):
        for k, v in x.items():
            w = y.get(k)
            total += 1
            if isinstance(v, (int, float)) and isinstance(w, (int, float)):
                if (v >= 0.5) != (w >= 0.5) and abs(v - w) > 0.1:
                    cruces += 1
                    print("  MUEVE", k, round(v, 2), round(w, 2), "|", msg[:60])
            elif v != w:
                cruces += 1
                print("  MUEVE", k, v, w, "|", msg[:60])
print(f"otras señales: {cruces} movidas de {total} lecturas")
