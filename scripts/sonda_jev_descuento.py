"""CALN-3 (28-oct) sonda de Jev (CALN3-Q05): ¿la pregunta nueva pide_un_descuento mueve las otras señales de Jev? Corre en dp-pre-bot con el
código local (`ENV_FILE=.env.dev python -m scripts.sonda_jev_descuento [N] [salida]`): las mismas preguntas del turno con y sin ella, N veces por mensaje, y compara cada señal."""
import json
import sys

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

MENSAJES = [
    # descuento concreto (debe dar sí)
    "Entonces el descuento de grupo nos aplica o no? Somos 5",
    "Si llevo mi propio equipo completo, ¿me hacen descuento?",
    "Is the group discount valid for the mini course?",
    "¿Por ser colombianos tenemos algún descuento?",
    # descuento general (debe dar no)
    "¿Tienen algún descuento?",
    "Do you have any discounts?",
    "Hola, somos 5 amigos de Madrid y queremos sacarnos el Open Water. Precio por persona y si nos hacéis descuento de grupo",
    # sin descuento (las otras señales no deben moverse)
    "hola cuanto cuesta bucear con ustedes?",
    "Somos 3 y se suma mi primo, ¿cuánto sería?",
    "Al final vamos a estar alojados en Isla Grande, ¿cambia el precio?",
    "ya reservamos, ¿a qué hora es y dónde nos recogen?",
    "Can we move our dive to Friday instead?",
    "I'd do the 2 dives and she the mini course. Is the equipment included? What would be the total for both of us?",
    "Mándame los links porfa",
    "Mi hijo tiene 9 años, ¿puede hacer el minicurso?",
    "¿Qué pasa si llueve ese día?",
]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4

REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg, sin):
    q = j._questions_for_turn(None)
    if sin:
        q.pop(j.PIDE_UN_DESCUENTO, None)
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
                for sin in (True, False):
                    try:
                        print(json.dumps({"msg": msg, "rep": rep, "variante": "A" if sin else "B",
                                          "a": await una(c, msg, sin)}, ensure_ascii=False), flush=True)
                    except Exception as e:
                        print(json.dumps({"msg": msg, "rep": rep, "error": str(e)[:200]}), flush=True)
asyncio.run(main())
'''

script = f"MENSAJES = {json.dumps(MENSAJES, ensure_ascii=False)!r}\nMENSAJES = __import__('json').loads(MENSAJES)\nN = {N}\n{REMOTO}"
r = pre_ssh(docker_python(None, codigo_local=subir_codigo_local()), input_text=script, timeout=1800)
filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
if r.stderr:
    print(r.stderr[-1500:], file=sys.stderr)
out = sys.argv[2] if len(sys.argv) > 2 else "sonda-jev-descuento.jsonl"
open(out, "w", encoding="utf-8").write("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas))
print(f"{len(filas)} filas -> {out}")
