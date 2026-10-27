"""CALN-6 (27-oct, decisión de Gadea: opción A): un compositor al final del turno.

La respuesta de un turno se escribe en ~26 sitios y se le pegan trozos en ~27 (`docs/robustness/caln/
estudio-caln6-composicion.md`): el escritor cierra con la pregunta de la reserva, el código le añade detrás lo que se le
escapó (arq-7b: qué incluye, la recogida, el alojamiento), los avisos van al final, y la pregunta se vuelve a pegar. En
la ronda caln1-B, 16 respuestas decían lo mismo dos veces y 17 llevaban dos preguntas.

Paso 1: la pregunta de la reserva va UNA vez y al FINAL. `ask_slot` apunta en el turno cada pregunta que formula
(`_preguntas_del_turno`); aquí se quitan sus copias de la respuesta, estén donde estén (un párrafo entero o una frase con
«?» dentro de otro), y se pone la de la pregunta pendiente al final. Si la respuesta no la llevaba (una tarjeta, un
pase), no se toca.
"""
from __future__ import annotations

import re
import unicodedata

_PARRAFO = "\n\n"
# Una frase que acaba en «?» (con el cierre de negrita, cursiva o paréntesis), dentro de una línea.
_PREGUNTA_RE = re.compile(r"[^.!?\n]*\?+[*_)\]]*")


def _palabras(texto: str) -> set[str]:
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return set(re.sub(r"[^a-z0-9 ]", " ", t).split())


def _es_la_misma(a: str, b: str) -> bool:
    """Dos textos que dicen lo mismo: las mismas cifras y casi las mismas palabras (sobre el más largo)."""
    if re.findall(r"\d[\d.,]*", a) != re.findall(r"\d[\d.,]*", b):
        return False
    pa, pb = _palabras(a), _palabras(b)
    return bool(pa and pb) and len(pa & pb) / max(len(pa), len(pb)) >= 0.8


def _sin_las_preguntas(respuesta: str, preguntas: list[str]) -> tuple[bool, str]:
    """(si había alguna, la respuesta sin ellas): fuera los párrafos que son un párrafo de una pregunta del turno y, dentro
    de los demás, las frases con «?» que son la frase con «?» de una pregunta."""
    partes_de_preguntas = [p.strip() for q in preguntas for p in q.split(_PARRAFO) if p.strip()]
    frases_de_preguntas = [f.strip() for q in preguntas for f in _PREGUNTA_RE.findall(q)]
    quitada, quedan = False, []
    for parrafo in respuesta.split(_PARRAFO):
        if parrafo.strip() and any(_es_la_misma(parrafo.strip(), p) for p in partes_de_preguntas):
            quitada = True
            continue
        antes = parrafo
        for frase in _PREGUNTA_RE.findall(parrafo):
            if any(_es_la_misma(frase.strip(), q) for q in frases_de_preguntas):
                parrafo = parrafo.replace(frase, "", 1)
        if parrafo != antes:
            quitada = True
            parrafo = re.sub(r"[ \t]{2,}", " ", parrafo).strip()
        if parrafo.strip():
            quedan.append(parrafo)
    return quitada, _PARRAFO.join(quedan)


def _sin_parrafos_repetidos(respuesta: str) -> str:
    """Fuera los párrafos idénticos a uno anterior (en un pase, lo contestado delante y la respuesta del turno traían la
    misma lista dos veces: caln1-B, pareja-certificados-cop-descuento-almuerzo t3)."""
    vistos, quedan = set(), []
    for parrafo in respuesta.split(_PARRAFO):
        clave = " ".join(parrafo.split())
        if clave and clave in vistos:
            continue
        vistos.add(clave)
        quedan.append(parrafo)
    return _PARRAFO.join(quedan)


def componer(state, respuesta: str, *, pase: bool = False) -> str:
    """La respuesta del turno con la pregunta de la reserva una vez y al final (paso 1). En un turno que pasa a un
    asesor, sus copias salen y no se vuelve a poner: sigue una persona (y la nota de la tarjeta, si va, ya pregunta)."""
    if not respuesta:
        return respuesta
    respuesta = _sin_parrafos_repetidos(respuesta)
    preguntas = getattr(state, "_preguntas_del_turno", None) or []
    pendiente = state.core_pending_slot
    final = next((texto for slot, texto in reversed(preguntas) if slot == pendiente and texto), None)
    if final is None and not pase:
        return respuesta
    quitada, cuerpo = _sin_las_preguntas(respuesta, [texto for _, texto in preguntas if texto])
    if not quitada:
        return respuesta
    if pase or final is None:
        return cuerpo
    return f"{cuerpo.rstrip()}{_PARRAFO}{final}" if cuerpo.strip() else final
