"""s05d (5-nov, «dos salidas de un día» recibía la tarjeta del paquete de 5): ¿distingue Jev a quien quiere salidas sueltas de un día de quien quiere
un paquete? Corre en dp-pre-bot con el código local (`ENV_FILE=.env.dev python -m scripts.sonda_jev_salidas_sueltas [N]`)."""
import json
import sys

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

MENSAJES = [
    # sí: salidas sueltas de un día, sin paquete
    ("si", "Preferiríamos dormir en Cartagena: ¿podemos hacer dos salidas de un día, ida y vuelta cada día, en vez del paquete?"),
    ("si", "We'd rather sleep in Cartagena. Could we do two separate one-day trips instead of a package?"),
    ("si", "queremos dos salidas de un día, sin dormir en las islas"),
    ("si", "no queremos el paquete, mejor dos días sueltos ida y vuelta"),
    ("si", "Can we just book the one-day trip twice?"),
    ("si", "mejor hacemos la salida de 2 inmersiones el sábado y otra el domingo, volviendo a Cartagena cada día"),
    ("si", "I don't want to stay overnight on the islands, I'd do a day trip on Monday and another on Tuesday"),
    ("si", "¿se puede reservar la salida de un día dos veces en lugar del paquete de dos días?"),
    # no: paquete, un solo día u otra cosa
    ("no", "Queremos hacer dos días de buceo saliendo desde Cartagena"),
    ("no", "We'd like the two-day package with 4 dives from Cartagena"),
    ("no", "quiero el paquete de 5 inmersiones"),
    ("no", "queremos dormir en las islas y bucear dos días"),
    ("no", "solo queremos un día de buceo"),
    ("no", "two dives on Saturday"),
    ("no", "somos 6 amigos, ¿tienen descuento de grupo?"),
    ("no", "¿cuánto cuesta el paquete de dos días?"),
    ("no", "What does the day trip include?"),
    ("no", "¿A qué hora vuelve la lancha a Cartagena?"),
    ("no", "Nos alojamos en Cartagena y queremos bucear"),
    ("no", "hola, cuánto cuesta el minicurso"),
]
PREGUNTA = {
    "type": "noul",
    "instructions": (
        "The customer wants to dive on several days as SEPARATE one-day trips, each a same-day round trip, instead of a multi-day package "
        "or sleeping on the islands. It is FALSE if they want a multi-day package, want to stay on the islands, want a single day, or only "
        "say how many days they want to dive without saying that they want separate one-day trips."
    ),
}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 2
REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg):
    q = {**j._questions_for_turn(None), "salidas_sueltas": PREGUNTA}
    r = await client.post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                          json={"model": settings.jev_model, "state": j._estado_para_jev(msg, None), "questions": q}, timeout=30)
    r.raise_for_status()
    return r.json()["answers"]["salidas_sueltas"]["noul"]

async def main():
    async with httpx.AsyncClient() as c:
        for tipo, msg in MENSAJES:
            print(json.dumps({"tipo": tipo, "msg": msg, "p": [round(await una(c, msg), 2) for _ in range(N)]}, ensure_ascii=False), flush=True)
asyncio.run(main())
'''
script = (f"import json\nMENSAJES = json.loads({json.dumps(MENSAJES, ensure_ascii=False)!r})\nPREGUNTA = {PREGUNTA!r}\nN = {N}\n{REMOTO}")
r = pre_ssh(docker_python(None, codigo_local=subir_codigo_local()), input_text=script, timeout=900)
if r.stderr:
    print(r.stderr[-600:], file=sys.stderr)
for ln in (r.stdout or "").splitlines():
    if ln.startswith("{"):
        f = json.loads(ln)
        print(f["tipo"], f["p"], f["msg"][:80])
