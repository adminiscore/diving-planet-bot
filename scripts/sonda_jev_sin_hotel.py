"""CALN-35 (5-nov, «todavía no tenemos hotel» recibía «¿desde dónde saldrías?»): ¿distingue Jev a quien aún no tiene dónde alojarse? Corre en
dp-pre-bot con el código local (`ENV_FILE=.env.dev python -m scripts.sonda_jev_sin_hotel [N]`)."""
import json
import sys

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

MENSAJES = [
    # sí: aún no tiene dónde alojarse
    ("si", "todavía no tenemos hotel"),
    ("si", "aún no tengo hotel"),
    ("si", "we haven't booked a hotel yet"),
    ("si", "no tengo hotel todavía, lo veo después"),
    ("si", "no sé aún dónde me voy a quedar"),
    ("si", "We don't have accommodation yet"),
    ("si", "no hemos reservado alojamiento"),
    ("si", "aún estamos mirando hoteles"),
    ("si", "primero quiero reservar el buceo y luego busco hotel"),
    ("si", "Still looking for a place to stay on the islands"),
    ("si", "no hotel yet"),
    ("si", "quiero bucear desde las islas pero aún no tengo dónde quedarme"),
    # no: lo tiene, pregunta por hoteles o le falta otra cosa
    ("no", "Ya reservamos en el Hotel Cocoliso"),
    ("no", "Me alojo en un Airbnb que se llama Casa Azul"),
    ("no", "En Isla Grande"),
    ("no", "estamos en el hotel Ubuntu"),
    ("no", "¿Qué hoteles me recomiendan?"),
    ("no", "Is accommodation included?"),
    ("no", "We're staying at the Hilton in Cartagena"),
    ("no", "salimos desde Cartagena"),
    ("no", "quiero bucear el sábado, somos 2"),
    ("no", "hola, cuánto cuesta el minicurso"),
    ("no", "no, buceé hace poco"),
    ("no", "no soy colombiano"),
    ("no", "no tengo certificación"),
    ("no", "no tengo equipo"),
    ("no", "todavía no he buceado nunca"),
    ("no", "aún no sé la fecha"),
    ("no", "¿El hotel tiene acceso por lancha?"),
    ("no", "no necesito hotel, vuelvo a Cartagena el mismo día"),
    ("no", "Vamos a dormir en Cartagena"),
    ("no", "ya tengo hotel"),
]
PREGUNTA = {
    "type": "noul",
    "instructions": (
        "The customer says that they do not have their accommodation yet: they have not booked or chosen a hotel or place to stay, "
        "or are still looking for one. It is FALSE if they name a hotel or place where they stay or say they already have one, if "
        "they only ask about hotels or whether accommodation is included, if they do not need accommodation, and if what they do "
        "not have yet is something else (a certification, equipment, a date)."
    ),
}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 2
REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg):
    q = {**j._questions_for_turn(None), "sin_hotel": PREGUNTA}
    r = await client.post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                          json={"model": settings.jev_model, "state": j._estado_para_jev(msg, None), "questions": q}, timeout=30)
    r.raise_for_status()
    return r.json()["answers"]["sin_hotel"]["noul"]

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
