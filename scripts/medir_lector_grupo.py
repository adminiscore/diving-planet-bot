"""CALN-2, paso 1 del lector del grupo (diseño `docs/robustness/caln/diseno-caln2-lector-grupo.md`; Gadea #2231): mide el
lector SOLO, sin enchufarlo, con llamadas directas (sin PRE).

    python scripts/medir_lector_grupo.py llamar-aciertos N   # guarda las llamadas (extractor y lector a la vez)
    python scripts/medir_lector_grupo.py llamar-turnos       # guarda el extractor en cada turno (y el lector si salta)
    python scripts/medir_lector_grupo.py releer              # solo el lector otra vez, sobre lo guardado
    python scripts/medir_lector_grupo.py puntuar             # las tablas, sin llamar, por disparador (T1, T2a, T2b)

`aciertos`: el primer turno de los casos de un turno de banco-grupo (lo esperado es el del banco) y de la batería y
banco-lectura (lo esperado, a mano, abajo). Por llamada corren a la vez el extractor y el lector, como irían en el turno;
se mide cada uno y lo que el lector sumaría al turno (si acaba después del extractor).
`turnos`: el extractor (N=1) en cada turno de usuario de los diálogos VISIBLES de la última ronda (nunca los del
oculto: se filtran por `suite`) y de las charlas de la 2.ª tanda de la batería; cuenta en cuántos saltaría el lector, y
el p95 de esos turnos hoy y con el lector.
"""
from __future__ import annotations

import asyncio
import glob
import json
import sys
import time
from collections import Counter
from pathlib import Path

from src.agents import extractor_turno as ex
from src.agents import lector_grupo as lg

ROOT = Path(__file__).resolve().parent.parent
BANCO_GRUPO = ROOT / "docs/robustness/caln/banco-grupo.json"
GOLDEN = ROOT / "docs/robustness/golden-set/golden-dialogues.json"
RONDA = ROOT / "docs/robustness/synthetic-runs/2026-10-27-caln3-B.jsonl"
CHARLAS = ROOT / "docs/robustness/g3/charlas-rama"
SEM = asyncio.Semaphore(6)

# Lo esperado en el PRIMER turno, a mano: total, decididos (la regla de negocio pone el buceo a quien es certificado y
# quiere bucear), cuántos sin decidir y cuántos certificados. Frases nuestras (batería y banco-lectura).
A_MANO = [
    ("b1", "es", "Hola! Vamos a pasar unos días en Cartagena. Mi esposo y yo somos Advanced, nuestro hijo de 11 nunca ha "
     "buceado y mi suegra viene con nosotros pero no se mete al agua. ¿Qué nos recomiendas y cuánto cuesta?",
     4, {"companion": 1}, 3, 2),
    ("b5", "es", "Hola! Yo tengo el Open Water y quiero bucear. Mi esposo no bucea y vamos con los niños, de 7 y 4 años. "
     "Estamos alojados en Cartagena. ¿Qué podemos hacer todos?", 4, {"certified_diving": 1}, 3, 1),
    ("b6", "es", "Hola, somos 6 amigos de Bogotá: 4 tenemos certificación y 2 dudan entre el minicurso y el snorkel. "
     "Salimos desde Cartagena el sábado. ¿Qué precio nos dan por ser grupo?", 6, {}, 6, 4),
    ("l01", "en", "Hello! I'm Advanced Open Water and my girlfriend has never been underwater. We're staying in Cartagena "
     "for a few days.", 2, {}, 2, 1),
    ("l02", "en", "Hi there, two of us coming to Cartagena: my brother holds a PADI Open Water card, I'm a total beginner.",
     2, {}, 2, 1),
    ("l03", "es", "Hola, mi pareja y yo vamos a Cartagena. Yo soy Open Water y ella nunca ha buceado.", 2, {}, 2, 1),
    ("l04", "en", "Hi! My wife and I will be in Cartagena next month. I'm a certified diver and I want to do the 2 dives. "
     "She's never dived.", 2, {"certified_diving": 1}, 1, 1),
    ("l05", "es", "Hola! Vamos dos amigos a Cartagena. Yo tengo el Advanced y quiero bucear las 2 inmersiones. Mi amigo "
     "nunca ha buceado.", 2, {"certified_diving": 1}, 1, 1),
    ("l06", "es", "Buenas! Somos 3 de Pereira. Mi primo tiene la certificación de buzo y nosotras dos queremos hacer "
     "snorkel. Salimos desde Cartagena.", 3, {"snorkel": 2}, 1, 1),
    ("l07", "en", "Hi! Three of us from Toronto, leaving from Cartagena. My cousin is a certified diver and the two of us "
     "want to go snorkeling.", 3, {"snorkel": 2}, 1, 1),
    ("l08", "es", "Hola, somos 3 de Cali. Mi hermano es buzo certificado y mi esposa y yo queremos hacer snorkel. Salimos "
     "desde Cartagena.", 3, {"snorkel": 2}, 1, 1),
    ("l10", "en", "Hi, there are three of us leaving from Cartagena. My sister is a certified diver, and my husband and I "
     "want to snorkel.", 3, {"snorkel": 2}, 1, 1),
]


