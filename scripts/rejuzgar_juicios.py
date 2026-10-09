"""s4-33 (8-oct): re-juzgar con OTRO juez de grounding los juicios REALES que grabó `scripts/reproducir_juez_pre.py`.

Cada línea de esos JSONL trae, por turno, los juicios del juez de PRE con la respuesta y el contexto ENTERO que vio.
Aquí se juzgan otra vez las MISMAS respuestas con los mismos contextos y el juez que se quiera (modelo e
interruptores), y se listan los desacuerdos: así se compara un juez nuevo sin pagar conversaciones nuevas y sin el
ruido de que el bot redacte distinto. Los desacuerdos hay que LEERLOS: el juez de PRE no es la verdad.

    python -m scripts.rejuzgar_juicios <ficheros.jsonl...> --modelo gpt-6-luna --flag juez_v3_luna

Corre en local (`.env.dev`): la cuenta de OpenAI es la misma que la de PRE.
"""
import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")

from src.agents import grounding_check  # noqa: E402
from src.config import settings  # noqa: E402


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ficheros", nargs="+")
    ap.add_argument("--modelo", default=settings.grounding_v3_model)
    ap.add_argument("--flag", action="append", default=[], help="interruptor de settings a encender (repetible)")
    ap.add_argument("--concurrencia", type=int, default=6)
    ap.add_argument("--salida", help="JSONL con cada juicio entero (respuesta, contexto, los dos veredictos); para etiquetar")
    a = ap.parse_args()
    settings.grounding_v3_model = a.modelo
    for f in a.flag:
        setattr(settings, f, True)

    juicios = []
    for fichero in a.ficheros:
        for linea in Path(fichero).read_text(encoding="utf-8").splitlines():
            if linea.strip():
                fila = json.loads(linea)
                if "answer" in fila:  # formato plano (docs/robustness/juez/s4-33/juicios-reales-142.jsonl)
                    fila = {"turn": fila["origen"], "juicios": [{"ok": fila["ok_pre_gpt41"], **fila}]}
                for j in fila.get("juicios") or []:
                    juicios.append({"origen": f"{Path(fichero).stem} t{fila.get('turn')}", "lang":
                                    "en" if any(w in j["answer"].lower() for w in (" the ", " you ", " and ")) else "es",
                                    **j})
    sem = asyncio.Semaphore(a.concurrencia)

    async def uno(j: dict) -> None:
        async with sem:
            t = time.perf_counter()
            ok, motivo = await grounding_check.is_grounded(j["answer"], j["context"], j["lang"])
            j["nuevo_ok"], j["nuevo_motivo"], j["segundos"] = ok, motivo, time.perf_counter() - t

    await asyncio.gather(*(uno(j) for j in juicios))
    iguales = sum(j["ok"] == j["nuevo_ok"] for j in juicios)
    print(f"{len(juicios)} juicios · PRE rechaza {sum(not j['ok'] for j in juicios)} · nuevo ({a.modelo}, {a.flag}) "
          f"rechaza {sum(not j['nuevo_ok'] for j in juicios)} · de acuerdo {iguales} · "
          f"tiempo mediana {statistics.median(j['segundos'] for j in juicios):.2f}s")
    for j in juicios:
        if j["ok"] != j["nuevo_ok"]:
            print(f"\n[{'PRE aprueba, nuevo RECHAZA' if j['ok'] else 'PRE rechaza, nuevo APRUEBA'}] {j['origen']}")
            print(f"  respuesta: {j['answer'][:400]!r}")
            print(f"  PRE:   {(j.get('why') or '')[:300]}")
            print(f"  nuevo: {j['nuevo_motivo'][:300]}")
    if a.salida:
        Path(a.salida).write_text("".join(json.dumps(j, ensure_ascii=False) + "\n" for j in juicios), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
