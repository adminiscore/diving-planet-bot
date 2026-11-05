"""#3300 (2b, 4-nov), sonda de Jev: «Entiendo, gracias. Entonces lo dejo para otra ocasión» recibía «¿Con cuál te animas?». `se_despide`:
el cliente deja la conversación o la aplaza sin fecha. Corre en dp-pre-bot con el código local
(`ENV_FILE=.env.dev python -m scripts.sonda_jev_se_despide [N] [salida]`)."""
import json
import sys
from collections import defaultdict

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

# (mensaje, se_despide)
CASOS = [
    ("Entiendo, gracias. Entonces lo dejo para otra ocasión.", True),
    ("Gracias, pero al final no vamos a reservar.", True),
    ("Ok, no thanks. Maybe next time.", True),
    ("Thanks, I'll pass for now.", True),
    ("Muchas gracias, hasta luego.", True),
    ("Perfect, thanks. Bye!", True),
    ("Entonces lo dejamos, gracias.", True),
    ("No me interesa, gracias.", True),
    ("That's too expensive for us, thanks anyway.", True),
    ("Lo dejo para el año que viene, gracias por todo.", True),
    ("Gracias por la información, que tengan buen día.", True),
    ("Vale, ya no me da tiempo este viaje. Otra vez será.", True),
    # Los controles que pidió Gadea (#3336)
    ("gracias, ¿y cuánto cuesta?", False),
    ("lo pienso y te digo mañana", False),
    ("perfecto, gracias", False),
    # Sigue hablando de la reserva
    ("Gracias. Somos 3 personas.", False),
    ("Thanks, and we're leaving from Cartagena.", False),
    ("No, no tengo certificación.", False),
    ("No gracias, prefiero el snorkel.", False),
    ("No thanks, not the package, just the 2 dives.", False),
    ("Perfecto, ¿cómo reservamos?", False),
    ("Ok", False),
    ("Sí, por favor.", False),
    ("Lo dejo para el sábado entonces, ¿me pasas el enlace?", False),
    ("I'll book tonight, thanks.", False),
    ("Gracias, una última cosa: ¿hay que llevar toalla?", False),
]

REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg):
    r = await client.post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                          json={"model": settings.jev_model, "state": j._estado_para_jev(msg, None), "questions": j._questions_for_turn(None)},
                          timeout=30)
    r.raise_for_status()
    return r.json()["answers"][j.SE_DESPIDE].get("noul")

async def main():
    async with httpx.AsyncClient() as c:
        for msg in MENSAJES:
            for rep in range(N):
                try:
                    print(json.dumps({"msg": msg, "rep": rep, "p": await una(c, msg)}, ensure_ascii=False), flush=True)
                except Exception as e:
                    print(json.dumps({"msg": msg, "rep": rep, "error": str(e)[:200]}), flush=True)
asyncio.run(main())
'''

N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
MENSAJES = [c[0] for c in CASOS]
script = f"import json\nMENSAJES = json.loads({json.dumps(MENSAJES, ensure_ascii=False)!r})\nN = {N}\n{REMOTO}"
r = pre_ssh(docker_python(None, codigo_local=subir_codigo_local()), input_text=script, timeout=900)
filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
if r.stderr:
    print(r.stderr[-800:], file=sys.stderr)
out = sys.argv[2] if len(sys.argv) > 2 else "sonda-jev-se-despide.jsonl"
open(out, "w", encoding="utf-8").write("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas))

por = defaultdict(list)
for f in filas:
    if f.get("p") is not None:
        por[f["msg"]].append(f["p"])
    elif "error" in f:
        print("ERROR", f["msg"][:40], f["error"][:120])
bien = 0
for msg, esperado in CASOS:
    ps = por.get(msg) or []
    aciertos = sum((p >= 0.7) == esperado for p in ps)
    bien += aciertos
    print(f"{'SI' if esperado else 'no'} {min(ps, default=0):.2f}-{max(ps, default=0):.2f} {aciertos}/{len(ps)} | {msg[:60]}")
print(f"TOTAL se_despide {bien}/{len(CASOS) * N}")
