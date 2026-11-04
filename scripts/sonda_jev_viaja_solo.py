"""CALN-18 (4-nov), sonda de Jev: «¿para cuántas personas?» a quien habla de sí mismo. Dos preguntas: (a) `viaja_solo`: dice que va
solo («travelling alone» lo leía Haiku 2 de 3 veces y el bot volvía a preguntar); (b) `habla_de_si`: habla solo de sí mismo, sin
decir que va solo («Soy chileno y me gustaría sacar el Advanced»): no se da por hecho que vaya solo, pero se le pregunta
«¿es solo para ti o para más personas?». Corre en dp-pre-bot con el código local
(`ENV_FILE=.env.dev python -m scripts.sonda_jev_viaja_solo [N] [salida]`)."""
import json
import sys
from collections import defaultdict

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

# (mensaje, viaja_solo, habla_de_si)
CASOS = [
    ("I'm from Ireland and I'm travelling alone. Can I still dive with you?", True, True),
    ("Viajo solo y quiero bucear el sábado", True, True),
    ("Es solo para mí", True, True),
    ("Solo yo", True, True),
    ("Just me, thanks", True, True),
    ("Voy sola, ¿hay algún problema?", True, True),
    ("Hi, I'm a solo traveller looking for a dive on Friday", True, True),
    ("Soy chileno y me gustaría sacar el Advanced. ¿Cuánto dura?", False, True),
    ("Hola, ya tengo el Open Water y quiero bucear en enero", False, True),
    ("I'd like to book the mini course for next Tuesday", False, True),
    ("Hi, I got my certification 10 years ago. Do I need a refresher?", False, True),
    ("Me interesa el snorkel, ¿qué incluye?", False, True),
    ("We'd like to dive on Saturday", False, False),
    ("Queremos hacer el minicurso", False, False),
    ("Somos 3 amigas de Bogotá", False, False),
    ("Mi esposa y yo tenemos Open Water", False, False),
    ("Voy con mi novia y mi hermano", False, False),
    ("My husband is certified but I've never dived", False, False),
    ("Solo queremos la mañana", False, False),
    ("I can only dive in the morning", False, None),
    ("¿Cuánto cuesta el minicurso?", False, None),
    ("How much is it?", False, None),
    ("¿Un niño de 12 años puede bucear?", False, False),
]
SOLO = (
    "The customer says that they alone are going: only they will take part ('just me', 'I'm travelling alone', 'voy solo', "
    "'es solo para mí'). It is FALSE when they mention or imply anyone else coming, when 'only/solo' limits something else "
    "('solo la mañana', 'I can only dive in the morning'), and when they just talk about themselves without saying that "
    "nobody else is coming."
)
DE_SI = (
    "The customer speaks only about themselves in the first person singular ('I', 'me', 'yo', 'me gustaría', 'soy'), and "
    "mentions no one else who might come. It is FALSE if they speak in the plural ('we', 'somos', 'queremos') or mention "
    "anyone else (a partner, friends, family, children)."
)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3

REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg):
    q = j._questions_for_turn(None)
    q["viaja_solo"] = {"type": "noul", "instructions": SOLO}
    q["habla_de_si"] = {"type": "noul", "instructions": DE_SI}
    r = await client.post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                          json={"model": settings.jev_model, "state": j._estado_para_jev(msg, None), "questions": q},
                          timeout=30)
    r.raise_for_status()
    a = r.json()["answers"]
    return {k: a[k].get("noul") for k in ("viaja_solo", "habla_de_si")}

async def main():
    async with httpx.AsyncClient() as c:
        for msg in MENSAJES:
            for rep in range(N):
                try:
                    print(json.dumps({"msg": msg, "rep": rep, "a": await una(c, msg)}, ensure_ascii=False), flush=True)
                except Exception as e:
                    print(json.dumps({"msg": msg, "rep": rep, "error": str(e)[:200]}), flush=True)
asyncio.run(main())
'''

MENSAJES = [c[0] for c in CASOS]
script = (f"import json\nMENSAJES = json.loads({json.dumps(MENSAJES, ensure_ascii=False)!r})\n"
          f"SOLO = {SOLO!r}\nDE_SI = {DE_SI!r}\nN = {N}\n{REMOTO}")
r = pre_ssh(docker_python(None, codigo_local=subir_codigo_local()), input_text=script, timeout=900)
filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
if r.stderr:
    print(r.stderr[-800:], file=sys.stderr)
out = sys.argv[2] if len(sys.argv) > 2 else "sonda-jev-viaja-solo.jsonl"
open(out, "w", encoding="utf-8").write("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas))

por = defaultdict(list)
for f in filas:
    if "a" in f:
        por[f["msg"]].append(f["a"])
bien_solo = bien_si = cuenta_si = 0
for msg, solo, de_si in CASOS:
    vs = por.get(msg) or []
    a = [v.get("viaja_solo") or 0 for v in vs]
    b = [v.get("habla_de_si") or 0 for v in vs]
    bien_solo += sum((x >= 0.7) == solo for x in a)
    if de_si is not None:  # None: da igual (no habla de quién va)
        bien_si += sum((x >= 0.7) == de_si for x in b)
        cuenta_si += len(b)
    print(f"solo {'SI' if solo else 'no'} {min(a, default=0):.2f}-{max(a, default=0):.2f} | de_si {de_si!s:5} "
          f"{min(b, default=0):.2f}-{max(b, default=0):.2f} | {msg[:60]}")
print(f"TOTAL viaja_solo {bien_solo}/{len(CASOS) * N}; habla_de_si {bien_si}/{cuenta_si}")
