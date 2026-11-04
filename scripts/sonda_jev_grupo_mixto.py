"""CALN-S04J (4-nov), sonda de Jev: «soy mexicana con cédula de extranjería y mi novio vive en México» no queda marcado como grupo
mixto (Haiku duda entre colombiana y no colombiana), y el escritor parte el pago: «tú en pesos, tu novio en dólares». ¿Lo coge
una pregunta de Jev, sin coger a quienes pagan todos igual (venezolano con cédula y esposa colombiana: todos en pesos)? Corre en
dp-pre-bot con el código local (`ENV_FILE=.env.dev python -m scripts.sonda_jev_grupo_mixto [N] [salida]`)."""
import json
import sys
from collections import defaultdict

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

# (mensaje, lo que debe contestar)
CASOS = [
    # mezclan a quien paga en pesos con quien paga en dólares
    ("Hola, soy mexicana y vivo en Bogotá desde hace tres años con cédula de extranjería. Mi novio vive en México y viene de "
     "visita. Los dos tenemos Open Water. ¿En qué moneda pagamos?", True),
    ("Mi pareja es colombiana y yo soy española, ¿en qué moneda pagamos?", True),
    ("We are two: I'm American and my wife is Colombian", True),
    ("Somos 4, dos colombianos y dos alemanes", True),
    ("I'm French and my girlfriend has Colombian nationality", True),
    ("Yo soy de Medellín y mi amiga viene de Chile a visitarme", True),
    ("My friend lives in Bogotá and has a cédula de extranjería, and I'm visiting from Canada", True),
    ("Vamos mi mamá, que es colombiana, y yo, que soy francés y vivo en París", True),
    # todos pagan en pesos
    ("Hola, soy venezolano, vivo en Cartagena hace 5 años y tengo cédula de extranjería. Mi esposa es colombiana.", False),
    ("Somos dos colombianos y vivimos en Bogotá", False),
    ("Somos tres amigas de Bogotá", False),
    ("Mi esposo y yo somos colombianos, pero vivimos en Miami", False),
    ("Tengo doble nacionalidad, colombiana y española", False),
    # todos pagan en dólares
    ("We're both Portuguese citizens and we don't have any Colombian ID", False),
    ("Soy chileno y viajo solo", False),
    ("Somos de Argentina, mi hermano y yo", False),
    ("Soy alemana y vivo en Bogotá, pero no tengo cédula. Mi novio también es alemán", False),
    ("We are a family of four from Texas", False),
    # sin grupo o sin nacionalidad
    ("¿Cuánto cuesta el minicurso?", False),
    ("Is the price the same for Colombians and foreigners?", False),
    ("¿Los colombianos pagan distinto que los extranjeros?", False),
    ("Somos 3 personas y queremos bucear el sábado", False),
    ("Quiero reservar el paquete de 5 inmersiones", False),
]
NUEVA = (
    "The customer says that the people booking together include BOTH someone who is Colombian or a resident of Colombia "
    "(holder of a cédula de extranjería) AND someone else who is a foreigner who is neither. It is FALSE if everyone in the "
    "group is Colombian or holds a cédula, if everyone is a foreigner, if they mention only one person, if they do not say "
    "where the people are from, and if they only ask a general question about prices for Colombians and foreigners."
)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3

REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg):
    q = j._questions_for_turn(None)
    q["grupo_mixto"] = {"type": "noul", "instructions": NUEVA}
    r = await client.post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                          json={"model": settings.jev_model, "state": j._estado_para_jev(msg, None), "questions": q},
                          timeout=30)
    r.raise_for_status()
    return r.json()["answers"]["grupo_mixto"].get("noul")

async def main():
    async with httpx.AsyncClient() as c:
        for msg in MENSAJES:
            for rep in range(N):
                try:
                    print(json.dumps({"msg": msg, "rep": rep, "a": await una(c, msg)}, ensure_ascii=False), flush=True)
                except Exception as e:
                    print(json.dumps({"msg": msg, "rep": rep, "error": str(e)[:200]}), flush=True)
asyncio.run(main())
'''

MENSAJES = [m for m, _ in CASOS]
script = (f"import json\nMENSAJES = json.loads({json.dumps(MENSAJES, ensure_ascii=False)!r})\n"
          f"NUEVA = {NUEVA!r}\nN = {N}\n{REMOTO}")
r = pre_ssh(docker_python(None, codigo_local=subir_codigo_local()), input_text=script, timeout=900)
filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
if r.stderr:
    print(r.stderr[-800:], file=sys.stderr)
out = sys.argv[2] if len(sys.argv) > 2 else "sonda-jev-grupo-mixto.jsonl"
open(out, "w", encoding="utf-8").write("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas))

por = defaultdict(list)
for f in filas:
    if "a" in f:
        por[f["msg"]].append(f["a"] or 0)
aciertos = 0
for msg, debe in CASOS:
    vs = por.get(msg) or []
    bien = sum((v >= 0.7) == debe for v in vs)
    aciertos += bien
    print(f"{'SI' if debe else 'no'} {bien}/{len(vs)} {min(vs, default=0):.2f}-{max(vs, default=0):.2f} | {msg[:80]}")
print(f"TOTAL {aciertos}/{len(CASOS) * N}")
