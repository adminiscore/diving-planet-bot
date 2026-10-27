"""CALN-6 (27-oct, decisión de Gadea: opción A): un compositor al final del turno.

La respuesta de un turno se escribe en ~26 sitios y se le pegan trozos en ~27 (`docs/robustness/caln/
estudio-caln6-composicion.md`): el escritor cierra con la pregunta de la reserva, el código le añade detrás lo que se le
escapó (arq-7b: qué incluye, la recogida, el alojamiento), los avisos van al final, y la pregunta se vuelve a pegar. En
la ronda caln1-B, 16 respuestas decían lo mismo dos veces y 17 llevaban dos preguntas.

Paso 1: la pregunta de la reserva va UNA vez y al FINAL. `ask_slot` apunta en el turno cada pregunta que formula
(`_preguntas_del_turno`); aquí se quitan sus copias de la respuesta, estén donde estén (un párrafo entero o una frase con
«?» dentro de otro), y se pone la de la pregunta pendiente al final. Si la respuesta no la llevaba (una tarjeta, un
pase), no se toca.

Paso 2: UNA pregunta como mucho. Si lo que queda ya pregunta algo (el escritor cierra con su pregunta, la nota de la
tarjeta pregunta), la de la reserva no se pone y queda pendiente para el turno siguiente: la regla de u3-4 y CAL-C3b
(`_answer_replaces_the_booking_question`), que solo valía en algunos caminos. Y las frases de la pregunta final (la
explicación que la acompaña) no se repiten en el cuerpo.
"""
from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger("uvicorn.error")

_PARRAFO = "\n\n"
# Una frase que acaba en «?» (con el cierre de negrita, cursiva o paréntesis), dentro de una línea.
_PREGUNTA_RE = re.compile(r"[^.!?\n]*\?+[*_)\]]*")
# Una frase entera (acaba en «.», «!» o «?»), dentro de una línea.
_FRASE_RE = re.compile(r"[^.!?\n]+[.!?]+[*_)\]]*")
# Un párrafo que acaba preguntando: su última línea acaba en «?» (con la negrita o un emoji detrás).
_ACABA_PREGUNTANDO_RE = re.compile(r"\?[*_)\]]*\s*[\U0001F000-\U0001FAFF☀-➿]?\s*$")
# El saludo de Coral del primer turno (`conversational_core._greeting`) y el «¡Hola!» con que el escritor empieza.
_SALUDO_DE_CORAL_RE = re.compile(r"Soy \*Coral\*|I'm \*Coral\*")
_SALUDO_INICIAL_RE = re.compile(r"^\s*(?:¡\s*)?(?:hola|buenas(?: tardes| noches)?|buenos d[ií]as|hi|hello|hey)\b"
                                r"[^.!?\n]{0,25}?[!.,]\s*", re.IGNORECASE)


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


def _sin_las_frases_de(cuerpo: str, pregunta: str) -> str:
    """El cuerpo sin las frases de la pregunta que va al final, dichas ya en el cuerpo: «¡Perfecto, serían 2 personas
    para el minicurso! Puedes salir desde Cartagena… o, si ya estás en las islas…» y debajo «¿Desde dónde saldrías?
    Puedes salir desde Cartagena…» (4 de las 7 respuestas que repiten en caln2-B). Solo frases largas: «¡Perfecto!» no
    es la pregunta."""
    frases = [f.strip() for f in _FRASE_RE.findall(pregunta) if len(_palabras(f)) >= 6]
    if not frases:
        return cuerpo
    quedan = []
    for parrafo in cuerpo.split(_PARRAFO):
        antes = parrafo
        for frase in _FRASE_RE.findall(parrafo):
            if any(_es_la_misma(frase.strip(), f) for f in frases):
                parrafo = parrafo.replace(frase, "", 1)
        if parrafo != antes:
            parrafo = re.sub(r"[ \t]{2,}", " ", parrafo).strip()
        if parrafo.strip():
            quedan.append(parrafo)
    return _PARRAFO.join(quedan)


def _ya_pregunta(cuerpo: str) -> bool:
    """¿Algún párrafo acaba preguntando? (la pregunta del escritor, la de la nota de la tarjeta)."""
    return any(_ACABA_PREGUNTANDO_RE.search(p.strip().splitlines()[-1]) for p in cuerpo.split(_PARRAFO) if p.strip())


