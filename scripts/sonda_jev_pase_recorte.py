"""¿Ve Jev la oferta del asesor cuando va al final de un mensaje largo del bot? `_estado_para_jev` da a Jev los 400 PRIMEROS
caracteres de cada mensaje anterior. Con los mensajes reales de visto-6940 (t4 → «Yes, please…») y 6952 (t1 → «Sí, por favor…»):
el contexto como hoy, frente al mismo mensaje cortado por el final (los 400 últimos). Sin cambiar el código: el recorte va en la
historia que se pasa. `ENV_FILE=.env.dev python -m scripts.sonda_jev_pase_recorte [N]`"""
import json
import sys
from pathlib import Path

from scripts.pre_access import docker_python, pre_ssh, subir_codigo_local

RAIZ = Path(__file__).resolve().parent.parent


def respuesta(fichero: Path, clave: str, valor, turno: int) -> str:
    for ln in fichero.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            f = json.loads(ln)
            if f.get(clave) == valor and (f.get("turn") or f.get("turno")) == turno:
                return f["reply"]
    raise SystemExit(f"no está {valor} t{turno} en {fichero}")


bot_6952 = respuesta(Path("C:/t/wt-059/docs/robustness/g3/charlas/6952.jsonl"), "conv", 6952, 1)
bot_6940 = respuesta(Path("C:/t/wt-pj/docs/robustness/caln/panel/059c.jsonl"), "dialogo", "visto-6940", 4)
CASOS = [
    ("6952 t2", "Sí, por favor. La casa se llama Casa Brisa Coralina, está cerca del muelle del pueblo de Isla Grande, "
                "tiene un pequeño muelle propio. Soy de Chile, mi última inmersión fue en agosto", bot_6952),
    ("6940 t5", "Yes, please. Thank you for your help.", bot_6940),
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
        for nombre, msg, bot in CASOS:
            for modo, contenido in (("hoy", bot), ("final", bot[-400:])):
                for rep in range(N):
                    p, h = await una(c, msg, [{"role": "assistant", "content": contenido}])
                    print(json.dumps({"caso": nombre, "modo": modo, "rep": rep, "acepta": p, "wants_human": h}), flush=True)
asyncio.run(main())
'''
script = f"import json\nCASOS = json.loads({json.dumps(CASOS, ensure_ascii=False)!r})\nN = {N}\n{REMOTO}"
r = pre_ssh(docker_python(None, codigo_local=subir_codigo_local()), input_text=script, timeout=600)
filas = [json.loads(ln) for ln in (r.stdout or "").splitlines() if ln.startswith("{")]
if not filas:
    print((r.stderr or "")[-1500:])
for nombre, _msg, bot in CASOS:
    print(f"{nombre}: el mensaje del bot tiene {len(bot)} caracteres; la oferta está en los 400 primeros: "
          f"{'asesor' in bot[:400].lower() or 'advisor' in bot[:400].lower()}")
    for modo in ("hoy", "final"):
        fs = [f for f in filas if f["caso"] == nombre and f["modo"] == modo]
        print(f"   {modo:5} acepta={[round(f['acepta'], 2) for f in fs]} wants_human={[round(f['wants_human'], 2) for f in fs]}")