def _lang(msg: str) -> str:
    return "en" if any(w in msg.lower().replace("!", " ").replace(",", " ").split()
                       for w in ("i", "we", "my", "hi", "the", "hello")) else "es"


def casos() -> list[tuple]:
    """(id, lang, mensaje, total, decididos, sin_decidir, certificados); None = no se mira."""
    out = list(A_MANO)
    for d in json.load(open(BANCO_GRUPO, encoding="utf-8"))["dialogos"]:
        if len(d["turnos"]) != 1:
            continue
        g = d.get("grupo") or {}
        out.append((d["id"].split("-")[0], _lang(d["turnos"][0]), d["turnos"][0], g.get("total", "?"),
                    g.get("decididos"), g.get("sin_decidir"), None))
    return out


# --- A: lo que deja el extractor (como el código de hoy, en grueso) ------------------------------------------------

def _sin(reparto: dict | None) -> dict:
    return {a: n for a, n in (reparto or {}).items() if a != "undecided" and isinstance(n, int) and n > 0}


def lectura_a(x: dict) -> dict:
    """total, decididos, sin_decidir y certificados con lo del extractor. Sin reparto, el grupo hace la actividad de
    quien escribe salvo que otro no esté certificado (`grupo.sin_certificar_no_hereda`)."""
    reparto, total, act = x.get("group_allocation"), x.get("group_size"), x.get("activity")
    if reparto:
        decididos = _sin(reparto)
        total = total or sum(n for n in reparto.values() if isinstance(n, int)) or None
    elif act:
        decididos = {act: 1 if (x.get("otro_sin_certificar") or not total) else total}
    else:
        decididos = {}
    sin = (total - sum(decididos.values())) if isinstance(total, int) else (reparto or {}).get("undecided")
    return {"total": total, "decididos": decididos, "sin": sin, "cert": 1 if x.get("is_certified") else 0}


DISPARADORES = ("T1", "T2a", "T2b")


