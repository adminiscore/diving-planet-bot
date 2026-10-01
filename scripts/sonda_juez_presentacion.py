"""Banco del flag `juez_presentacion` (1-oct): ¿el juez deja pasar la presentación oficial y sigue cazando inventos
parecidos sobre la empresa?

Motivo (ronda 2026-10-01-juez-B, docs/robustness/juez/README.md): el juez tiraba "30 años" y "PADI 5 estrellas",
que el bot tiene ORDENADO decir (`prompts/info.py` PRESENTACION_*), porque no las veía en su contexto.

Usa el juez de PRODUCCIÓN (`grounding_check.is_grounded`, con J2 si está encendido) y un contexto como el real: el
catálogo para el juez (`catalog.para_el_juez`) + links + un par de documentos. Cada caso N veces, sin y con la
presentación delante (lo que hace `rag_agent` con el flag). Criterio fijado ANTES de medir: con la presentación, los
casos ciertos pasan (>= 2 de 3) y NINGÚN invento pasa en ninguna repetición.

    python -m scripts.sonda_juez_presentacion            # ~60 llamadas al juez, ~1 $
"""
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

os.environ.setdefault("ENV_FILE", ".env.dev")
os.environ.setdefault("APP_ENV", "development")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.agents.grounding_check import is_grounded  # noqa: E402
from src.flows.catalog import catalog_booking_links, catalog_facts, para_el_juez  # noqa: E402
from src.prompts.info import JUEZ_PRESENTACION_EN, JUEZ_PRESENTACION_ES  # noqa: E402

N = 3
DOCS = {
    "es": ("Pregunta: ¿Como es el Curso Basico PADI (Open Water)? Respuesta: Curso de 2 dias: teoria online, piscina y 4 "
           "inmersiones. Dia 1: Muelle de la Bodeguita 8:00 a.m., noche en las islas (hotel no incluido).\n"
           "Pregunta: ¿Que medios de pago aceptan? Respuesta: Para extranjeros: 100% online con tarjeta, o presencial "
           "con tarjeta o efectivo."),
    "en": ("Question: What is the Basic PADI Course (Open Water) like? Answer: 2-day course: online theory, pool and 4 "
           "dives. Day 1: Muelle de la Bodeguita 8:00 a.m., night on the islands (hotel not included).\n"
           "Question: Which payment methods do you accept? Answer: For foreigners: 100% online by card, or in person "
           "by card or cash."),
}

# (idioma, respuesta, lo que DEBE decir el juez CON la presentación)
CASOS = [
    ("es", "¡Claro! Llevamos 30 años buceando en las Islas del Rosario y somos el primer centro PADI 5 Estrellas de Colombia.", "GROUNDED"),
    ("es", "Diving Planet tiene 30 años de experiencia en las Islas del Rosario. El curso básico PADI dura 2 días.", "GROUNDED"),
    ("es", "Somos un centro PADI 5 Estrellas. El curso básico para colombianos cuesta 2.450.000 COP online.", "GROUNDED"),
    ("en", "We've been diving the Rosario Islands for 30 years and we're Colombia's first PADI 5 Star Dive Center.", "GROUNDED"),
    ("es", "Llevamos 50 años buceando en las Islas del Rosario.", "HALLUCINATED"),
    ("es", "Somos el único centro PADI 5 Estrellas de toda Sudamérica.", "HALLUCINATED"),
    ("es", "Tenemos tres barcos propios y más de 20.000 buzos certificados.", "HALLUCINATED"),
    ("es", "Todos nuestros instructores tienen 30 años de experiencia.", "HALLUCINATED"),
    ("es", "Llevamos 30 años en las islas y el curso básico incluye el alojamiento en Isla Grande.", "HALLUCINATED"),
    ("en", "We've been operating for 30 years and we have a 100% safety record.", "HALLUCINATED"),
]


def contexto(lang: str, presentacion: bool) -> str:
    base = para_el_juez(catalog_facts(lang) + "\n" + catalog_booking_links(lang), lang) + "\n\n" + DOCS[lang]
    if not presentacion:
        return base
    return f"{JUEZ_PRESENTACION_ES if lang == 'es' else JUEZ_PRESENTACION_EN}\n\n{base}"


async def main() -> None:
    sem = asyncio.Semaphore(6)

    async def juzga(lang, ans, pres):
        async with sem:
            ok, why = await is_grounded(ans, contexto(lang, pres), lang=lang)
            return ("GROUNDED" if ok else "HALLUCINATED"), why

    filas = []
    for lang, ans, want in CASOS:
        lados = {}
        for pres in (False, True):
            res = await asyncio.gather(*(juzga(lang, ans, pres) for _ in range(N)))
            lados["con" if pres else "sin"] = {"aciertos": sum(r[0] == want for r in res),
                                               "veredictos": [r[0] for r in res], "motivo": res[0][1][:200]}
        filas.append({"lang": lang, "respuesta": ans, "debe": want, **lados})
        print(f"{want:12} sin {lados['sin']['aciertos']}/{N}  con {lados['con']['aciertos']}/{N}  | {ans[:80]}")

    ciertos = [f for f in filas if f["debe"] == "GROUNDED"]
    inventos = [f for f in filas if f["debe"] == "HALLUCINATED"]
    pasa = (all(f["con"]["aciertos"] >= 2 for f in ciertos) and all(f["con"]["aciertos"] == N for f in inventos))
    resumen = {
        "ciertos_que_pasan": {k: sum(f[k]["aciertos"] for f in ciertos) for k in ("sin", "con")},
        "inventos_cazados": {k: sum(f[k]["aciertos"] for f in inventos) for k in ("sin", "con")},
        "de": {"ciertos": N * len(ciertos), "inventos": N * len(inventos)}, "criterio_cumplido": pasa,
    }
    print(json.dumps(resumen, ensure_ascii=False))
    out = Path("docs/robustness/juez") / f"presentacion-{date.today().isoformat()}.json"
    out.write_text(json.dumps({"resumen": resumen, "casos": filas}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"→ {out}")


if __name__ == "__main__":
    asyncio.run(main())
