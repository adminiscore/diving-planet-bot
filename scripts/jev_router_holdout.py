"""l2-4 (paso 2b): Jev frente al router en mensajes que NO son de la bateria (2026-09-24).

La bateria (`battery_router_signals`, 37 casos) sirvio para ver DONDE falla Jev, y la
v2 de `jev_router_eval` arregla esas causas de forma general. Para no ajustar Jev a
esos 37 casos, aqui se mide con otros mensajes: todos los mensajes de cliente del
golden-set, SIN el examen oculto (`suite == "oculto"`, que no se mira al arreglar).

No hay etiquetas de senales para estos mensajes, asi que se compara Jev con el router
actual y se listan los DESACUERDOS para revisarlos a mano. El router tampoco es la
verdad (en la bateria fallaba "soy epileptica" 5 de 8 veces): cada desacuerdo se juzga.

Uso:  ENV_FILE=.env.dev python -m scripts.jev_router_holdout [--v1] [--bias] > salida.txt
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

from scripts import battery_activity_choice as bac
from scripts import battery_router_signals as brs
from scripts import jev_router_eval as jre

GOLDEN = Path("docs/robustness/golden-set/golden-dialogues.json")


def _messages() -> list[tuple[str, str, str]]:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    seen, out = set(), []
    for d in data["dialogues"]:
        if d.get("suite") == "oculto" or "turns" not in d:  # los de lotes guardan los turnos en batches.json
            continue
        lang = (d.get("cobertura") or {}).get("idioma") or "es"
        lang = "en" if str(lang).startswith("en") else "es"
        for i, t in enumerate(d["turns"]):
            msg = t if isinstance(t, str) else (t.get("text") or t.get("msg") or "")
            if msg and msg not in seen:
                seen.add(msg)
                out.append((f"{d['id']}#{i + 1}", lang, msg))
    return out


async def main():
    questions = jre._questions(v2="--v1" not in sys.argv)
    key = jre._key() if hasattr(jre, "_key") else None
    if not key:
        import os

        from dotenv import dotenv_values
        key = (dotenv_values(os.environ.get("ENV_FILE", ".env")).get("OPENROUTER_API_KEY") or "").strip()
    bac._restore()
    msgs = _messages()
    rows, lat_j, lat_r = [], [], []
    jre.QUESTIONS.clear()
    jre.QUESTIONS.update(questions)
    async with httpx.AsyncClient() as client:
        for mid, lang, msg in msgs:
            ans, ms_j, _ = await jre._jev(client, key, msg)
            got, ms_r = await jre._router(msg, lang)
            j = brs._signals(jre._to_signals(ans, 0.5, jre.BIAS_THRESHOLD if "--bias" in sys.argv else None))
            r = brs._signals(got)
            lat_j.append(ms_j)
            lat_r.append(ms_r)
            rows.append({"id": mid, "lang": lang, "msg": msg, "jev": brs._show(j), "router": brs._show(r),
                         "igual": brs._show(j) == brs._show(r)})
    iguales = sum(r["igual"] for r in rows)
    print(f"{len(rows)} mensajes (sin examen oculto) · coinciden {iguales} · desacuerdos {len(rows) - iguales}")
    print(f"latencia p50 jev {jre.statistics.median(lat_j):.0f} ms · router {jre.statistics.median(lat_r):.0f} ms\n")
    for r in rows:
        if not r["igual"]:
            print(f"{r['id']} [{r['lang']}] «{r['msg'][:140]}»\n    jev    {r['jev']}\n    router {r['router']}")
    print("JSON " + json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
