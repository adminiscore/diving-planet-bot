"""Mini de la 0.52 (4-nov; Gadea #3202), sonda de Jev: «Yo tengo extrangeria» tras una charla que ya habla de colombianos y
extranjeros lo leía el extractor como «soy extranjero». ¿Lo coge una pregunta de Jev (`tiene_cedula_extranjeria`), sin coger
a quien solo es extranjero, turista, no la tiene, pregunta en general o dice que la tiene otra persona? Frases nuestras. Corre
en dp-pre-bot con el código local (`ENV_FILE=.env.dev python -m scripts.sonda_jev_cedula [N] [salida]`)."""
import json
import sys
from collections import defaultdict

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

PREGUNTA = [{"role": "assistant", "content": "¿Eres colombiano o residente en Colombia? Así te doy el precio en la moneda que "
                                             "te corresponde."}]
# (mensaje, historia, lo que debe contestar)
CASOS = [
    ("Yo tengo extrangeria", PREGUNTA, True),
    ("Yo tengo extrangeria", None, True),
    ("Tengo la extranjería, vivo en Medellín hace 4 años", None, True),
    ("Soy venezolano, vivo en Cartagena hace 5 años y tengo cédula de extranjería. Mi esposa es colombiana.", None, True),
    ("I have a cédula de extranjería, I've lived in Bogotá for years", None, True),
    ("Soy argentina pero tengo extranjería", None, True),
    ("Sí, tengo cédula de extranjeria", PREGUNTA, True),
    ("tengo la cedula de extranjeria", None, True),
    ("Soy extranjero, de Chile", PREGUNTA, False),
    ("Somos turistas alemanes", None, False),
    ("No tengo cédula, soy español", None, False),
    ("¿Los extranjeros pagan en dólares?", None, False),
    ("Mi novia tiene cédula de extranjería, yo soy de México", None, False),
    ("Somos colombianos de Cali", None, False),
    ("¿Qué es la cédula de extranjería?", None, False),
    ("Is the price different for foreigners?", None, False),
    ("Vivo en Bogotá pero no tengo extranjería", None, False),
    ("Quiero reservar el minicurso", None, False),
]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3

REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg, historia, con):
    q = j._questions_for_turn(None)
    if not con:
        q.pop(j.TIENE_CEDULA)  # A: las preguntas de la base, para comparar el tiempo de Jev
    t0 = asyncio.get_event_loop().time()
    r = await client.post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                          json={"model": settings.jev_model, "state": j._estado_para_jev(msg, historia),
                                "questions": q}, timeout=30)
    r.raise_for_status()
    a = r.json()["answers"]
    return (a.get(j.TIENE_CEDULA) or {}).get("noul"), (a.get(j.GRUPO_MIXTO) or {}).get("noul"), asyncio.get_event_loop().time() - t0

async def main():
    async with httpx.AsyncClient() as c:
        for i, (msg, historia) in enumerate(CASOS):
            for rep in range(N):
                for con in ((True, False) if rep % 2 == 0 else (False, True)):
                    try:
                        p, mixto, s = await una(c, msg, historia, con)
                        print(json.dumps({"i": i, "rep": rep, "con": con, "a": p, "mixto": mixto, "s": round(s, 2)}),
                              flush=True)
                    except Exception as e:
                        print(json.dumps({"i": i, "rep": rep, "con": con, "error": str(e)[:200]}), flush=True)
asyncio.run(main())
'''

entrada = [(m, h) for m, h, _ in CASOS]
script = f"import json\nCASOS = json.loads({json.dumps(entrada, ensure_ascii=False)!r})\nN = {N}\n{REMOTO}"
r = pre_ssh(docker_python(None, codigo_local=subir_codigo_local()), input_text=script, timeout=900)
filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
if r.stderr and not filas:
    print(r.stderr[-1500:])
por_caso = defaultdict(list)
for f in filas:
    if f.get("con"):
        por_caso[f["i"]].append(f)
bien, total = 0, 0
for i, (msg, historia, esperado) in enumerate(CASOS):
    ps = [f.get("a") for f in por_caso[i] if f.get("a") is not None]
    aciertos = sum((p >= 0.7) == esperado for p in ps)
    bien, total = bien + aciertos, total + len(ps)
    print(f"{'✓' if aciertos == len(ps) == N else '✗'} {aciertos}/{len(ps)} esperado {esperado!s:5} "
          f"p={[round(p, 2) for p in ps]} {'(tras la pregunta) ' if historia else ''}{msg[:70]}")


def p50(xs):
    return sorted(xs)[len(xs) // 2] if xs else float("nan")


con = [f["s"] for f in filas if f.get("con") and "s" in f]
sin = [f["s"] for f in filas if f.get("con") is False and "s" in f]
errores = sum("error" in f for f in filas)
print(f"== {bien}/{total} · Jev p50 sin la pregunta {p50(sin):.2f} s → con ella {p50(con):.2f} s · errores {errores}")
if len(sys.argv) > 2:
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in filas))