def salta(x: dict, antes: dict | None = None, variante: str = "T1") -> bool:
    """¿Llamaría el turno al lector? T1: el mensaje habla de otras personas y el grupo no queda completo con lo del
    extractor (ni con lo sabido antes del turno). T2a: también si queda alguien sin elegir (su certificación decide la
    recomendación: b6, l06-l10). T2b: también cualquier grupo de 2 o más sin reparto (g28: «my friend… not sure»)."""
    antes = antes or {}
    reparto = x.get("group_allocation") or antes.get("group_allocation")
    total = x.get("group_size") or antes.get("group_size")
    actividad = x.get("activity") or antes.get("activity")
    otros = bool(x.get("edades") or x.get("otro_sin_certificar") or x.get("otro_certificado_inactivo")
                 or (x.get("group_allocation") and (len(x["group_allocation"]) > 1
                                                    or "undecided" in x["group_allocation"]
                                                    or "companion" in x["group_allocation"]))
                 or (isinstance(x.get("group_size"), int) and x["group_size"] > 1))
    if not otros:
        return False
    if not isinstance(total, int):
        return True
    if reparto and sum(n for n in reparto.values() if isinstance(n, int)) != total:
        return True
    if not reparto and (x.get("otro_sin_certificar") or x.get("edades")):
        return True
    if variante == "T1" or total < 2:
        return False
    if (reparto or {}).get("undecided") or (not reparto and not actividad):
        return True
    return variante == "T2b" and not reparto


def lectura_b(x: dict, lec: dict | None) -> dict:
    """Con el lector: rellena lo que el extractor dejó vacío y la certificación de cada uno. La regla de negocio
    (certificado y quiere bucear = buceo certificado) vale para quien escribe, uno, como en el extractor."""
    a = lectura_a(x)
    if not lec or not lec["personas"]:
        return a
    cert = sum(p["cantidad"] for p in lec["personas"] if p["certificado"] is True)
    reparto = x.get("group_allocation")
    dicho = x.get("group_size")
    if reparto and isinstance(dicho, int) and sum(n for n in reparto.values() if isinstance(n, int)) == dicho:
        return {**a, "cert": cert}  # el reparto del extractor está completo: manda; el lector solo da la certificación
    decididos = Counter()
    for p in lec["personas"]:
        act = p["actividad"]
        if act is None and p["quien"] == "cliente" and x.get("quiere_bucear") and x.get("is_certified"):
            decididos["certified_diving"] += 1
            continue
        if act:
            decididos[act] += p["cantidad"]
    total = x.get("group_size") or lg.total_de(lec)
    sin = (total - sum(decididos.values())) if isinstance(total, int) else None
    return {"total": total, "decididos": dict(decididos), "sin": sin, "cert": cert}


def bien(pred: dict, total, decididos, sin, cert) -> dict:
    return {"total": total == "?" or pred["total"] == total,
            "reparto": (decididos is None or pred["decididos"] == decididos) and (sin is None or pred["sin"] == sin),
            "cert": cert is None or pred["cert"] == cert}


def invento(pred: dict, total, decididos) -> bool:
    """Más personas que las dichas, o una actividad que nadie eligió."""
    if isinstance(total, int) and isinstance(pred["total"], int) and pred["total"] > total:
        return True
    return decididos is not None and any(n > decididos.get(a, 0) for a, n in pred["decididos"].items())


async def _t(coro):
    t0 = time.perf_counter()
    r = await coro
    return r, time.perf_counter() - t0


async def _par(msg, lang, history=None, sabido=None):
    async with SEM:
        (x, tx), (lec, tl) = await asyncio.gather(
            _t(ex.extraer_turno(msg, history=history or [], sabido=sabido or {}, lang=lang)),
            _t(lg.leer_grupo(msg, history=history, lang=lang)))
    return x or {}, tx, lec, tl


def _p(vals, q):
    vals = sorted(vals)
    return round(vals[min(len(vals) - 1, int(q * len(vals)))], 2) if vals else None


SALIDA_ACIERTOS = Path("C:/t/inv/lector_aciertos.jsonl")
SALIDA_TURNOS = Path("C:/t/inv/lector_turnos.jsonl")


async def llamar_aciertos(n: int):
    with open(SALIDA_ACIERTOS, "w", encoding="utf-8") as out:
        for cid, lang, msg, *_ in casos():
            for x, tx, lec, tl in await asyncio.gather(*(_par(msg, lang) for _ in range(n))):
                out.write(json.dumps({"caso": cid, "x": x, "tx": tx, "lec": lec, "tl": tl}, ensure_ascii=False) + "\n")
            print(cid, end=" ", flush=True)
    print()


