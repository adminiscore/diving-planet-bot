"""EX-EST-2 (14-oct, idea de Gadea): auditoría de contradicciones de la base de conocimiento.

En la ronda est3-B, la mitad de los fallos del RAG venían de la BASE, no de la redacción: datos que faltaban (a qué
hora acaba el día 1) o que se contradecían entre documentos (regreso al hotel a las 2:00, a las 4:30 o a las
12:30-13:30; punto de encuentro "Muelle de la Bodeguita" o "Marina Turística"). Con dos versiones del mismo dato, el
RAG coge una u otra según el turno: respuestas distintas cada vez.

Lee EXACTAMENTE lo que ve el bot: los documentos de la base v2 (`scripts.kb_v2.build_kb_v2`: fichas de servicio,
FAQs curadas, políticas y descuentos) y el catálogo del prompt (`catalog.catalog_facts`). Dos pasadas:

  temas     por cada tema de los metadatos (horarios, precios, punto de encuentro…), todos sus documentos en español
            + el catálogo a un modelo, que lista los pares de afirmaciones INCOMPATIBLES con la cita literal de cada
            lado. Las citas se comprueban en el texto (una cita que no está, fuera): nada inventado.
  idiomas   cada documento en español frente al mismo en inglés: ¿dicen datos distintos?

Salida: `docs/robustness/auditoria-base/<fecha>-<name>.json` y un resumen por pantalla. No cambia nada: lo que
salga se revisa a mano y la verdad la decide el negocio (Gadea).

    ENV_FILE=.env.dev python -m scripts.auditoria_base --name base
    ENV_FILE=.env.dev python -m scripts.auditoria_base --name prueba --temas schedule,meeting_point --sin-idiomas
"""
import argparse
import asyncio
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "docs/robustness/auditoria-base"

_SISTEMA_TEMAS = (
    "Eres auditor de la base de conocimiento de un centro de buceo (Diving Planet, Cartagena e Islas del Rosario). "
    "Te doy documentos numerados [D1], [D2]… sobre el tema «{tema}», y el CATÁLOGO [CAT]. Busca CONTRADICCIONES: dos "
    "afirmaciones sobre la MISMA cosa que no pueden ser verdad a la vez (horas, precios, lugares, qué incluye, "
    "requisitos, edades, noches, reglas de pago o de reserva…).\n"
    "NO es contradicción: que un documento dé más detalle que otro; planes distintos con datos distintos (desde "
    "Cartagena frente a quien ya está en las islas, un curso frente a otro, día 1 frente a día 2); un 'normal' frente "
    "a un 'online'; redacciones distintas del mismo dato. Ante la duda sobre si hablan del mismo plan, NO la listes.\n"
    "Cada cita es un trozo LITERAL y corto (copiado tal cual, 5-25 palabras) del documento que citas. "
    "Responde SOLO JSON: {{\"contradicciones\": [{{\"que\": \"dato en conflicto\", \"doc_a\": \"D3\", \"cita_a\": \"…\", "
    "\"doc_b\": \"D7\", \"cita_b\": \"…\", \"explicacion\": \"por qué no pueden ser verdad a la vez\", "
    "\"gravedad\": \"alta|media|baja\"}}]}}. alta = el cliente recibiría un dato operativo falso (hora, lugar, precio, "
    "qué incluye); media = regla o requisito; baja = matiz. Si no hay ninguna, lista vacía."
)

_SISTEMA_IDIOMAS = (
    "Te doy pares de textos [Pn] en español (ES) y en inglés (EN) que deberían decir LO MISMO. ¿Alguno dice un DATO "
    "distinto en un idioma que en el otro (hora, precio, lugar, qué incluye, requisito, regla)? Las diferencias de "
    "estilo o de traducción no cuentan; que un idioma omita una frase entera sí, si es un dato. "
    "Responde SOLO JSON: {\"diferencias\": [{\"par\": \"P2\", \"cita_es\": \"…\", \"cita_en\": \"…\", "
    "\"explicacion\": \"…\"}]}. Citas literales y cortas. Si no hay ninguna, lista vacía."
)


def norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[*_`\"“”'’]", "", t)).strip()


def cita_esta(cita: str, texto: str) -> bool:
    return bool(cita and cita.strip()) and norm(cita.strip(" .…")) in norm(texto)


def documentos() -> tuple[list[dict], dict]:
    from scripts.kb_v2 import build_kb_v2
    from src.flows.catalog import catalog_facts

    docs = build_kb_v2()
    es = [d for d in docs if d["metadata"].get("lang") == "es"]
    en = {d["metadata"].get("key"): d for d in docs if d["metadata"].get("lang") == "en"}
    cat = {"content": catalog_facts("es"), "metadata": {"key": "catalogo", "source": "catalogo", "topics": []}}
    return es + [cat], en


async def _json(client, model: str, sistema: str, usuario: str) -> dict:
    extra = {"reasoning_effort": "medium"} if model.startswith(("gpt-5", "o")) else {"temperature": 0}
    r = await client.chat.completions.create(
        model=model, response_format={"type": "json_object"}, **extra,
        messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}])
    try:
        return json.loads(r.choices[0].message.content or "{}"), r.usage
    except json.JSONDecodeError:
        return {}, r.usage


async def pasada_temas(client, model: str, docs: list[dict], temas: list[str] | None, sem) -> tuple[list, dict]:
    cat = docs[-1]
    por_tema = defaultdict(list)
    for d in docs[:-1]:
        for t in d["metadata"].get("topics") or ["sin_tema"]:
            por_tema[t].append(d)
    elegidos = temas or sorted(por_tema, key=lambda t: -len(por_tema[t]))
    uso = defaultdict(int)

    async def uno(tema: str) -> list[dict]:
        grupo = por_tema.get(tema, [])
        if not grupo:
            return []
        ids = {f"D{i + 1}": d for i, d in enumerate(grupo)}
        ids["CAT"] = cat
        cuerpo = "\n\n".join(f"[{k}] ({d['metadata'].get('key')})\n{d['content']}" for k, d in ids.items())
        async with sem:
            res, u = await _json(client, model, _SISTEMA_TEMAS.format(tema=tema), cuerpo)
        uso["entrada"] += u.prompt_tokens
        uso["salida"] += u.completion_tokens
        salida = []
        for c in res.get("contradicciones") or []:
            a, b = ids.get(c.get("doc_a")), ids.get(c.get("doc_b"))
            ok = bool(a and b and cita_esta(c.get("cita_a", ""), a["content"])
                      and cita_esta(c.get("cita_b", ""), b["content"]))
            salida.append({**c, "tema": tema, "citas_comprobadas": ok,
                           "doc_a": a["metadata"].get("key") if a else c.get("doc_a"),
                           "doc_b": b["metadata"].get("key") if b else c.get("doc_b")})
        print(f"  {tema}: {len(grupo)} documentos, {len(salida)} contradicciones "
              f"({sum(1 for s in salida if s['citas_comprobadas'])} con citas comprobadas)", flush=True)
        return salida

    listas = await asyncio.gather(*[uno(t) for t in elegidos])
    # El mismo par de citas puede salir en varios temas: una vez.
    vistos, unicas = set(), []
    for c in (c for lista in listas for c in lista):
        clave = frozenset({(c["doc_a"], norm(c.get("cita_a", ""))), (c["doc_b"], norm(c.get("cita_b", "")))})
        if clave not in vistos:
            vistos.add(clave)
            unicas.append(c)
    return unicas, dict(uso)


async def pasada_idiomas(client, model: str, docs: list[dict], en: dict, sem, lote: int = 6) -> tuple[list, dict]:
    pares = [(d, en[d["metadata"]["key"]]) for d in docs[:-1] if d["metadata"].get("key") in en]
    uso = defaultdict(int)

    async def uno(trozo: list) -> list[dict]:
        ids = {f"P{i + 1}": p for i, p in enumerate(trozo)}
        cuerpo = "\n\n".join(f"[{k}] ({es['metadata']['key']})\nES: {es['content']}\nEN: {en_['content']}"
                             for k, (es, en_) in ids.items())
        async with sem:
            res, u = await _json(client, model, _SISTEMA_IDIOMAS, cuerpo)
        uso["entrada"] += u.prompt_tokens
        uso["salida"] += u.completion_tokens
        salida = []
        for c in res.get("diferencias") or []:
            p = ids.get(c.get("par"))
            ok = bool(p and cita_esta(c.get("cita_es", ""), p[0]["content"])
                      and cita_esta(c.get("cita_en", ""), p[1]["content"]))
            salida.append({**c, "doc": p[0]["metadata"]["key"] if p else c.get("par"), "citas_comprobadas": ok})
        return salida

    listas = await asyncio.gather(*[uno(pares[i:i + lote]) for i in range(0, len(pares), lote)])
    return [c for lista in listas for c in lista], dict(uso)


async def main_async(a) -> int:
    from openai import AsyncOpenAI

    from src.config import settings

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    sem = asyncio.Semaphore(a.paralelo)
    docs, en = documentos()
    print(f"{len(docs) - 1} documentos en español + catálogo; modelo {a.modelo}", flush=True)
    temas = [t for t in a.temas.split(",") if t] if a.temas else None
    contradicciones, uso_t = await pasada_temas(client, a.modelo, docs, temas, sem)
    diferencias, uso_i = ([], {}) if a.sin_idiomas else await pasada_idiomas(client, a.modelo_idiomas, docs, en, sem)
    orden = {"alta": 0, "media": 1, "baja": 2}
    contradicciones.sort(key=lambda c: (not c["citas_comprobadas"], orden.get(c.get("gravedad"), 3), c["tema"]))

    DIR.mkdir(parents=True, exist_ok=True)
    salida = DIR / f"{date.today().isoformat()}-{a.name}.json"
    salida.write_text(json.dumps({
        "nombre": a.name, "modelo": a.modelo, "modelo_idiomas": a.modelo_idiomas, "temas": temas or "todos",
        "uso_tokens": {"temas": uso_t, "idiomas": uso_i},
        "contradicciones": contradicciones, "diferencias_idioma": diferencias,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    buenas = [c for c in contradicciones if c["citas_comprobadas"]]
    print(f"\nCONTRADICCIONES: {len(buenas)} con citas comprobadas "
          f"({len(contradicciones) - len(buenas)} descartadas por cita que no está)")
    for c in buenas:
        print(f"  [{c.get('gravedad')}] {c['tema']} · {c.get('que')}\n"
              f"      {c['doc_a']}: «{c.get('cita_a')}»\n      {c['doc_b']}: «{c.get('cita_b')}»")
    buenas_i = [d for d in diferencias if d["citas_comprobadas"]]
    print(f"\nES ≠ EN: {len(buenas_i)} con citas comprobadas ({len(diferencias) - len(buenas_i)} descartadas)")
    for d in buenas_i:
        print(f"  {d['doc']}: «{d.get('cita_es')}» ≠ «{d.get('cita_en')}»")
    print(f"\ntokens: temas {uso_t} · idiomas {uso_i}\n→ {salida}")
    return 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--name", required=True)
    p.add_argument("--temas", default="", help="temas de los metadatos separados por comas (por defecto, todos)")
    p.add_argument("--modelo", default="gpt-5")
    p.add_argument("--modelo-idiomas", default="gpt-4.1")
    p.add_argument("--sin-idiomas", action="store_true")
    p.add_argument("--paralelo", type=int, default=5)
    return asyncio.run(main_async(p.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
