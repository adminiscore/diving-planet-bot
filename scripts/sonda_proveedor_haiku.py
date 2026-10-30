"""CALN-10: ¿la variación de Haiku viene de que OpenRouter reparta las llamadas entre proveedores? Mismos casos ×N con
los proveedores de siempre y con uno solo; por caso, cuántas salidas distintas y cuántos inventos (banco ex0)."""
import asyncio
import json
import sys
from collections import Counter

sys.path.insert(0, ".")
from scripts.run_extraction_eval import casos_ex0, puntuar_ex0
from src.agents import extractor_turno as et
from src.config import settings

SENSIBLES = {"ex0-cambio-idioma-t1", "ex0-actividad-cambia-varias-t1", "ex0-aprobacion-logs-padi-t2", "ex0-familia-mixta-precio-descuento-refresher-t3",
             "ex0-grupo-cambia-dos-veces-t5", "ex0-reserva-solo-link-t1", "ex0-certificado-precio-dia-paquete-5-y-hoteles-base-t2",
             "ex0-nacionalidad-ambigua-t1", "ex0-familia-mixta-precio-descuento-refresher-t1", "ex0-colombianos-precio-minicurso-dos-inmersiones-t2",
             "ex0-acompanante-goteo-t4", "ex0-principiante-hora-lugar-y-precio-t2"}
casos = [c for c in casos_ex0("diseño") if c["id"] in SENSIBLES]
PROPIOS = [  # frases nuestras del sparring (solo estabilidad: sin esperado)
    {"id": "cali", "lang": "es", "message": "Buenas, una amiga hizo el minicurso con ustedes hace un año y le costó 500.000 pesos. Sigue igual? Soy de Cali y salgo de Cartagena"},
    {"id": "nacio-madrid", "lang": "es", "message": "Hola! Nací en Colombia pero vivo en Madrid desde pequeña. Cuánto cuesta el snorkel desde Cartagena? Pago en pesos?"},
    {"id": "residente", "lang": "es", "message": "yo soy residente"},
    {"id": "pareja-advanced", "lang": "en", "message": "Hi there! My wife and I are staying at a hotel in Barú next week. We're both certified divers (Advanced). Can you pick us up at the hotel? Is lunch included? How much for 2 dives?"},
    {"id": "both-of-us", "lang": "en", "message": "We're at the Decameron in Barú. We just want the 2 dives, both of us. Where do we meet the boat?"},
]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
VARIANTES = {"reparto": settings.openrouter_proveedores, "solo-uno": sys.argv[2] if len(sys.argv) > 2 else "anthropic"}
async def una(c, sem):
    async with sem:
        sabido = c.get("sabido") or {}
        d = await et.extraer_turno(c["message"], history=c.get("history"), sabido=sabido, lang=c["lang"])
        return {f: v for f, v in (d or {}).items() if v != sabido.get(f)} if d is not None else None
async def main():
    sem = asyncio.Semaphore(6)
    salidas = {v: {c["id"]: [] for c in casos + PROPIOS} for v in VARIANTES}
    for rep in range(N):
        for v, prov in VARIANTES.items():
            settings.openrouter_proveedores = prov
            res = await asyncio.gather(*[una(c, sem) for c in casos + PROPIOS])
            for c, d in zip(casos + PROPIOS, res, strict=True):
                salidas[v][c["id"]].append(d)
    for v in VARIANTES:
        distintas = sum(len({json.dumps(x, sort_keys=True, ensure_ascii=False) for x in salidas[v][c["id"]]}) for c in casos + PROPIOS)
        inv = sum(len(puntuar_ex0(d or {}, c["expected"], c.get("sabido"))["inventado"]) for c in casos for d in salidas[v][c["id"]])
        fallos = sum(1 for c in casos + PROPIOS for d in salidas[v][c["id"]] if d is None)
        print(f"{v:<9} ({VARIANTES[v]}): salidas distintas {distintas} en {len(casos + PROPIOS)} casos ×{N} · inventos (ex0) {inv} · llamadas fallidas {fallos}")
    print("por caso (salidas distintas reparto / solo-uno):")
    for c in casos + PROPIOS:
        a, b = (len({json.dumps(x, sort_keys=True, ensure_ascii=False) for x in salidas[v][c["id"]]}) for v in VARIANTES)
        print(f"  {c['id'][-38:]:<38} {a} / {b}")
    nac = {v: Counter(str((d or {}).get("is_colombian")) for cid in ("cali", "nacio-madrid", "residente") for d in salidas[v][cid]) for v in VARIANTES}
    print("is_colombian en cali/nacio-madrid/residente:", nac)
asyncio.run(main())
