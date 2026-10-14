"""EX-EST-2 (14-oct): banco del revisor de grounding (el juez que decide si una respuesta del RAG está respaldada).

Ronda flujo1-B: el RAG escribió datos que contradicen la base y el revisor los dejó pasar ("en ambos casos la recogida
en lancha está incluida", "el Curso Referido exige pernocte", la opción de 3 buceos sin COP). Aquí, respuestas cortas
con el MISMO contexto que ve el revisor en PRE (catálogo + políticas): la mitad correctas, la mitad con un error
sembrado que contradice la base. Mide:
- errores que se escapan (respuesta con error sembrado que el revisor da por buena);
- rechazos injustos (respuesta correcta que el revisor rechaza; con la revisión con cita, EX-RAG-3, como en PRE).

    ENV_FILE=.env.dev python -m scripts.banco_revisor [--pasadas 3]
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

CASOS = [
    # (respuesta, ¿correcta?, qué contradice si no lo es)
    ("Si ya estás alojado en las Islas del Rosario y tu hotel tiene acceso marítimo, la recogida y el regreso en "
     "lancha están incluidos sin cargo adicional.", True, None),
    ("En ambos casos, saliendo desde Cartagena o desde las islas, la recogida en lancha desde tu hotel está incluida.",
     False, "la recogida en el hotel solo es para quien ya está en las islas"),
    ("Pagan en pesos colombianos los colombianos y los residentes en Colombia; el precio es el mismo, solo cambia la "
     "moneda.", True, None),
    ("Los colombianos tienen un 10% de descuento adicional por ser colombianos.", False,
     "no hay descuento por ser colombiano"),
    ("Hay que esperar al menos 18 horas para volar después de bucear, y 12 horas después del minicurso.", True, None),
    ("Después de bucear puedes volar a las 6 horas sin problema.", False, "18 h / 12 h"),
    ("El alojamiento no está incluido en los planes y se reserva directamente con el hotel.", True, None),
    ("El paquete de 5 inmersiones incluye una noche de alojamiento en Isla Grande.", False,
     "ningún plan incluye alojamiento"),
    ("Si han pasado más de 2 años desde tu última inmersión, se requiere un refresher antes de bucear.", True, None),
    ("El refresher solo se exige si han pasado más de 5 años desde tu última inmersión.", False, "más de 2 años"),
    ("Operamos todos los días del año excepto el 25 de diciembre y el 1 de enero.", True, None),
    ("Los domingos no hay salidas de buceo.", False, "operamos todos los días salvo 25-dic y 1-ene"),
    ("Las actividades y los cursos se dan en español y en inglés.", True, None),
    ("También damos los cursos en francés y en portugués.", False, "solo español e inglés"),
    ("En la lancha se puede llevar una mochila o un bolso por persona.", True, None),
    ("En la lancha puedes llevar tu maleta grande sin problema.", False, "una mochila o bolso; la maleta, con asesor"),
    ("Para el paquete de 5 inmersiones se requiere certificación Open Water como mínimo.", True, None),
    ("El paquete de 5 inmersiones lo puede hacer cualquier persona, aunque no esté certificada.", False,
     "requiere certificación"),
    ("Si el grupo mezcla colombianos y extranjeros, toda la reserva se paga en dólares.", True, None),
    ("En un grupo mixto, los colombianos pagan en pesos y los extranjeros en dólares.", False,
     "grupo mixto: todo en USD"),
]


async def main_async(pasadas: int) -> int:
    from src.agents.grounding_check import is_grounded
    from src.config import settings
    from src.flows.catalog import catalog_facts, para_el_juez, policies_facts

    contexto = para_el_juez(catalog_facts("es") + "\n\n" + policies_facts("es"), "es")
    escapados, injustos, filas = 0, 0, []
    for respuesta, correcta, motivo in CASOS:
        res = await asyncio.gather(*[is_grounded(respuesta, contexto, lang="es") for _ in range(pasadas)])
        pasa = [ok for ok, _ in res]
        if correcta:
            injustos += pasa.count(False)
        else:
            escapados += pasa.count(True)
        filas.append({"respuesta": respuesta, "correcta": correcta, "contradice": motivo, "pasa": pasa})
        marca = "ok " if all(p == correcta for p in pasa) else "MAL"
        print(f"{marca} {'correcta' if correcta else 'ERROR   '} pasa={sum(pasa)}/{pasadas} | {respuesta[:80]}")
    n_err = sum(1 for _, c, _ in CASOS if not c) * pasadas
    n_ok = sum(1 for _, c, _ in CASOS if c) * pasadas
    resumen = {"pasadas": pasadas, "errores_escapados": f"{escapados}/{n_err}", "rechazos_injustos": f"{injustos}/{n_ok}",
               "juez_revisa_con_cita": settings.juez_revisa_con_cita, "modelo": settings.grounding_v3_model}
    print(json.dumps(resumen, ensure_ascii=False))
    out = Path("docs/robustness/juez/banco-revisor-resultado.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({**resumen, "filas": filas}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pasadas", type=int, default=3)
    return asyncio.run(main_async(p.parse_args(argv).pasadas))


if __name__ == "__main__":
    sys.exit(main())
