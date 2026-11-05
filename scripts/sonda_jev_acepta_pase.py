"""5-nov (Gadea #3570; panel visto-6940, tanda s05f 6952), sonda de Jev: el escritor ofrece pasar con un asesor y el cliente acepta
añadiendo algo («Yes, please. Thank you for your help.»); el «sí» solo se reconocía si el mensaje era SOLO la afirmación.
`acepta_el_pase`: el último mensaje del asistente ofreció una persona y el cliente acepta. Frases nuestras, cada una con lo que
acaba de decir el asistente. Corre en dp-pre-bot con el código local
(`ENV_FILE=.env.dev python -m scripts.sonda_jev_acepta_pase [N] [salida]`)."""
import json
import sys
from collections import defaultdict

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

OFERTA_ES = [{"role": "assistant", "content": "Como es un Airbnb fuera de nuestra lista de hoteles, un asesor debe confirmar la "
                                              "recogida antes de que reserves. ¿Quieres que te pase con un asesor para confirmarla?"}]
OFERTA_EN = [{"role": "assistant", "content": "A different return date needs to be arranged with a team advisor. Would you like me to "
                                              "connect you with one?"}]
SIN_OFERTA = [{"role": "assistant", "content": "¡Perfecto! 🙌 ¿Para cuántas personas sería: solo para ti o van más? 😊"}]
# (mensaje, lo que dijo el asistente, lo que debe contestar)
CASOS = [
    ("Sí, por favor. La casa se llama Casa Brisa Coralina, tiene muelle propio.", OFERTA_ES, True),
    ("Yes, please. Thank you for your help.", OFERTA_EN, True),
    ("sí", OFERTA_ES, True),
    ("Dale, pásame con el asesor", OFERTA_ES, True),
    ("Sí por favor, ¿y cuánto sería el anticipo?", OFERTA_ES, True),
    ("Yes please, and could they also check my suitcase?", OFERTA_EN, True),
    ("Perfecto, gracias, que me escriban", OFERTA_ES, True),
    ("That would be great, thanks!", OFERTA_EN, True),
    ("No, gracias, prefiero reservar yo por la web", OFERTA_ES, False),
    ("Todavía no, primero dime el precio", OFERTA_ES, False),
    ("¿Y el almuerzo está incluido?", OFERTA_ES, False),
    ("Somos 3 personas", OFERTA_ES, False),
    ("Not now, thanks.", OFERTA_EN, False),
    ("I'll think about it and come back later.", OFERTA_EN, False),
    ("Sí, por favor", SIN_OFERTA, False),
    ("Sí, somos dos", SIN_OFERTA, False),
    ("Yes please send me the link", SIN_OFERTA, False),
    ("Gracias, eso es todo", SIN_OFERTA, False),
]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3

REMOTO = r'''
import asyncio, json, httpx
from src.config import settings
from src.agents import jev_router as j

async def una(client, msg, historia):
    r = await client.post(j.JEV_URL, headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                          json={"model": settings.jev_model, "state": j._estado_para_jev(msg, historia),
                                "questions": j._questions_for_turn(None)}, timeout=30)
    r.raise_for_status()
    a = r.json()["answers"]
    return (a.get(j.ACEPTA_EL_PASE) or {}).get("noul"), (a.get("wants_human") or {}).get("noul")

async def main():
    async with httpx.AsyncClient() as c:
        for i, (msg, historia) in enumerate(CASOS):
            for rep in range(N):
                try:
                    p, humano = await una(c, msg, historia)
                    print(json.dumps({"i": i, "rep": rep, "a": p, "wants_human": humano}), flush=True)
                except Exception as e:
                    print(json.dumps({"i": i, "rep": rep, "error": str(e)[:200]}), flush=True)
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
    por_caso[f["i"]].append(f)
bien, total = 0, 0
for i, (msg, historia, esperado) in enumerate(CASOS):
    ps = [f.get("a") for f in por_caso[i] if f.get("a") is not None]
    humanos = [f.get("wants_human") for f in por_caso[i] if f.get("wants_human") is not None]
    aciertos = sum((p >= 0.7) == esperado for p in ps)
    bien, total = bien + aciertos, total + len(ps)
    contexto = "oferta" if historia is not SIN_OFERTA else "sin oferta"
    print(f"{'✓' if aciertos == len(ps) == N else '✗'} {aciertos}/{len(ps)} esperado {esperado!s:5} p={[round(p, 2) for p in ps]} "
          f"wants_human={[round(h, 2) for h in humanos]} ({contexto}) {msg[:60]}")
print(f"== {bien}/{total} · errores {sum('error' in f for f in filas)}")
if len(sys.argv) > 2:
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in filas))
