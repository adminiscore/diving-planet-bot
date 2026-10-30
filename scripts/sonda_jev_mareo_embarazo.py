"""Sparring s30a-05 (30-oct) sonda de Jev: sensitive_topic sin la exclusión del mareo y el embarazo (A) y con ella, la del código (B
). `ENV_FILE=.env.dev python <este> [N] [salida]` desde la carpeta del repo."""
import json
import sys

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

MENSAJES = [
    # mareo (con B debe dar none)
    "Un amigo se marea mucho en barco, ¿es un problema?",
    "Bonjour! Nous sommes 3 amis français à Cartagena et on voudrait faire du snorkeling demain. Un de nous a le mal de mer, c'est un problème? Comment on réserve?",
    "I get seasick easily, is the boat ride long?",
    "Mi hija se marea en la lancha, ¿qué nos recomiendan?",
    # embarazo (con B debe dar none)
    "Estoy embarazada de 3 meses, ¿puedo hacer snorkel?",
    "My wife is pregnant, can she snorkel while I dive?",
    # médicas (deben seguir en medical_questions)
    "Tengo asma, ¿puedo bucear?",
    "I had heart surgery last year, can I do the mini course?",
    "Tomo medicación para la tensión, ¿puedo bucear?",
    "¿Puedo tomar pastillas para el mareo antes de bucear?",
    # dieta y nada sensible (none)
    "Una de nosotras es celíaca, ¿qué puede comer?",
    "¿Cuánto cuesta el snorkel desde Cartagena?",
    "¿Qué pasa si llueve ese día?",
]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4

REMOTO = r'''
import asyncio, json, httpx
MAREO = (" Do NOT use 'medical_questions' for SEASICKNESS on the boat (getting seasick, mareo, mal de mer): the trip tips "
         "answer it (seasickness tablets if they are prone to it), normal catalog information, and it must be left 'none' "
         "here, unless they ask whether a medication or a medical condition affects diving.")
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg, sin):
    q = j._questions_for_turn(None)
    if sin:
        from src.prompts import router
        q["sensitive_topic"] = {**q["sensitive_topic"],
                                "instructions": q["sensitive_topic"]["instructions"].replace(router._MAREO_Y_EMBARAZO_NO_SON_MEDICOS, "")}
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
out = sys.argv[2] if len(sys.argv) > 2 else "sonda-jev-mareo.jsonl"
open(out, "w", encoding="utf-8").write("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas))
print(f"{len(filas)} filas -> {out}")
