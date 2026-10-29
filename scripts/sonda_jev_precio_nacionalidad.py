"""CALN-3 (29-oct) sonda de Jev: «¿ese es el precio para colombianos?» daba pide_precio 0,64-0,68 (umbral 0,7) y no salían
los precios. ¿Lo coge `pide_precio` si se nombra que el precio sea el suyo (por nacionalidad o residencia), sin coger la
moneda («¿en dólares o pesos?», que es de pago) ni lo que no vendemos? Corre en dp-pre-bot con el código local
(`ENV_FILE=.env.dev python -m scripts.sonda_jev_precio_nacionalidad [N] [salida]`): A, la pregunta de hoy; B, la nueva;
N veces por mensaje, con todas las señales."""
import json
import sys

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

MENSAJES = [
    # el precio es el suyo (debe dar sí)
    "¿Ese es el precio para ciudadanos colombianos?",
    "¿Ese precio es para colombianos o para extranjeros?",
    "Somos colombianos, ¿nos sale igual?",
    "Is that the price for foreigners too?",
    "¿Y para residentes en Colombia cuánto es?",
    # de antes (deben seguir en sí)
    "hola cuanto cuesta bucear con ustedes?",
    "Al final vamos a estar alojados en Isla Grande, ¿cambia el precio?",
    "¿Y en pesos cuánto sería?",
    # moneda y pago (deben seguir en no)
    "¿El precio es en dólares o en pesos?",
    "¿Puedo pagar en pesos colombianos?",
    "Do you accept credit cards?",
    # lo que no vendemos y otras (deben seguir en no)
    "¿Cuánto cuesta la noche en el hotel de la isla?",
    "Somos colombianos y saldríamos desde Cartagena. ¿Tienen almuerzo incluido?",
    "¿Cuánto dura el minicurso?",
    "Mándame los links porfa",
]
NUEVA = (
    "The customer asks how much one of the dive center's activities costs: dive trips and dive packages, the dive "
    "mini-course or refresher, snorkeling, PADI courses and specialties (price, rate, cost, a quote), including "
    "asking that price again in another currency or for a different number of people, or asking whether that price "
    "changes (with another departure point, staying on the islands, another date or group size) or whether that price "
    "is the one that applies to them (for Colombians, residents or foreigners), even if the same message also asks "
    "other things. It is FALSE when they only ask the price of something the dive center does not sell (a hotel, a "
    "room or night, a taxi or transport), when they only ask in which currency they pay or which payment methods are "
    "accepted, and when they ask about duration, number of dives or how to book."
)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4

REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg, nueva):
    q = j._questions_for_turn(None)
    if nueva:
        q[j.PIDE_PRECIO] = {**q[j.PIDE_PRECIO], "instructions": NUEVA}
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
          f"NUEVA = {NUEVA!r}\nN = {N}\n{REMOTO}")
r = pre_ssh(docker_python(None, codigo_local=subir_codigo_local()), input_text=script, timeout=1800)
filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
if r.stderr:
    print(r.stderr[-1500:], file=sys.stderr)
out = sys.argv[2] if len(sys.argv) > 2 else "sonda-jev-precio-nacionalidad.jsonl"
open(out, "w", encoding="utf-8").write("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas))
print(f"{len(filas)} filas -> {out}")
