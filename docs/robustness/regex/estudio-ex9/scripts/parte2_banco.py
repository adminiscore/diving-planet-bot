"""Parte 2: solape regex / extractor (Haiku) en el banco ex0 (342 turnos etiquetados del golden VISIBLE).

- Regex de HOY (modo `regex` de scripts/run_extraction_eval, sin red) frente a las etiquetas, por campo.
- Extractor Haiku (PRE) frente a las etiquetas: del fichero ya medido estabilidad-mod2-cert-claude-haiku-5-5.json
  (grupo diseño, 200 casos, 3 pasadas, flag certificado_solo_si_lo_dice como en PRE). No se llama a ningún modelo.
- Cruce por caso y campo en diseño: ¿cuando Haiku pierde un dato, lo tenía el regex? ¿cuando el regex se inventa algo,
  lo evita Haiku?
Salida: out/parte2.json
"""
import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import comun  # noqa: E402

comun.bloquear_red()

from scripts.run_extraction_eval import CAMPOS_EX0, _turno_ex0, casos_ex0, puntuar_ex0  # noqa: E402
from src.agents.intent_detector import IntentDetector  # noqa: E402

BANCO = comun.REPO / "docs/robustness/regex/banco-ex0"


async def main():
    casos = casos_ex0("todos")
    det = IntentDetector()
    por_campo = {f: Counter() for f in CAMPOS_EX0}
    filas = {}
    for c in casos:
        prod = await _turno_ex0(c, "regex", det)
        r = puntuar_ex0(prod, c["expected"], c.get("sabido"))
        filas[c["id"]] = {"grupo": c["grupo"], "msg": c["message"], "esperado": c["expected"], "regex": prod, **r}
        for t, fs in r.items():
            for f in fs:
                por_campo[f][t] += 1
    tot = Counter()
    for f, v in por_campo.items():
        tot.update(v)
    esperados = tot["acierto"] + tot["equivocado"] + tot["perdido"]
    con_invento = sum(1 for x in filas.values() if x["inventado"])
    print(f"REGEX HOY, 342 casos: aciertos {tot['acierto']}/{esperados} ({tot['acierto'] / esperados:.1%}), "
          f"casos con invento {con_invento} ({con_invento / len(filas):.1%})")
    for f, v in por_campo.items():
        n = v["acierto"] + v["equivocado"] + v["perdido"]
        print(f"  {f:24} {v['acierto']:3}/{n:<3} equiv {v['equivocado']:2} perdido {v['perdido']:2} inventado {v['inventado']:2}")

    # Haiku (PRE) en diseño: los casos que no están en fallos_modales son correctos en todos sus campos.
    h = json.loads((BANCO / "estabilidad-mod2-cert-claude-haiku-5-5.json").read_text(encoding="utf-8"))
    fallos = {x["id"]: x for x in h["fallos_modales"]}
    print(f"\nHAIKU (PRE) diseño: modal {h['modal']}, flags {h['flags']}, estables {h['estables_pct']} %")
    cruce = defaultdict(Counter)
    ejemplos = defaultdict(list)
    for cid, x in filas.items():
        if x["grupo"] != "diseño":
            continue
        fh = fallos.get(cid, {"perdido": [], "equivocado": [], "inventado": [], "modal": None})
        for f in CAMPOS_EX0:
            esperado = f in x["esperado"]
            if esperado:
                hk = "haiku_ok" if f not in fh["perdido"] and f not in fh["equivocado"] else "haiku_mal"
                rx = "regex_ok" if f in x["acierto"] else "regex_mal"
                cruce[f][f"{hk}+{rx}"] += 1
                if hk == "haiku_mal" and rx == "regex_ok":
                    ejemplos[f"{f}: Haiku lo pierde y el regex lo tiene"].append(x["msg"][:120])
            else:
                hi = f in fh["inventado"]
                ri = f in x["inventado"]
                if hi or ri:
                    cruce[f][f"invento: haiku={hi} regex={ri}"] += 1
                    if ri and not hi:
                        ejemplos[f"{f}: el regex se lo inventa y Haiku no"].append(f"{x['msg'][:100]!r} -> {x['regex'].get(f)!r}")
                    if hi and not ri:
                        ejemplos[f"{f}: Haiku se lo inventa y el regex no"].append(f"{x['msg'][:100]!r} -> {fh.get('modal')!r}")
    print("\nCRUCE (diseño, 200 casos):")
    for f, c in cruce.items():
        print(f"  {f:24} {dict(c)}")
    for k, v in ejemplos.items():
        print(f"  * {k} ({len(v)}): {v[:3]}")
    out = {"regex_por_campo": {f: dict(v) for f, v in por_campo.items()}, "regex_total": dict(tot),
           "regex_casos_con_invento": con_invento, "casos": len(filas),
           "haiku_modal_diseno": h["modal"], "haiku_flags": h["flags"],
           "cruce_diseno": {f: dict(c) for f, c in cruce.items()}, "ejemplos": {k: v[:8] for k, v in ejemplos.items()},
           "filas": filas}
    (comun.OUT / "parte2.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


asyncio.run(main())
