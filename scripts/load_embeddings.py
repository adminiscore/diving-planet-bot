"""Utilidades compartidas del índice de la base (`scripts/kb_v2.py`): rutas, modelo de embeddings y temas.

lat-deuda-u (26-oct): el índice v1 que construía este módulo (`load_knowledge_base`, `python -m scripts.load_embeddings`)
se retiró: el bot lee la base curada (esquema kb_v2) desde rag-2 y el CI pagaba embeddings en cada deploy por un índice
que nadie leía. Quedan aquí las piezas que usa kb_v2.
"""

import re
from pathlib import Path

from openai import OpenAI

from src.config import settings

DATA_DIR = Path(__file__).parent.parent / "data" / "knowledge_base"
EMBEDDING_MODEL = settings.openai_embedding_model  # text-embedding-3-small


TOPIC_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("pricing", re.compile(r"\b(precio|precios|valor|cu[aá]nto cuesta|usd|d[oó]lares|pesos|cop)\b", re.IGNORECASE)),
    ("discount", re.compile(r"(?:10%|\bdescuento\b|\bdiscount\b|descuento\s*10|discount\s*10)", re.IGNORECASE)),
    ("availability", re.compile(r"\b(disponibilidad|cupos|hay cupo|available|availability|tomorrow|ma[nñ]ana)\b", re.IGNORECASE)),
    ("booking", re.compile(r"\b(reservar|reserva|reservas|reservo|reservamos|apartar|booking|book|p[aá]gina|web|online)\b", re.IGNORECASE)),
    ("meeting_point", re.compile(r"\b(punto de encuentro|muelle|bodeguita|gate|puerta|marina|todo mar)\b", re.IGNORECASE)),
    ("schedule", re.compile(r"\b(horario|hora|itinerario|schedule|duraci[oó]n|duration|regreso|return)\b", re.IGNORECASE)),
    ("reschedule", re.compile(r"\b(mover la fecha|cambiar la fecha|cambio de fecha|reprogramar|reagendar|move the date|change the date|reschedule)\b", re.IGNORECASE)),
    ("certification", re.compile(r"\b(certificaci[oó]n|certificado|open water|advanced|rescue|padi|ssi|logbook)\b", re.IGNORECASE)),
    ("refresher", re.compile(r"\b(refresh|refresher|refresh requirement|hace a[nñ]os no buceo|hace mucho no buceo|sin bucear|tiempo sin bucear)\b", re.IGNORECASE)),
    ("location_islands", re.compile(r"\b(isla|islas|rosario|isla grande|cocoliso|majagua|mulata|hotel)\b", re.IGNORECASE)),
    ("accommodation", re.compile(r"\b(alojamiento|accommodation|hotel|hospedaje|incluye alojamiento|is accommodation included)\b", re.IGNORECASE)),
    ("discount_colombian", re.compile(r"\b(colombian|colombiano|colombiana|colombianos|colombianas|residente)\b", re.IGNORECASE)),
    ("payment", re.compile(r"\b(pago|pagar|transferencia|qr|bancolombia|tarjeta|credit|pasarela|link de pago)\b", re.IGNORECASE)),
    ("forms_waiver", re.compile(r"\b(formulario|exoneraci[oó]n|jotform|carn[eé]|carne|certification photo|foto)\b", re.IGNORECASE)),
    ("equipment", re.compile(r"\b(equipo|equipment|incluye|include|insurance|seguro|qu[eé]\s+debo\s+llevar|qu[eé]\s+llevar|llevar|traer|bring|towel|toalla|bloqueador|sunscreen)\b", re.IGNORECASE)),
    ("depth", re.compile(r"\b(profundidad|metros|m\b|maxima|max\s+depth|depth)\b", re.IGNORECASE)),
    ("weather_cancellation", re.compile(r"\b(clima|weather|cancelaci[oó]n|reembolso|refund|pol[ií]tica)\b", re.IGNORECASE)),
    ("photos_media", re.compile(r"\b(foto|fotos|photos|video|videos)\b", re.IGNORECASE)),
    ("seasickness", re.compile(r"\b(mareo|sea sick|seasick|tabletas|pills)\b", re.IGNORECASE)),
]


def detect_topics(text: str) -> list[str]:
    topics: list[str] = []
    for name, pattern in TOPIC_PATTERNS:
        if pattern.search(text):
            topics.append(name)
    return topics


def generate_embeddings(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts using OpenAI API."""
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]
