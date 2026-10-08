"""Formato de WhatsApp para el texto que sale hacia el cliente (8-oct, cambio de modelos).

GPT-6 Luna escribe con Markdown de documento (`**negrita**`, `[texto](url)`, títulos `###`), y WhatsApp lo enseña
tal cual, con los asteriscos y los corchetes. WhatsApp usa `*negrita*`, `_cursiva_` y `~tachado~`, y los enlaces son
la URL a secas. Esto solo cambia la PRESENTACIÓN, nunca el contenido, y deja intacto lo que ya está en formato de
WhatsApp (las respuestas fijas del bot y las de gpt-4.1-mini).
"""
import re

_NEGRITA = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_NEGRITA_GUION = re.compile(r"__(?=\S)(.+?)(?<=\S)__")
_TACHADO = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
_ENLACE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_TITULO = re.compile(r"^[ \t]*#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)


def _enlace(m: re.Match) -> str:
    texto, url = m.group(1).strip(), m.group(2)
    return url if texto.rstrip("/") == url.rstrip("/") else f"{texto}: {url}"


def a_whatsapp(texto: str) -> str:
    """El texto con el formato de WhatsApp en vez del de Markdown."""
    if not texto:
        return texto
    out = _ENLACE.sub(_enlace, texto)
    out = _TITULO.sub(lambda m: f"*{m.group(1).strip('*').strip()}*", out)
    out = _NEGRITA.sub(r"*\1*", out)
    out = _NEGRITA_GUION.sub(r"*\1*", out)
    return _TACHADO.sub(r"~\1~", out)
