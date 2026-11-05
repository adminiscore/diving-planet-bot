"""CALN-37 (5-nov): «queremos bucear desde las islas, ya estaremos allí» o «snorkel desde Cartagena» recibían «Entonces, ¿…?»: Jev no llegaba al mínimo
de `customer_place`. ¿Qué dicen `customer_place` y `affirms_location` de quien lo afirma y de quien solo lo plantea? Corre en dp-pre-bot con el código
local (`ENV_FILE=.env.dev python -m scripts.sonda_jev_origen_dicho [N]`)."""
import json
import sys

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

MENSAJES = [
    # lo afirma: las islas
    ("si", "Hola, somos 2 buzos certificados y queremos bucear desde las islas del Rosario, ya estaremos allí"),
    ("si", "We'll be on the Rosario Islands and want to do the mini course, two of us"),
    ("si", "Estaré en las islas del Rosario y quiero hacer el minicurso. ¿Puedo reservar el buceo y ya luego veo el hotel?"),
    ("si", "Soy colombiana y quiero hacer snorkel desde las islas, estaré allá la próxima semana"),
    ("si", "Buena Tardes quería preguntarte estaremos en islas del rosario en junio y quería regalarle a mi esposo una experiencia del buceo"),
    ("si", "Buenas. Soy español, tengo el título de Advanced y estaré unos días en las Islas del Rosario el mes que viene. Aún no tengo hotel, pero querría dejar ya reservadas 2 inmersiones."),
    # lo afirma: Cartagena
    ("si", "Hola, somos dos colombianos de Medellín y queremos hacer snorkel desde Cartagena el sábado."),
    ("si", "Hi! I'm German and I'd like to do the mini course from Cartagena."),
    ("si", "Hola! Nací en Colombia pero vivo en Madrid desde pequeña. ¿Cuánto cuesta el snorkel desde Cartagena? ¿Pago en pesos?"),
    ("si", "Hola, qué pena molestar. Somos una pareja de Medellín, los dos buzos Open Water. Queremos un paquete que tenga buceo nocturno saliendo desde Cartagena. ¿Qué opciones hay y se puede dejar un anticipo?"),
    ("si", "We're two certified divers staying in Cartagena. I'd like 4 dives over 2 days, how much is it?"),
    ("si", "Hola, soy venezolano, vivo en Cartagena hace 5 años y tengo cédula de extranjería. Queremos hacer el minicurso los dos."),
    ("si", "Hola! Vamos a estar en Cartagena la semana que viene con la familia. Mi marido y yo buceamos."),
    # no lo afirma: hipótesis o sitio de buceo
    ("no", "What if I decide to stay one day longer in rosario, can you provide details?"),
    ("no", "¿Y si nos quedamos a dormir una noche más en las islas, nos traen de vuelta a Cartagena al día siguiente?"),
    ("no", "Could we stay overnight on the Rosario Islands after the dive and come back the next day?"),
    ("no", "Quiero bucear en las Islas del Rosario, ¿cuánto cuesta?"),
    ("no", "I'd love to snorkel in the Rosario Islands next week. How much is it?"),
    ("no", "Estoy interesada en bucear el lunes festivo en islas del rosario. Que precio tiene?"),
    ("no", "buenas! somos unos amigos de Medellín y queremos hacer snorkel en las islas este puente. cuánto vale?"),
    ("no", "Is there anything shorter we could do that gets us back by 3 pm? Or could we go from the islands somehow?"),
    ("no", "¿Dónde es el punto de encuentro en Cartagena?"),
    ("no", "What if we leave from Cartagena instead, would it be cheaper?"),
    ("no", "Vamos a ir a las islas del Rosario a bucear, ¿qué planes tienen?"),
    ("no", "Queremos ir a Isla Grande a bucear la próxima semana"),
    ("no", "We're going to visit the Rosario Islands, can we dive there?"),
    ("no", "Me gustaría hacer snorkel en las islas en junio"),
    ("no", "¿Se puede volver de las islas a Cartagena en la lancha de ustedes?"),
    ("no", "Nos quedamos en Barú, en un hotel de playa"),
    ("si", "Salimos desde Cartagena"),
    ("si", "Estamos alojados en Isla Grande. ¿Cuánto cuesta el snorkel?"),
    ("si", "We're already on the islands, in a small guesthouse on Isla Grande."),
]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
# Variante: lo que quien lo afirma dice con otras palabras. La A es la pregunta de hoy.
EXTRA_C = (" Wanting or asking for an activity from Cartagena (\"saliendo desde Cartagena\", \"from Cartagena\") also counts: it is where they set out from.")
EXTRA_I = (" Saying that they will be there (\"estaré en las islas\", \"we'll be on the islands\", \"desde las islas, ya estaremos allí\") also counts. Wanting to go to, "
           "visit, dive or snorkel in the islands does not.")
REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg, nueva):
    q = j._questions_for_turn(None)
    if nueva:
        lugar = q[j.CUSTOMER_PLACE]
        criterios = dict(lugar["criteria"])
        criterios["cartagena"] += EXTRA_C
        criterios["islands"] += EXTRA_I
        q[j.CUSTOMER_PLACE] = {**lugar, "criteria": criterios}
    r = await client.post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                          json={"model": settings.jev_model, "state": j._estado_para_jev(msg, None), "questions": q}, timeout=30)
    r.raise_for_status()
    lugar = r.json()["answers"][j.CUSTOMER_PLACE]
    return lugar.get("choice"), round(lugar.get("confidence") or 0, 2)

async def main():
    async with httpx.AsyncClient() as c:
        for tipo, msg in MENSAJES:
            print(json.dumps({"tipo": tipo, "msg": msg, "a": [await una(c, msg, False) for _ in range(N)], "b": [await una(c, msg, True) for _ in range(N)]}, ensure_ascii=False), flush=True)
asyncio.run(main())
'''
cabeza = [f"MENSAJES = json.loads({json.dumps(MENSAJES, ensure_ascii=False)!r})", f"EXTRA_C = {EXTRA_C!r}", f"EXTRA_I = {EXTRA_I!r}", f"N = {N}"]
script = "\n".join(["import json", *cabeza, REMOTO])
r = pre_ssh(docker_python(None, codigo_local=subir_codigo_local()), input_text=script, timeout=900)
if r.stderr:
    print(r.stderr[-600:], file=sys.stderr)
for ln in (r.stdout or "").splitlines():
    if ln.startswith("{"):
        f = json.loads(ln)
        print(f["tipo"], "A", " ".join(f"{a[:3]}{b:.2f}" for a, b in f["a"]), "| B", " ".join(f"{a[:3]}{b:.2f}" for a, b in f["b"]), f["msg"][:60])
