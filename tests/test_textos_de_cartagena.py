"""Textos fijos del flujo en el español de Cartagena (gen, 20-oct, decisión de Gadea; promocionado, su flag
`textos_de_cartagena` y `flows/textos.py` se borraron en sim-5).

- "ustedes" en vez de "vosotros", sin género supuesto ("¡tranqui!") y la pregunta del origen dice que desde Cartagena
  se sale del Muelle de la Bodeguita (no "podemos recogerte").
- Guarda para el futuro: ningún texto del bot (las cadenas de `src/`, sin docstrings) usa "vosotros" ni dice que se
  recoge en Cartagena."""

import ast
import re
from pathlib import Path


from src.agents import conversational_core as core
from src.flows.state import ConversationState

VOSOTROS = re.compile(
    r"\b(sois|vosotr[oa]s|vuestr[oa]s?|os (ayudo|interesa|gustar[ií]a|paso|escribe|recog\w*)|"
    r"(ten|quer|pod|sab|hab|est)[eé]is|est[aá]is|vais)\b", re.IGNORECASE)
RECOGE_EN_CARTAGENA = re.compile(r"recoger(te|los|les)? saliendo|pick you up \*?from Cartagena", re.IGNORECASE)


def _cadenas_del_bot():
    """(fichero, línea, texto) de cada cadena de src/ que no es un docstring."""
    for f in sorted(Path("src").rglob("*.py")):
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        fuera: set[int] = set()
        for nodo in ast.walk(arbol):
            cuerpo = getattr(nodo, "body", None)
            if isinstance(cuerpo, list) and cuerpo and isinstance(cuerpo[0], ast.Expr) \
                    and isinstance(cuerpo[0].value, ast.Constant) and isinstance(cuerpo[0].value.value, str):
                fuera.add(id(cuerpo[0].value))  # docstring
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and id(nodo) not in fuera:
                yield f, nodo.lineno, nodo.value


def test_ningun_texto_del_bot_usa_vosotros_ni_recoge_en_cartagena():
    malos = [f"{f}:{n} {t[:80]!r}" for f, n, t in _cadenas_del_bot()
             if VOSOTROS.search(t) or RECOGE_EN_CARTAGENA.search(t)]
    assert not malos, "\n".join(malos)


def _estado(n: int | None = None) -> ConversationState:
    st = ConversationState(conversation_id="textos-cartagena", language="es")
    st.detected_group_size = n
    return st


def test_la_pregunta_del_origen():
    texto = core._pregunta_origen("es")
    assert "Puedes salir *desde Cartagena* (desde el Muelle de la Bodeguita)" in texto and "recogerte" not in texto


def test_la_pregunta_del_origen_en_ingles():
    texto = core._pregunta_origen("en", mismo_dia=True)
    assert "from Muelle de la Bodeguita, round trip, same day" in texto and "pick you up *from" not in texto


def test_recordar_cuantos_son():
    assert core._recall_answer(_estado(4), "group_size") == "Me dijiste que son *4* personas."
