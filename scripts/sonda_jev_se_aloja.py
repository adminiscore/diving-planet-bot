"""CALN-39 (5-nov, semana-santa: «¿ustedes cotizan los hoteles San Pedro y Cocoliso?» y luego el enlace «para San Pedro de Majagua»): ¿distingue Jev a quien
dice dónde se aloja de quien pregunta por un hotel? Corre en dp-pre-bot con el código local (`ENV_FILE=.env.dev python -m scripts.sonda_jev_se_aloja [N]`)."""
import json
import sys

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

MENSAJES = [
    # sí: dice dónde se aloja o se alojará
    ("si", "Ya reservamos en el Hotel Cocoliso"),
    ("si", "Me alojo en un Airbnb que se llama Casa Azul"),
    ("si", "estamos en el hotel Ubuntu"),
    ("si", "We're staying at Bora Bora"),
    ("si", "nos quedamos en San Pedro de Majagua"),
    ("si", "en el Ubuntu"),
    ("si", "Cocoliso"),
    ("si", "estaremos en el Ubuntu, ¿tiene lancha?"),
    ("si", "una noche en Coral Sand y la otra en Majagua"),
    ("si", "I booked the Mulata hotel for three nights"),
    # no: pregunta por hoteles, sin decir que se aloje
    ("no", "Ustedes cotizan los hoteles san pedro y cocoliso"),
    ("no", "¿Qué hoteles me recomiendan?"),
    ("no", "¿Cuál es mejor, Cocoliso o San Pedro?"),
    ("no", "Me pasas el contacto del hotel Cocoliso?"),
    ("no", "¿El Ubuntu tiene acceso por lancha?"),
    ("no", "todavía no tenemos hotel"),
    ("no", "Is Cocoliso close to the dive base?"),
    ("no", "estaba mirando el Hotel Mulata, ¿qué tal es?"),
    ("no", "Do you have rates for San Pedro de Majagua?"),
    ("no", "Me interesa, llegaría el 17 de abril y me iría el 20"),
    ("no", "quiero quedarme en las islas"),
]
PREGUNTA = {
    "type": "noul",
    "instructions": (
        "The customer says that they are staying or will stay at a specific named hotel or place, or answers which one it is. It is FALSE if "
        "they only ask about a hotel (its price, contact, access, or a recommendation), compare hotels, are still looking at one, say they "
        "have none yet, or only say that they will stay on the islands without naming where."
    ),
}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 2
REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg):
    q = {**j._questions_for_turn(None), "se_aloja": PREGUNTA}
    r = await client.post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                          json={"model": settings.jev_model, "state": j._estado_para_jev(msg, None), "questions": q}, timeout=30)
    r.raise_for_status()
    return r.json()["answers"]["se_aloja"]["noul"]

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
