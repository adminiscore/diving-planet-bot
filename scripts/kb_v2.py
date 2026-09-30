"""rag-2 (Plan Coral, fase RAG): la base de conocimiento curada (v2) y su carga en pgvector.

Qué cambia frente a `scripts/load_embeddings.py` (v1, que sigue igual):
- UNA ficha por servicio y origen, autocontenida (qué es, para quién, duración y noches, precio, qué incluye y qué
  no, itinerario, requisitos, preparación, enlaces), en lugar de 5 trozos. La línea de datos es la misma del
  catálogo del prompt (`catalog.service_fact_parts`): la ficha y el catálogo no pueden contradecirse.
- FAQs curadas (`data/knowledge_base/curada/faqs.json`): sin las 25 que describían un servicio, sin listas de
  precios, sin teléfono ni tono de "escríbenos".
- Cada política y cada descuento como su propio documento, con 3 formas de preguntarlo
  (`curada/preguntas.json`) para que la búsqueda los encuentre; el texto sigue en `policies.json` /
  `discounts.json` (una regla, un sitio).
- Sin trozos de precios (los precios están en la ficha y en el catálogo).

Se carga en el esquema `kb_v2` de la misma base (tabla `kb_v2.kb_documents`, mismas columnas e índices): la de hoy
(`public.kb_documents`) no se toca. El bot la usa solo con el flag `RAG_KB_V2`.

    python -m scripts.kb_v2 --dry-run      # construye y resume, sin tocar nada
    python -m scripts.kb_v2 --yes          # embeddings (céntimos) + carga en kb_v2
"""
import argparse
import asyncio
import json
import logging
from collections import Counter

import asyncpg
from openai import OpenAI

from scripts.load_embeddings import DATA_DIR, EMBEDDING_MODEL, detect_topics, generate_embeddings
from src.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCHEMA = settings.rag_kb_esquema  # "kb_v2"; otro solo para medir sin tocar PRE (--esquema)
CURADA = DATA_DIR / "curada"

_T = {
    "es": {"ficha": "Ficha del servicio", "desde": "saliendo desde Cartagena",
           "islas": "para quien ya está en las Islas del Rosario (recogida en el hotel si tiene acceso marítimo)",
           "datos": "Datos", "incluye": "Incluye", "no_incluye": "No incluye", "itinerario": "Itinerario",
           "requisitos": "Requisitos", "preparacion": "Antes de la actividad", "reserva": "Reserva",
           "info": "Más información", "pregunta": "Pregunta", "otras": "Otras formas de preguntarlo",
           "respuesta": "Respuesta", "edad10": "edad mínima 10"},
    "en": {"ficha": "Service sheet", "desde": "departing from Cartagena",
           "islas": "for guests already on the Rosario Islands (hotel pick-up if it has boat access)",
           "datos": "Facts", "incluye": "Included", "no_incluye": "Not included", "itinerario": "Itinerary",
           "requisitos": "Requirements", "preparacion": "Before the activity", "reserva": "Booking",
           "info": "More info", "pregunta": "Question", "otras": "Other ways to ask",
           "respuesta": "Answer", "edad10": "minimum age 10"},
}


def _lista(titulo: str, items) -> str:
    if isinstance(items, str):
        return f"{titulo}: {items}" if items.strip() else ""
    items = [i for i in (items or []) if i]
    return f"{titulo}:\n" + "\n".join(f"- {i}" for i in items) if items else ""


def ficha_servicio(service_id: str, svc: dict, lang: str) -> dict:
    """El documento de un servicio en la base v2: la ficha + sus metadatos.

    El TEXTO lo construye `catalog.service_fact_sheet` (rag-3): la misma funcion que arma la ficha
    que se inyecta en el contexto del turno cuando ya se sabe que servicio mira el cliente. Vivia
    aqui hasta rag-2, cuando solo la usaba la base; se movio al tener dos usos, para que la ficha
    de la base y la del contexto no puedan decir cosas distintas -- que es el principio de rag-2.
    `tests/test_rag3_ficha_servicio.py` fija que el texto no cambio al moverlo."""
    from src.flows.catalog import service_fact_sheet

    island = service_id.endswith("_already_on_island")
    texto = service_fact_sheet(service_id, lang, svc)
    return {"content": texto, "metadata": {
        "source": "services", "key": f"ficha:{service_id}", "service_id": service_id, "lang": lang,
        "origin": "islas" if island else "cartagena", "topics": detect_topics(texto)}}


_REFRESHER = {
    "es": ("Ficha del servicio: Refresher (repaso para buzos certificados con más de 2 años sin bucear) — {origen}",
           "El refresher es la MISMA actividad que el Minicurso de Buceo: misma información, itinerario, requisitos y "
           "precio. Se reserva como '{nombre}'. Lo que sigue es la ficha de ese minicurso."),
    "en": ("Service sheet: Refresher (review for certified divers who haven't dived in more than 2 years) — {origen}",
           "The refresher is the SAME activity as the Dive Mini Course: same information, itinerary, requirements and "
           "price. It is booked as '{nombre}'. Below is that mini course's sheet."),
}