def _turnos_golden():
    ocultos = {d["id"] for d in json.load(open(GOLDEN, encoding="utf-8"))["dialogues"] if d.get("suite") == "oculto"}
    por_dialogo: dict[str, list] = {}
    for ln in open(RONDA, encoding="utf-8"):
        r = json.loads(ln)
        if r.get("tag") in ocultos or not r.get("msg"):  # nunca los del oculto
            continue
        por_dialogo.setdefault(r["tag"], []).append(r)
    return {k: sorted(v, key=lambda r: r["turn"]) for k, v in por_dialogo.items()}


def _turnos_sparring():
    out = {}
    for f in sorted(glob.glob(str(CHARLAS / "b*-t2.jsonl"))):
        filas = [json.loads(ln) for ln in open(f, encoding="utf-8")]
        out[Path(f).stem] = [{"msg": r["msg"], "reply": r.get("reply"), "client_latency_s": r.get("segundos")}
                             for r in filas if r.get("msg")]
    return out


async def _un_dialogo(fuente, dialogo, filas):
    history, sabido, out = [], {}, []
    for r in filas:
        lang = _lang(r["msg"])
        async with SEM:
            x, tx = await _t(ex.extraer_turno(r["msg"], history=history, sabido=sabido, lang=lang))
            x = x or {}
            lec, tl = (await _t(lg.leer_grupo(r["msg"], history=history, lang=lang))
                       if salta(x, sabido, "T2b") else (None, 0.0))
        out.append({"fuente": fuente, "dialogo": dialogo, "x": x, "tx": tx, "antes": dict(sabido), "lec": lec,
                    "tl": tl, "lat": r.get("client_latency_s")})
        for k in ("group_size", "group_allocation", "activity", "is_certified"):
            if x.get(k) is not None:
                sabido[k] = x[k]
        history += [{"role": "user", "content": r["msg"]}, {"role": "assistant", "content": r.get("reply") or ""}]
    return out


async def llamar_turnos():
    with open(SALIDA_TURNOS, "w", encoding="utf-8") as out:
        for fuente, dialogos in (("golden", _turnos_golden()), ("sparring", _turnos_sparring())):
            for filas in await asyncio.gather(*(_un_dialogo(fuente, d, f) for d, f in dialogos.items())):
                for fila in filas:
                    out.write(json.dumps(fila, ensure_ascii=False) + "\n")


