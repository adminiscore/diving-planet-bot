"""EX-EST-1 (14-oct): estabilidad del extractor "LLM primero" en el banco ex0.

Ronda flujo1-B: con temperatura 0, el mismo mensaje daba resultados distintos de una llamada a otra ("Buzos
certificados", "sin ir de Cartagena", la cita de "Frances"), y el juez atribuía esas variaciones a otros cambios. Aquí
cada caso del banco se pasa N veces (en paralelo, con tope de concurrencia) y se mide:
- estabilidad: % de casos que dan SIEMPRE el mismo resultado en los campos del banco;
- aciertos e inventos de la respuesta MÁS FRECUENTE de cada caso (con `puntuar_ex0`, la misma puntuación del banco);
- peor caso: aciertos e inventos si se toma, en cada caso, la peor de las N pasadas;
- latencia p50/p95 por llamada.

    ENV_FILE=.env.dev python -m scripts.estabilidad_extractor --grupo diseño --pasadas 5 [--modelo gpt-4.1]
        [--flag extractor_aclaraciones] [--coinciden 2]

`--coinciden 2`: modo "dos llamadas que tienen que coincidir": cada pasada lanza dos llamadas en paralelo y solo
se queda con los campos en los que coinciden (un campo en que no coinciden queda sin dato). Guarda el detalle en
docs/robustness/regex/banco-ex0/estabilidad-<etiqueta>.json. Solo diseño para decidir; el ciego, una vez al final.
"""
import argparse
import asyncio
import json
import sys
import time
from collections import Counter

from scripts.run_extraction_eval import BANCO_EX0, CAMPOS_EX0, casos_ex0, puntuar_ex0


def _clave(producido: dict) -> str:
    return json.dumps({k: producido.get(k) for k in CAMPOS_EX0 if producido.get(k) is not None},
                      sort_keys=True, ensure_ascii=False)


async def _una(caso: dict, modelo: str | None, coinciden: int, tiempos: list[float]) -> dict:
    from src.agents.extractor_turno import extraer_turno

    sabido = caso.get("sabido") or {}

    async def llamada() -> dict:
        t0 = time.perf_counter()
        datos = await extraer_turno(caso["message"], history=caso.get("history"), sabido=sabido, lang=caso["lang"],
                                    modelo=modelo)
        tiempos.append(time.perf_counter() - t0)
        return {f: v for f, v in (datos or {}).items() if v != sabido.get(f)}

    if coinciden <= 1:
        return await llamada()
    res = await asyncio.gather(*[llamada() for _ in range(coinciden)])
    return {k: v for k, v in res[0].items() if all(r.get(k) == v for r in res[1:])}


def _tot(filas: list[dict]) -> dict:
    t = Counter()
    for f in filas:
        for tipo in ("acierto", "equivocado", "perdido", "inventado"):
            t[tipo] += len(f[tipo])
    esperados = t["acierto"] + t["equivocado"] + t["perdido"]
    return {**t, "pct": round(100 * t["acierto"] / esperados, 1) if esperados else None,
            "casos_con_invento": sum(1 for f in filas if f["inventado"])}


async def main_async(args) -> int:
    from src.config import settings

    for flag in args.flag or []:
        setattr(settings, flag, True)
    casos = casos_ex0(args.grupo)
    sem = asyncio.Semaphore(args.concurrencia)
    tiempos: list[float] = []

    async def pasadas(caso):
        async with sem:
            return [await _una(caso, args.modelo, args.coinciden, tiempos) for _ in range(args.pasadas)]

    t0 = time.perf_counter()
    todas = await asyncio.gather(*[pasadas(c) for c in casos])
    estables, modal_filas, peor_filas, detalle, con_invento = 0, [], [], [], []
    for caso, res in zip(casos, todas, strict=True):
        cuenta = Counter(_clave(r) for r in res)
        modal = json.loads(cuenta.most_common(1)[0][0])
        estables += len(cuenta) == 1
        p_modal = puntuar_ex0(modal, caso["expected"], caso.get("sabido"))
        puntos = [puntuar_ex0(json.loads(_clave(r)), caso["expected"], caso.get("sabido")) for r in res]
        peor = min(puntos, key=lambda p: (len(p["acierto"]) - len(p["inventado"]) - len(p["equivocado"])))
        modal_filas.append(p_modal)
        peor_filas.append(peor)
        if p_modal["inventado"] or p_modal["equivocado"] or p_modal["perdido"]:
            con_invento.append({"id": caso["id"], "message": caso["message"][:160], "sabido": caso.get("sabido"),
                                "esperado": caso["expected"], "modal": modal, "inventado": p_modal["inventado"],
                                "equivocado": p_modal["equivocado"], "perdido": p_modal["perdido"]})
        if len(cuenta) > 1:
            detalle.append({"id": caso["id"], "message": caso["message"][:160], "esperado": caso["expected"],
                            "resultados": dict(cuenta)})
    ts = sorted(tiempos)
    resumen = {
        "modelo": args.modelo or settings.extractor_turno_model, "flags": args.flag or [], "pasadas": args.pasadas,
        "coinciden": args.coinciden, "grupo": args.grupo, "casos": len(casos),
        "estables_pct": round(100 * estables / len(casos), 1),
        "modal": _tot(modal_filas), "peor": _tot(peor_filas),
        "latencia_p50": round(ts[len(ts) // 2], 2) if ts else None,
        "latencia_p95": round(ts[int(0.95 * len(ts))], 2) if ts else None,
        "segundos": round(time.perf_counter() - t0),
    }
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    etiqueta = args.etiqueta or f"{resumen['modelo']}-{args.pasadas}x{'-coinciden' + str(args.coinciden) if args.coinciden > 1 else ''}"
    salida = BANCO_EX0 / f"estabilidad-{etiqueta.replace('/', '_')}.json"
    salida.write_text(json.dumps({**resumen, "inestables": detalle, "fallos_modales": con_invento}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"(detalle en {salida})")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--grupo", default="diseño")
    p.add_argument("--pasadas", type=int, default=5)
    p.add_argument("--modelo", default=None, help="modelo del extractor (por defecto settings.extractor_turno_model)")
    p.add_argument("--flag", action="append", help="flag de settings a encender (se puede repetir)")
    p.add_argument("--coinciden", type=int, default=1, help="llamadas en paralelo que tienen que coincidir (1 = una)")
    p.add_argument("--concurrencia", type=int, default=8)
    p.add_argument("--etiqueta", default=None)
    return asyncio.run(main_async(p.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
