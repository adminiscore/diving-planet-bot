"""EX-EST-1 (14-oct): estabilidad del extractor "LLM primero" en el banco ex0.

Ronda flujo1-B: con temperatura 0, el mismo mensaje daba resultados distintos de una llamada a otra ("Buzos
certificados", "sin ir de Cartagena", la cita de "Frances"), y el juez atribuía esas variaciones a otros cambios. Aquí
cada caso del banco se pasa N veces (en paralelo, con tope de concurrencia) y se mide:
- estabilidad: % de casos que dan SIEMPRE el mismo resultado en los campos del banco;
- aciertos e inventos de la respuesta MÁS FRECUENTE de cada caso (con `puntuar_ex0`, la misma puntuación del banco);
- peor caso: aciertos e inventos si se toma, en cada caso, la peor de las N pasadas;
- latencia p50/p95 por llamada.

    ENV_FILE=.env.dev python -m scripts.estabilidad_extractor --grupo diseño --pasadas 5 [--modelo gpt-4.1]
        [--flag <flag>] [--coinciden 2]

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


# EXT-SALIDA (27-oct): para medir A/B desde una sola rama. «hoy» = el prompt de lat-6b (TODAS las claves y sus null,
# con `required`); «b» = todas repasadas en orden, pero escribiendo solo las que tienen dato; sin --variante, la del
# código («a»: solo las claves con dato).
_HOY_ES = ("\n\nResponde SOLO con un objeto JSON (sin texto antes ni después, sin ```), con TODAS las claves de "
           "este esquema (ninguna omitida, en este orden) y sus tipos. Cada dato es {\"valor\", \"cita\"} si el "
           "cliente lo afirma en su mensaje (aunque ya se supiera o parezca obvio: rellénalo con su cita) y null "
           "solo si no lo dice. Repasa el mensaje entero antes de dejar un dato en null:\n")
_HOY_EN = ("\n\nAnswer ONLY with a JSON object (no text before or after, no ```), with ALL the keys of this schema "
           "(none omitted, in this order) and their types. Each fact is {\"valor\", \"cita\"} if the customer "
           "states it in their message (even if it was already known or seems obvious: fill it in with the "
           "quote) and null only if they do not say it. Re-read the whole message before leaving a fact null:\n")
_B_ES = ("\n\nResponde SOLO con un objeto JSON (sin texto antes ni después, sin ```). Repasa, una a una y en este "
         "orden, TODAS las claves de este esquema contra el mensaje entero, pero escribe solo las que el cliente "
         "afirma, más \"idioma\" siempre, con sus tipos; las que no dice no se escriben (nada de null ni de listas "
         "vacías). Cada dato es {\"valor\", \"cita\"} (aunque ya se supiera o parezca obvio: escríbelo con su cita):\n")
_B_EN = ("\n\nAnswer ONLY with a JSON object (no text before or after, no ```). Go through ALL the keys of this "
         "schema, one by one and in this order, against the whole message, but write only the ones the customer "
         "states, plus \"idioma\" always, with their types; the ones they do not say are not written (no nulls, no "
         "empty lists). Each fact is {\"valor\", \"cita\"} (even if it was already known or seems obvious: write it "
         "with the quote):\n")


def _poner_variante(variante: str | None) -> None:
    from src.agents import extractor_turno as ex

    if variante == "hoy":
        ex._SOLO_JSON_ES, ex._SOLO_JSON_EN = _HOY_ES, _HOY_EN
        ex._esquema_del_prompt = lambda esquema: esquema
    elif variante == "b":
        ex._SOLO_JSON_ES, ex._SOLO_JSON_EN = _B_ES, _B_EN


async def _una(caso: dict, modelo: str | None, coinciden: int, tiempos: list[float],
               salidas: list[int] | None = None) -> dict:
    from src.agents.extractor_turno import extraer_turno

    sabido = caso.get("sabido") or {}

    async def llamada() -> dict:
        t0 = time.perf_counter()
        datos = await extraer_turno(caso["message"], history=caso.get("history"), sabido=sabido, lang=caso["lang"],
                                    modelo=modelo)
        tiempos.append(time.perf_counter() - t0)
        if salidas is not None and datos is not None and (extraer_turno.ultimo_uso or {}).get("salida"):
            # Sin await desde que extraer_turno lo puso: es el de esta llamada aunque haya otras a la vez.
            salidas.append(extraer_turno.ultimo_uso["salida"])
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
    _poner_variante(args.variante)
    casos = casos_ex0(args.grupo)
    sem = asyncio.Semaphore(args.concurrencia)
    tiempos: list[float] = []
    salidas: list[int] = []

    async def pasadas(caso):
        async with sem:
            return [await _una(caso, args.modelo, args.coinciden, tiempos, salidas) for _ in range(args.pasadas)]

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
    ts, sal = sorted(tiempos), sorted(salidas)
    resumen = {
        "modelo": args.modelo or settings.extractor_turno_model, "flags": args.flag or [], "pasadas": args.pasadas,
        "variante": args.variante or "a",
        "tokens_salida_p50": sal[len(sal) // 2] if sal else None,
        "tokens_salida_p90": sal[int(0.9 * len(sal))] if sal else None,
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
    p.add_argument("--variante", choices=("hoy", "a", "b"), default=None,
                   help="EXT-SALIDA: prompt de la salida del extractor (hoy = todas las claves con null; a = el del código)")
    return asyncio.run(main_async(p.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