def puntuar():
    esperado = {c[0]: c[3:] for c in casos()}
    filas = [json.loads(ln) for ln in open(SALIDA_ACIERTOS, encoding="utf-8")]
    t_ex = [f["tx"] for f in filas]
    t_lec = [f["tl"] for f in filas if f["lec"] is not None]
    descartes = sum(len(f["lec"]["descartes"]) for f in filas if f["lec"])
    print(f"ACIERTOS ({len(filas)} llamadas; extractor p50 {_p(t_ex, .5)} p95 {_p(t_ex, .95)} s; lector p50 "
          f"{_p(t_lec, .5)} p95 {_p(t_lec, .95)} s; citas del lector descartadas {descartes})")
    for var in DISPARADORES:
        tot = {"A": Counter(), "B": Counter()}
        inv, saltos, suma = Counter(), 0, []
        por_caso = {}
        for f in filas:
            total, decididos, sin, cert = esperado[f["caso"]]
            pa = lectura_a(f["x"])
            sl = salta(f["x"], None, var)
            pb = lectura_b(f["x"], f["lec"]) if sl else pa
            saltos += sl
            if sl:
                suma.append(f["tl"])
            ba, bb = bien(pa, total, decididos, sin, cert), bien(pb, total, decididos, sin, cert)
            tot["A"].update(ba)
            tot["B"].update(bb)
            ia, ib = invento(pa, total, decididos), invento(pb, total, decididos)
            inv["A"] += ia
            inv["B"] += ib
            c = por_caso.setdefault(f["caso"], Counter())
            c.update({"n": 1, "salta": sl, "A": all(ba.values()), "B": all(bb.values()), "invA": ia, "invB": ib})
        print(f"\n{var}: salta {saltos}/{len(filas)}; A {dict(tot['A'])} inventos {inv['A']}; "
              f"B {dict(tot['B'])} inventos {inv['B']}; lector en serie (si salta) p50 {_p(suma, .5)} p95 {_p(suma, .95)} s")
        cambian = [f"{k} {c['A']}→{c['B']}/{c['n']} (salta {c['salta']}, inv {c['invA']}→{c['invB']})"
                   for k, c in por_caso.items() if c["A"] != c["B"] or c["invA"] != c["invB"]]
        print("  cambian:", "; ".join(cambian) or "ninguno")
    if not SALIDA_TURNOS.exists():
        return
    turnos = [json.loads(ln) for ln in open(SALIDA_TURNOS, encoding="utf-8")]
    print("\nTURNOS")
    for fuente in ("golden", "sparring"):
        ts = [t for t in turnos if t["fuente"] == fuente]
        for var in DISPARADORES:
            sal = [t for t in ts if salta(t["x"], t["antes"], var)]
            hoy = [t["lat"] for t in sal if isinstance(t["lat"], (int, float))]
            par = [t["lat"] + max(0.0, t["tl"] - t["tx"]) for t in sal if isinstance(t["lat"], (int, float))]
            serie = [t["lat"] + t["tl"] for t in sal if isinstance(t["lat"], (int, float))]
            print(f"  {fuente} {var}: {len(sal)}/{len(ts)} turnos; p95 de esos turnos hoy {_p(hoy, .95)} s, con el "
                  f"lector a la vez {_p(par, .95)} s, detrás del extractor {_p(serie, .95)} s")


async def releer():
    """Solo el lector otra vez, sobre las filas guardadas (aciertos y turnos donde salta T2b); el extractor no se repite."""
    langs = {c[0]: (c[1], c[2]) for c in casos()}
    filas = [json.loads(ln) for ln in open(SALIDA_ACIERTOS, encoding="utf-8")]

    async def _uno(f):
        lang, msg = langs[f["caso"]]
        async with SEM:
            f["lec"], f["tl"] = await _t(lg.leer_grupo(msg, lang=lang))
        return f

    filas = await asyncio.gather(*(_uno(f) for f in filas))
    with open(SALIDA_ACIERTOS, "w", encoding="utf-8") as out:
        for f in filas:
            out.write(json.dumps(f, ensure_ascii=False) + "\n")
    if not SALIDA_TURNOS.exists():
        return
    turnos = [json.loads(ln) for ln in open(SALIDA_TURNOS, encoding="utf-8")]
    dialogos = {**_turnos_golden(), **_turnos_sparring()}
    por_dialogo: dict[str, list] = {}
    for t in turnos:
        por_dialogo.setdefault(t["dialogo"], []).append(t)
    for d, ts in por_dialogo.items():
        history = []
        for t, r in zip(ts, dialogos[d]):
            if t["lec"] is not None:
                async with SEM:
                    t["lec"], t["tl"] = await _t(lg.leer_grupo(r["msg"], history=history, lang=_lang(r["msg"])))
            history += [{"role": "user", "content": r["msg"]}, {"role": "assistant", "content": r.get("reply") or ""}]
    with open(SALIDA_TURNOS, "w", encoding="utf-8") as out:
        for t in turnos:
            out.write(json.dumps(t, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "puntuar"
    if modo == "llamar-aciertos":
        asyncio.run(llamar_aciertos(int(sys.argv[2]) if len(sys.argv) > 2 else 20))
    elif modo == "llamar-turnos":
        asyncio.run(llamar_turnos())
    elif modo == "releer":
        asyncio.run(releer())
    else:
        puntuar()
