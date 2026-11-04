"""CALN-25 (4-nov; aviso de Gonzalo, tanda s04k): «2 fun dives» salía como 2 días de buceo. `dive_counts_in` no lee la cita (la palabra
en medio), ni la regex de antes ni la marca de e24c1753. ¿Puede decidir `son_dias_de_buceo` sin mirar la cita? Aquí, lo que podría
romperse: planes que dicen sus días, y una cifra sola contestando a «¿cuántos días?». Descarta si p < 0,3
(`ENV_FILE=.env.dev python -m scripts.sonda_jev_dias_sin_cita [N]`)."""
import json
import sys
from collections import defaultdict

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

PREGUNTA = "¿Cuántos días quieres bucear?"
# (mensaje, último mensaje del bot o None, ¿son días?)
CASOS = [
    ("I want to book 2 fun dives for me", None, False),
    ("2 recreational dives please", None, False),
    ("Quiero 2 buceos recreativos", None, False),
    ("3 fun dives", None, False),
    ("Quiero hacer dos inmersiones de placer", None, False),
    ("I want to do 2 guided dives on Friday", None, False),
    ("We'd like two reef dives and lunch", None, False),
    ("Me apunto a las 2 inmersiones guiadas", None, False),
    ("The 3-day dive package please", None, True),
    ("Quiero el paquete de 2 días", None, True),
    ("El de 3 días de buceo", None, True),
    ("3 days", None, True),
    ("dos días", None, True),
    ("2 days of diving, thanks", None, True),
    ("Saturday and Sunday", None, True),
    ("We want to dive Saturday, Sunday and Monday", None, True),
    ("We'd like to dive twice, on Saturday and on Sunday", None, True),
    ("2", PREGUNTA, True),
    ("Tres", PREGUNTA, True),
    ("Solo dos", PREGUNTA, True),
]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3

REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg, previo):
    historia = [{"role": "assistant", "content": previo}] if previo else None
    r = await client.post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                          json={"model": settings.jev_model, "state": j._estado_para_jev(msg, historia),
                                "questions": j._questions_for_turn(None)}, timeout=30)
    r.raise_for_status()
    return r.json()["answers"][j.SON_DIAS_DE_BUCEO].get("noul")

async def main():
    async with httpx.AsyncClient() as c:
        for msg, previo, _ in CASOS:
            for rep in range(N):
                try:
                    print(json.dumps({"msg": msg, "a": await una(c, msg, previo)}, ensure_ascii=False), flush=True)
                except Exception as e:
                    print(json.dumps({"msg": msg, "error": str(e)[:200]}), flush=True)
asyncio.run(main())
'''

script = (f"import json\nCASOS = json.loads({json.dumps(CASOS, ensure_ascii=False)!r})\nN = {N}\n{REMOTO}")
r = pre_ssh(docker_python(None, codigo_local=subir_codigo_local()), input_text=script, timeout=600)
filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
if r.stderr:
    print(r.stderr[-800:], file=sys.stderr)
por = defaultdict(list)
for f in filas:
    if "a" in f:
        por[f["msg"]].append(f["a"] or 0)
bien = 0
for msg, previo, dias in CASOS:
    vs = por.get(msg) or []
    b = sum((v >= 0.3) == dias for v in vs)
    bien += b
    print(f"{'dias' if dias else 'no  '} {b}/{len(vs)} {min(vs, default=0):.2f}-{max(vs, default=0):.2f} | {msg[:50]}{' (tras «¿cuántos días?»)' if previo else ''}")
print(f"TOTAL {bien}/{len(CASOS) * N}")
