"""CALN-30 (5-nov), sonda de Jev: «yo soy residente» dicho sin que se pregunte. `es_residente_colombia`: se dice residente legal en Colombia;
«vivo en Colombia» a secas no cuenta. Corre en dp-pre-bot con el código local
(`ENV_FILE=.env.dev python -m scripts.sonda_jev_residente [N] [salida]`)."""
import json
import sys
from collections import defaultdict

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

# (mensaje, es_residente)
CASOS = [
    ("Yo soy residente.", True),
    ("Soy residente en Colombia.", True),
    ("Hola, soy residente, ¿cuánto cuesta el minicurso?", True),
    ("Soy mexicano pero residente en Colombia.", True),
    ("I'm a resident of Colombia.", True),
    ("I'm a resident here in Cartagena, how much are two dives?", True),
    ("Soy residente colombiana y quiero bucear el sábado.", True),
    ("We're Open Water. I'm a resident, by the way.", True),
    ("Vivo en Colombia.", False),
    ("Vivo en Medellín desde hace tres años.", False),
    ("I live in Bogotá but I'm American.", False),
    ("I work in Cartagena for a few months.", False),
    ("Soy turista.", False),
    ("¿Los residentes pagan en pesos?", False),
    ("Do residents get a different price?", False),
    ("Mi hermana es residente en Colombia.", False),
    ("No soy residente.", False),
    ("Soy residente en Panamá.", False),
    ("I'm a resident of Texas.", False),
    ("Vivo aquí hace años pero no tengo cédula.", False),
    ("Soy colombiano.", False),
    ("Soy de Cali.", False),
    ("Tengo cédula de extranjería.", False),
    ("Hola, ¿cuánto cuesta el minicurso?", False),
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
    return r.json()["answers"][j.ES_RESIDENTE].get("noul")

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
out = sys.argv[2] if len(sys.argv) > 2 else "sonda-jev-residente.jsonl"
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
print(f"TOTAL es_residente {bien}/{len(CASOS) * N}")
