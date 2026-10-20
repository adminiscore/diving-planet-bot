"""Textos fijos del flujo en el español de Cartagena (gen, 20-oct, decisión de Gadea; flag `textos_de_cartagena`).

Las respuestas que redacta el RAG siguen el tono del prompt (cartagenero, tuteo), pero las preguntas fijas del flujo
(origen, certificación, nacionalidad, refresher…) se escribieron a mano y salían tal cual:
- en español de España ("¿Sois buzos certificados?", "¿Os interesa?", "os ayudo"), cuando en Cartagena es "ustedes";
- con género supuesto ("¡tranquilo!");
- "Podemos recogerte saliendo desde Cartagena": desde Cartagena no hay recogida, el cliente llega al Muelle de la
  Bodeguita (la base lo dice desde gen-2, y el juez lo marcaba como invento).

`de_cartagena(nuevo, viejo)` elige el texto con el flag; al promocionarlo, la limpieza deja solo el nuevo. El test
`tests/test_textos_de_cartagena.py` impide volver a escribir "vosotros" en un texto del bot (salvo el `viejo` de aquí)."""

from src.config import settings


def de_cartagena(nuevo: str, viejo: str) -> str:
    return nuevo if settings.textos_de_cartagena else viejo
