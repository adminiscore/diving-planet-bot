"""mej-8 (24-oct, flag `marcar_mal`): quien prueba el bot escribe «#mal» (y, si quiere, qué esperaba) cuando una
respuesta está mal. El bot no lo contesta como un mensaje del cliente: pone la etiqueta `mal` a la conversación en
Chatwoot y acusa recibo. Luego `scripts/exportar_mal.py` saca esas conversaciones como casos del banco de fallos
(`scripts/banco_fallos.py medir --banco ...`).

Aquí solo lo que comparten el bot y el script (sin dependencias del canal)."""

MARCA = "#mal"
ETIQUETA = "mal"

ACUSE = {
    "es": "📝 Anotado como fallo. Gracias: puedes seguir la conversación.",
    "en": "📝 Logged as a failure. Thanks: you can carry on with the conversation.",
}


def es_marca(texto: str | None) -> bool:
    """«#mal», «#MAL: no me dio el enlace»… (al principio del mensaje; «#malecón» no cuenta)."""
    t = (texto or "").strip().lower()
    return t.startswith(MARCA) and (len(t) == len(MARCA) or not t[len(MARCA)].isalnum())


def comentario(texto: str | None) -> str:
    """Lo que quien prueba escribió detrás de la marca: qué esperaba o qué estaba mal ("" si nada)."""
    return (texto or "").strip()[len(MARCA):].strip(" :-–—\t\r\n")


def es_acuse(texto: str | None) -> bool:
    return (texto or "").strip() in ACUSE.values()
