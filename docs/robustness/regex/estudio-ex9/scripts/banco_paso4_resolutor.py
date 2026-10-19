"""Segunda parte del banco del paso 4 de ex-9b: las respuestas al origen que, con `respuesta_corta_por_ia`, no resuelve la
respuesta de Jev (duda o no contestó) y tampoco trae el extractor van a la red anti-bucle del mismo turno, que pregunta
al resolutor LLM (`resolve_slot_answer`, la misma regla: delegar = Cartagena). Lee `banco-paso4-respuestas-cortas.json`
y solo llama al resolutor en esos casos (una llamada por caso).

Con red. Desde la raíz del repo:
    ENV_FILE=<repo>/.env.dev python docs/robustness/regex/estudio-ex9/scripts/banco_paso4_resolutor.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
os.chdir(REPO)
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")
from scripts.check_deploy import expected_from_compose  # noqa: E402
from src.config import settings  # noqa: E402

for _k, _v in expected_from_compose().items():
    if hasattr(settings, _k):
        setattr(settings, _k, _v)
from src.agents.jev_router import PENDING_ANSWER_MIN  # noqa: E402
from src.agents.llm_extractor import resolve_slot_answer  # noqa: E402

DATOS = Path(__file__).resolve().parents[1] / "banco-paso4-respuestas-cortas.json"


def _va_al_resolutor(caso: dict) -> bool:
    """Lo que hace la red anti-bucle con el origen pendiente: si Jev está seguro (>= umbral) vale lo suyo (también "no
    contesta"); si duda o no contestó, el resolutor LLM. Solo si la respuesta corta no se resolvió y el extractor no
    trajo el origen."""
    if caso["slot"] != "location" or caso["fin_del_turno"] != "(no se resuelve)":
        return False
    jev = caso["jev"]
    return jev is None or float(jev.split("@")[1]) < PENDING_ANSWER_MIN


async def main():
    datos = json.loads(DATOS.read_text(encoding="utf-8"))
    filas = []
    for caso in datos["casos"]:
        if not _va_al_resolutor(caso):
            continue
        r = await resolve_slot_answer("location", caso["msg"], lang="es")
        valor = r.get("value", "(no se resuelve)")
        filas.append({"msg": caso["msg"], "esperado": caso["esperado"], "jev": caso["jev"], "resolutor": valor,
                      "bien": valor == caso["esperado"]})
        print(f"{caso['msg'][:50]!r:54} quiero={caso['esperado']:16} jev={caso['jev']!s:16} resolutor={valor}")
    print(f"el resolutor acierta {sum(f['bien'] for f in filas)}/{len(filas)} (modelo {settings.resolutor_model})")
    datos["resolutor"] = filas
    DATOS.write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


asyncio.run(main())