def fichas_refresher(services: dict) -> list[dict]:
    """rag-3 (30-sep, decisión de Gadea: "el refresher es la misma info que el minicurso"): una ficha propia del
    refresher por origen, que es la del servicio con el que se vende (registro de actividades, `refresher` →
    minicurso) con un encabezado que dice qué es. Sin ella, "necesito un refresher, ¿qué completo antes?" no
    encontraba el formulario médico y el bot le atribuía las 4 h de teoría del Open Water (`rag_piezas`)."""
    from src.domain import activities as dom
    from src.flows.catalog import service_fact_sheet

    docs = []
    for location, origen in (("cartagena", "cartagena"), ("island", "islas")):
        ids = dom.service_ids("refresher", location)
        if not ids or ids[0] not in services:
            continue
        sid = ids[0]
        for lang in ("es", "en"):
            titulo, nota = _REFRESHER[lang]
            ficha = service_fact_sheet(sid, lang, services[sid])
            separador = "\n\n"
            cuerpo = ficha.split(separador, 1)[1] if separador in ficha else ficha  # sin el título del minicurso
            texto = separador.join([titulo.format(origen=_T[lang]["islas" if origen == "islas" else "desde"]),
                                    nota.format(nombre=services[sid].get(f"name_{lang}") or sid), cuerpo])
            docs.append({"content": texto, "metadata": {
                "source": "services", "key": f"ficha:refresher:{sid}", "service_id": sid, "lang": lang,
                "origin": origen, "topics": detect_topics(texto)}})
    return docs


def _qa(pregunta: str, otras: list[str], respuesta: str, lang: str) -> str:
    t = _T[lang]
    otras = [o for o in otras if o and o.strip() != pregunta.strip()]
    return (f"{t['pregunta']}: {pregunta}\n" + (f"{t['otras']}: {' / '.join(otras)}\n" if otras else "")
            + f"{t['respuesta']}: {respuesta}")


def build_kb_v2() -> list[dict]:
    services = json.loads((DATA_DIR / "services.json").read_text(encoding="utf-8-sig"))["services"]
    policies = json.loads((DATA_DIR / "policies.json").read_text(encoding="utf-8"))["policies"]
    discounts = json.loads((DATA_DIR / "discounts.json").read_text(encoding="utf-8"))["discounts"]
    faqs = json.loads((CURADA / "faqs.json").read_text(encoding="utf-8"))["faqs"]
    preguntas = json.loads((CURADA / "preguntas.json").read_text(encoding="utf-8"))["reglas"]

    docs: list[dict] = []
    for sid, svc in services.items():
        if not isinstance(svc, dict):
            continue
        for lang in ("es", "en"):
            docs.append(ficha_servicio(sid, svc, lang))
    docs.extend(fichas_refresher(services))
    for f in faqs:
        for lang in ("es", "en"):
            texto = _qa(f[f"question_{lang}"], f.get(f"preguntas_alt_{lang}") or [], f[f"answer_{lang}"], lang)
            docs.append({"content": texto, "metadata": {"source": "faqs", "key": f"faq:{f['origen']}", "lang": lang,
                                                        "topics": detect_topics(texto)}})
    reglas = [(f"politica:{k}", v.get("es", ""), v.get("en", "")) for k, v in policies.items()]
    reglas += [(f"descuento:{k}", v.get("description_es", ""), v.get("description_en", "")) for k, v in discounts.items()]
    for key, es, en in reglas:
        alt = preguntas.get(key) or {}
        for lang, texto in (("es", es), ("en", en)):
            if not texto:
                continue
            qs = alt.get(lang) or []
            contenido = _qa(qs[0], qs[1:], texto, lang) if qs else texto
            docs.append({"content": contenido, "metadata": {"source": "policies", "key": key, "lang": lang,
                                                            "topics": detect_topics(contenido)}})
    return docs


def _ddl(schema: str) -> str:
    return f"""
CREATE SCHEMA IF NOT EXISTS {schema};
CREATE TABLE IF NOT EXISTS {schema}.kb_documents (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{{}}',
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW(),
    content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content, ''))) STORED
);
CREATE INDEX IF NOT EXISTS kb_v2_content_tsv_idx ON {schema}.kb_documents USING GIN (content_tsv);
"""


async def cargar(docs: list[dict], embeddings: list[list[float]], schema: str = SCHEMA) -> int:
    conn = await asyncpg.connect(settings.database_url)
    try:
        async with conn.transaction():
            await conn.execute(_ddl(schema))
            await conn.execute(f"DELETE FROM {schema}.kb_documents")
            await conn.executemany(
                f"INSERT INTO {schema}.kb_documents (content, metadata, embedding) VALUES ($1, $2, $3)",
                [(d["content"], json.dumps(d["metadata"], ensure_ascii=False), str(e)) for d, e in zip(docs, embeddings)])
        return int(await conn.fetchval(f"SELECT COUNT(*) FROM {schema}.kb_documents"))
    finally:
        await conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--yes", action="store_true", help="genera embeddings y carga kb_v2 (reemplaza su contenido)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--esquema", default=SCHEMA, help="esquema destino (por defecto el de la busqueda, kb_v2); "
                    "otro para medir una base nueva sin tocar la de PRE")
    args = ap.parse_args()
    docs = build_kb_v2()
    por = Counter(f"{d['metadata']['source']}/{d['metadata']['lang']}" for d in docs)
    chars = sum(len(d["content"]) for d in docs)
    logger.info(f"kb_v2: {len(docs)} documentos {dict(por)} · {chars} caracteres (~{chars // 4} tokens)")
    if args.dry_run or not args.yes:
        logger.info("sin --yes: no se genera nada ni se toca la base")
        return
    embeddings = []
    cliente = OpenAI(api_key=settings.openai_api_key)
    for n in range(0, len(docs), 256):
        embeddings += generate_embeddings(cliente, [d["content"] for d in docs[n:n + 256]])
    logger.info(f"{len(embeddings)} embeddings con {EMBEDDING_MODEL}")
    total = asyncio.run(cargar(docs, embeddings, args.esquema))
    logger.info(f"cargados {total} documentos en {args.esquema}.kb_documents")


if __name__ == "__main__":
    main()
