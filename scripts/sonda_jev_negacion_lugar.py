"""CALN-3 (29-oct) sonda de Jev: «Va quiero comprar sin ir de cartagena» daba customer_place none seguro, y con el
extractor leyendo island saltaba la confirmación del origen («¿ya estarás en las islas?»), que el juez cuenta como
repregunta (paquete-5-buceos-islas-residente-sin-recogida, en PRE y en la 5.ª). ¿Lo coge `customer_place` si el criterio
de las islas nombra la negación, sin mover los demás? Corre en dp-pre-bot con el código local
(`ENV_FILE=.env.dev python -m scripts.sonda_jev_negacion_lugar [N] [salida]`): A, la pregunta de hoy; B, la nueva."""
import json
import sys

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

MENSAJES = [
    # niega salir de Cartagena (debe dar islands)
    "Va quiero comprar sin ir de cartagena",
    "Queremos bucear sin salir de Cartagena, ¿se puede?",
    "No vamos a pasar por Cartagena, queremos hacerlo directo desde la isla",
    "We'd like to dive without going back to Cartagena",
    # controles (no deben moverse)
    "Estoy interesada en bucear el lunes festivo en islas del rosario. Que precio tiene?",
    "estamos en Cartagena, ¿cuánto cuesta?",
    "vamos a estar alojados en Isla Grande",
    "No queremos ir a las islas a dormir, volvemos a Cartagena el mismo día",
    "Estaremos visitando Cartagena la próxima semana",
    "¿Dónde es el punto de encuentro en Cartagena?",
    "hola cuanto cuesta bucear con ustedes?",
    "Nos quedamos en Barú, en un hotel de playa",
]
EXTRA = (" Also when they say they will NOT set out from or go through Cartagena (\"sin ir de Cartagena\", \"without "
         "going back to Cartagena\"): then they will already be on the islands.")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4

REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg, nueva):
    q = j._questions_for_turn(None)
    if nueva:
        lugar = q[j.CUSTOMER_PLACE]
        q[j.CUSTOMER_PLACE] = {**lugar, "criteria": {**lugar["criteria"], "islands": lugar["criteria"]["islands"] + EXTRA}}
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
                for nueva in (False, True):
                    try:
                        print(json.dumps({"msg": msg, "rep": rep, "variante": "B" if nueva else "A",
                                          "a": await una(c, msg, nueva)}, ensure_ascii=False), flush=True)
                    except Exception as e:
                        print(json.dumps({"msg": msg, "rep": rep, "error": str(e)[:200]}), flush=True)
asyncio.run(main())
'''

script = (f"import json\nMENSAJES = json.loads({json.dumps(MENSAJES, ensure_ascii=False)!r})\n"
          f"EXTRA = {EXTRA!r}\nN = {N}\n{REMOTO}")
r = pre_ssh(docker_python(None, codigo_local=subir_codigo_local()), input_text=script, timeout=1800)
filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
if r.stderr:
    print(r.stderr[-1500:], file=sys.stderr)
out = sys.argv[2] if len(sys.argv) > 2 else "sonda-jev-negacion-lugar.jsonl"
open(out, "w", encoding="utf-8").write("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas))
print(f"{len(filas)} filas -> {out}")
