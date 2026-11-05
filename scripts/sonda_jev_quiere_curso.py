"""Tanda s05a (5-nov, «Tres ya tenemos el Open Water» → el Curso Básico × 3; «Two of us already have our Advanced», 6 de 10 con el curso
en el reparto): ¿distingue Jev quien QUIERE HACER un curso de quien YA TIENE esa certificación? Corre en dp-pre-bot con el código local
(`ENV_FILE=.env.dev python -m scripts.sonda_jev_quiere_curso [N]`)."""
import json
import sys

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

MENSAJES = [
    # sí: quieren hacer un curso
    ("si", "Quiero hacer el curso Open Water en agosto"),
    ("si", "Hola, somos 5 de Cali. Dos ya tenemos el Open Water y tres quieren hacer el curso básico. ¿Cuánto cuesta?"),
    ("si", "We'd like to do the Advanced course next week"),
    ("si", "Tengo el Open Water y me gustaría sacar el Advanced"),
    ("si", "My son wants to get certified, I already have my Rescue"),
    ("si", "Queremos certificarnos, nunca hemos buceado"),
    ("si", "I'm Advanced and I want to take the Nitrox specialty"),
    ("si", "dos quieren el curso de Divemaster y yo solo bucear"),
    ("si", "¿Cuánto cuesta el curso Rescue?"),
    ("si", "¿El curso avanzado cuánto dura?"),
    # no: ya tienen la certificación
    ("no", "Hola, buen día. Somos un grupo de 7 amigas de Bogotá. Tres ya tenemos el Open Water, dos quieren probar el minicurso y dos prefieren snorkel. ¿Cuánto saldría por persona saliendo desde Cartagena y hay descuento por grupo?"),
    ("no", "Hello! We're a group of 6 friends from Medellín. Two of us already have our Advanced, two want to try the mini course and two prefer snorkeling. How much per person from Cartagena?"),
    ("no", "Somos dos buzos Advanced, queremos bucear el sábado"),
    ("no", "I hold a Rescue Diver certification and my wife has her Open Water"),
    ("no", "Tengo el Open Water hace años y quiero hacer dos inmersiones"),
    ("no", "Mi hija tiene el Junior Open Water y yo el Advanced; queremos salir a bucear"),
    ("no", "We are three Open Water divers and two snorkelers"),
    ("no", "Soy Divemaster, ¿me hacen descuento en las salidas?"),
    ("no", "Dos somos certificados PADI Open Water y el otro hará snorkel"),
    ("no", "quiero bucear certificado, somos 3"),
    ("no", "hola, cuanto cuesta el minicurso"),
    ("no", "queremos hacer snorkel"),
    ("no", "tengo la certificación SSI Open Water, ¿me sirve?"),
]
PREGUNTA = {
    "type": "noul",
    "instructions": (
        "The customer says that they or someone in their group wants to TAKE a certification course (Open Water, Advanced, "
        "Rescue, Divemaster or a specialty) to get a new certification, or asks about one of those courses. It is FALSE if "
        "they only say that they ALREADY HOLD a certification (\"we already have our Advanced\", \"tres ya tenemos el Open "
        "Water\", \"soy Divemaster\") and want to go diving, and if they only ask about dives, the mini-course or snorkeling."
    ),
}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 2
REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg):
    q = {**j._questions_for_turn(None), "quiere_curso": PREGUNTA}
    r = await client.post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                          json={"model": settings.jev_model, "state": j._estado_para_jev(msg, None), "questions": q}, timeout=30)
    r.raise_for_status()
    return r.json()["answers"]["quiere_curso"]["noul"]

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