def _aplazar(state) -> None:
    """La pregunta de la reserva no se hace este turno: sigue pendiente (`core_pending_slot` no cambia) y se va lo que
    preparó para su respuesta, que el cliente no ve: sus botones y la actividad que recomendaba (gen-8, CAL-C1). Si no,
    un «sí» a la pregunta del escritor («¿quieres que te cuente más del curso?») elegía esa actividad
    (`nucleo/routing._apply_short_answer`)."""
    state.quick_replies = []
    antes = getattr(state, "_sugerida_al_empezar", None)
    if getattr(state, "suggested_activity", None) and state.suggested_activity != antes:
        state.suggested_activity = antes


def _sin_saludo_repetido(respuesta: str, *, escribio: bool = False) -> str:
    """Tras el saludo de Coral, el escritor no vuelve a saludar (CALN-6 paso 2: «¡Hola! 🪸 Soy Coral…» y debajo «¡Hola!
    Bucear en las islas…» en 27 de los 116 primeros turnos de caln2-B). Si en el turno contesta el escritor, que ya da
    la bienvenida a su manera («¡Bienvenidos!», «¡Con mucho gusto te ayudo a armar el plan!»: 4 de 10 en la batería
    CALN4), el saludo se queda en la presentación, sin su frase de calidez."""
    partes = respuesta.split(_PARRAFO)
    for i, parrafo in enumerate(partes[:-1]):
        if _SALUDO_DE_CORAL_RE.search(parrafo):
            if escribio:
                from src.agents.conversational_core import CALIDEZ_DEL_SALUDO  # lazy

                for calidez in CALIDEZ_DEL_SALUDO.values():
                    partes[i] = partes[i].replace(calidez, "")
            resto = _SALUDO_INICIAL_RE.sub("", partes[i + 1], count=1)
            if resto.strip() and resto != partes[i + 1]:
                partes[i + 1] = resto if resto[0] in "¡¿*_" else resto[0].upper() + resto[1:]
            break
    return _PARRAFO.join(partes)


def _sin_el_cierre_si_ya_pregunta(respuesta: str) -> str:
    """La invitación genérica de la tarjeta («¿Te ayudo con algo más?…») cede ante una pregunta concreta de la misma
    respuesta (sparring CALN4, b2 t2: «Would you like help adding the refresher for him?» y la tarjeta con su cierre)."""
    from src.flows.cart_render import CIERRE_DE_LA_TARJETA  # lazy

    partes = respuesta.split(_PARRAFO)
    cierres = [i for i, p in enumerate(partes) if p.strip() in CIERRE_DE_LA_TARJETA.values()]
    otras = [p for i, p in enumerate(partes) if i not in cierres and p.strip()]
    if not cierres or not _ya_pregunta(_PARRAFO.join(otras)):
        return respuesta
    logger.info("[CORE][CALN6] compositor: la respuesta ya pregunta; fuera la invitación genérica de la tarjeta")
    return _PARRAFO.join(otras)


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


def componer(state, respuesta: str, *, pase: bool = False, escribio: bool | None = None) -> str:
    """La respuesta del turno con la pregunta de la reserva una vez y al final (paso 1), si no pregunta ya otra cosa
    (paso 2). En un turno que pasa a un asesor, sus copias salen y no se vuelve a poner: sigue una persona (y la nota
    de la tarjeta, si va, ya pregunta). `escribio`: si en el turno contestó el escritor (sin darlo, lo dice la traza
    del turno, `rag_used`)."""
    if not respuesta:
        return respuesta
    if escribio is None:
        from src.observability import hechos_del_turno  # lazy

        escribio = bool(hechos_del_turno().get("rag_used"))
    respuesta = _sin_el_cierre_si_ya_pregunta(_sin_parrafos_repetidos(_sin_saludo_repetido(respuesta,
                                                                                           escribio=escribio)))
    preguntas = getattr(state, "_preguntas_del_turno", None) or []
    pendiente = state.core_pending_slot
    final = next((texto for slot, texto in reversed(preguntas) if slot == pendiente and texto), None)
    if final is None and not pase:
        return respuesta
    quitada, cuerpo = _sin_las_preguntas(respuesta, [texto for _, texto in preguntas if texto])
    if not quitada:
        return respuesta
    logger.info(f"[CORE][CALN6] compositor: {len(respuesta)} → {len(cuerpo)} caracteres sin las preguntas del turno "
                f"({[slot for slot, _ in preguntas]}), pendiente {pendiente!r}, pase {pase}")
    if pase or final is None:
        return cuerpo
    if _ya_pregunta(cuerpo):
        logger.info(f"[CORE][CALN6] compositor: la respuesta ya pregunta; {pendiente!r} queda para el turno siguiente")
        _aplazar(state)
        return cuerpo
    cuerpo = _sin_las_frases_de(cuerpo, final)
    return f"{cuerpo.rstrip()}{_PARRAFO}{final}" if cuerpo.strip() else final
