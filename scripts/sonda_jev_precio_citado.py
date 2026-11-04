"""CALN-19 (4-nov), sonda de Jev: «los 5 buceos serían por 293 pagando en el website» no lleva interrogación y Jev no lo toma por
pregunta, así que el flujo contesta «¡Perfecto! 🙌» y su siguiente pregunta, y parece que da el precio por bueno. ¿Lo coge una
pregunta aparte, sin coger los números que no son dinero? Corre en dp-pre-bot con el código local
(`ENV_FILE=.env.dev python -m scripts.sonda_jev_precio_citado [N] [salida]`): N veces por mensaje, con `asks_question` y
`pide_precio` de hoy al lado, para ver si ya lo cogían."""
import json
import sys
from collections import defaultdict

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

# (mensaje, lo que debe contestar la pregunta nueva)
CASOS = [
    # cita un importe de un plan
    ("Veo q los 5 buceos serian por 293 pagando en el website", True),
    ("En la web vi el minicurso a 150 dólares", True),
    ("Me dijeron que el paquete de 5 inmersiones cuesta 300 dólares", True),
    ("Entonces me sale en 178 USD por persona", True),
    ("Una amiga pagó 120 dólares por las dos inmersiones el año pasado", True),
    ("A friend told me the two-dive trip is 120 USD", True),
    ("I saw online that the Open Water course is 400 dollars", True),
    ("The website says 99 USD for snorkeling", True),
    ("So that would be 250 for the two of us", True),
    ("Ok so 655.000 pesos each for the mini course", True),
    # números que no son dinero, y mensajes sin importe
    ("Somos 3 personas", False),
    ("Llegaría el 17 de abril y me iría el 20", False),
    ("Quiero quedarme en las islas", False),
    ("Mi última inmersión fue hace 2 años", False),
    ("I have about 50 logged dives", False),
    ("Tengo 30 años y mi hijo 14", False),
    ("We arrive on April 17 and leave on the 20th", False),
    ("Mi vuelo sale a las 8 de la mañana", False),
    ("Reservamos el paquete de 5 buceos", False),
    ("Estoy en el Hotel Cocoliso, habitación 293", False),
    ("Perfecto, muchas gracias", False),
    ("¿Cuánto cuesta el paquete de 5 inmersiones?", False),
    ("How much is the mini course?", False),
    ("We'd like to do 2 dives on Saturday", False),
]
NUEVA = (
    "The customer states a specific amount of money as the price of one of the dive center's activities or packages "
    "(seen on the website, told by someone, paid before, or worked out by them), even with no question mark. It is FALSE "
    "if they ask how much something costs without naming an amount, or if the numbers in the message are dates, ages, "
    "times, a room number, a number of people, of dives or of years, or if the message names no amount of money."
)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3

REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg):
    q = j._questions_for_turn(None)
    q["cita_precio"] = {"type": "noul", "instructions": NUEVA}
    r = await client.post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                          json={"model": settings.jev_model, "state": j._estado_para_jev(msg, None), "questions": q},
                          timeout=30)
    r.raise_for_status()
    a = r.json()["answers"]
    return {k: a[k].get("noul") for k in ("cita_precio", j.ASKS_QUESTION, j.PIDE_PRECIO) if k in a}

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
out = sys.argv[2] if len(sys.argv) > 2 else "sonda-jev-precio-citado.jsonl"
open(out, "w", encoding="utf-8").write("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas))

por = defaultdict(list)
for f in filas:
    if "a" in f:
        por[f["msg"]].append(f["a"])
aciertos = 0
for msg, debe in CASOS:
    vs = por.get(msg) or []
    cita = [v.get("cita_precio") or 0 for v in vs]
    bien = sum((c >= 0.7) == debe for c in cita)
    aciertos += bien
    pregunta = max((v.get("asks_question") or 0 for v in vs), default=0)
    precio = max((v.get("pide_precio") or 0 for v in vs), default=0)
    print(f"{'SI' if debe else 'no'} {bien}/{len(cita)} cita {min(cita, default=0):.2f}-{max(cita, default=0):.2f} "
          f"pregunta {pregunta:.2f} precio {precio:.2f} | {msg[:66]}")
print(f"TOTAL {aciertos}/{len(CASOS) * N}")
