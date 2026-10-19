"""Inventario de las expresiones regulares del bot (estudio del 9-oct, Gadea): cuántas hay, dónde y QUÉ deciden.

Recorre `src/`, encuentra cada grupo de patrones (una asignación con `re.compile` o con patrones r'...') y lo clasifica
por familia: no es lo mismo un regex que ENTIENDE al cliente (riesgo de vocabulario) que uno que tapa un número de
tarjeta. La familia sale de las reglas de abajo (fichero o carpeta + nombre); lo que no casa queda "sin clasificar" para
revisarlo.

ex-9 paso 0 (19-oct, docs/robustness/regex/estudio-ex9-regex.md): las reglas iban por NOMBRE de fichero y tras el reparto
de s4-2 los módulos de `agents/nucleo/` y `agents/rutas/` salían "sin clasificar" (192 patrones); ahora van por carpeta.
Los tres de `conversational_core` que leen el mensaje del cliente para decidir si pide precio (`_PIDE_PRECIO_RE`,
`_PRECIO_AJENO_RE`, `_PISTA_ORIGEN_RE`) son de "entender", no guardas de la respuesta. Y la familia "lista cerrada o
formato" separa lo que casa nombres fijos del catálogo (hoteles e islas) o solo parte/normaliza el texto
(tokenizadores, ¿hay una cifra?, el saludo): no intenta entender lo que dice el cliente.

    python -m scripts.inventario_regex                      # resumen por familia
    python -m scripts.inventario_regex --json docs/robustness/regex/inventario.json
"""
import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

LITERAL = re.compile(r"""(?<![A-Za-z0-9_])[rR][bB]?(?:'''|\"\"\"|'|")""")

ENTENDER = "entender al cliente"
ATAJO_ON = "atajo de texto fijo (activo)"
GUARDA = "guarda sobre la respuesta del bot"
LLM = "leer la salida de un LLM"
FORMATO = "formato y datos internos"
LISTA = "lista cerrada o formato"
PRIVACIDAD = "privacidad"

# Atajos de texto fijo de las rutas (antes de s4-2 vivían en supervisor.py).
ATAJOS_RUTAS = ("_ALCOHOL_BEFORE_DIVING_RE", "_ALLERGY_WORD_RE", "_FOOD_ALLERGEN_RE", "_AI_IDENTITY_RE",
                "_SAME_PRICE_DIFFERENT_NATIONALITY_RE")
# Tokenizadores de intent_detector (`re.findall(r"\w+", ...)`) y los que montan patrones del registro de actividades.
TOKENIZADORES = ("token_sets", "name", "alternatives", "text", "words", "writer", "rest")

# (fichero o carpeta, nombre exacto o tupla de nombres) -> familia. El orden importa: la primera que casa. Un fichero
# casa por el final de su ruta ("supervisor.py", "rutas/router.py"); una carpeta acaba en "/" ("agents/nucleo/") y casa
# con todos los ficheros de dentro.
REGLAS = [
    ("privacy.py", "*", PRIVACIDAD),
    ("formato.py", "*", FORMATO),
    ("fuzzy.py", "*", FORMATO),
    ("cart_render.py", "*", FORMATO),
    ("activities.py", "*", FORMATO),
    ("lead_summary.py", "*", FORMATO),
    ("extractor_turno.py", "*", FORMATO),  # trocea la cita del extractor y limpia el último mensaje del bot
    ("grounding_check.py", "_FACT_NO", LLM),
    ("grounding_check.py", "frases", LLM),
    ("grounding_check.py", "*", GUARDA),
    ("juez_segunda_opinion.py", "*", LLM),
    ("vector_store.py", "*", ENTENDER),  # TOPIC_PATTERNS: temas de la pregunta para la búsqueda
    ("rag_agent.py", ("_OVERVIEW_PHRASE", "_OVERVIEW_BARE_WORD_RE", "_OVERVIEW_DIVING_WORD", "_OVERVIEW_EXCLUDE"), ATAJO_ON),
    ("rag_agent.py", "item", LLM),  # lee el motivo de rechazo del juez de grounding
    ("rag_agent.py", "*", ENTENDER),
    ("agents/rutas/", ATAJOS_RUTAS, ATAJO_ON),
    ("rutas/router.py", "cleaned", LISTA),  # normaliza el mensaje antes de comparar con los botones
    ("agents/rutas/", "*", ENTENDER),
    ("agents/nucleo/", "*", ENTENDER),
    ("supervisor.py", "*", ENTENDER),
    ("conversational_core.py", ("_EXPLICIT_NUMBER_RE", "norm", "texto"), LISTA),  # ¿hay una cifra?, saludo, formato
    ("conversational_core.py", ("_PREGUNTA_ORIGEN_RE", "_IMPORTE_RE", "_FRASE_RE", "_DEPENDE_DEL_ORIGEN_RE",
                                "_HORA_DEL_RESUMEN"), GUARDA),
    ("conversational_core.py", "*", ENTENDER),  # incluye _PIDE_PRECIO_RE, _PRECIO_AJENO_RE y _PISTA_ORIGEN_RE
    ("intent_detector.py", ("hotel_patterns", "island_patterns"), LISTA),  # hoteles e islas del catálogo
    ("intent_detector.py", TOKENIZADORES, LISTA),
    ("intent_detector.py", "*", ENTENDER),
]


def _casa_fichero(fichero: str, donde: str) -> bool:
    if donde.endswith("/"):
        return f"/{donde}" in f"/{fichero}"
    return fichero.endswith(donde)


def familia(fichero: str, nombre: str) -> str:
    for donde, nombres, fam in REGLAS:
        if _casa_fichero(fichero, donde) and (
                nombres == "*" or nombre in (nombres if isinstance(nombres, tuple) else (nombres,))):
            return fam
    return "sin clasificar"


def inventario(raiz: Path = Path("src")) -> list[dict]:
    filas = []
    for p in sorted(raiz.rglob("*.py")):
        src = p.read_text(encoding="utf-8")
        arbol = ast.parse(src)
        vistos: set[int] = set()
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.Assign, ast.AnnAssign)) or nodo.lineno in vistos:
                continue
            seg = ast.get_source_segment(src, nodo) or ""
            n = len(LITERAL.findall(seg))
            if not n or ("re.compile" not in seg and n < 1):
                continue
            vistos.add(nodo.lineno)
            destino = nodo.targets[0] if isinstance(nodo, ast.Assign) else nodo.target
            nombre = (ast.get_source_segment(src, destino) or "?").strip()
            fichero = p.as_posix()
            filas.append({"fichero": fichero, "linea": nodo.lineno, "nombre": nombre, "patrones": n,
                          "familia": familia(fichero, nombre)})
    return filas


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", help="guarda el inventario completo en este fichero")
    a = ap.parse_args()
    filas = inventario()
    por_familia: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for f in filas:
        por_familia[f["familia"]][0] += 1
        por_familia[f["familia"]][1] += f["patrones"]
    total = sum(v[1] for v in por_familia.values())
    print(f"{len(filas)} grupos, {total} patrones")
    for fam, (g, n) in sorted(por_familia.items(), key=lambda kv: -kv[1][1]):
        print(f"  {n:4} patrones ({100 * n / total:4.1f} %) · {g:3} grupos · {fam}")
    por_fichero: dict[str, int] = defaultdict(int)
    for f in filas:
        if f["familia"] == ENTENDER:
            por_fichero[f["fichero"]] += f["patrones"]
    print("\n'entender al cliente' por fichero:")
    for fichero, n in sorted(por_fichero.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4}  {fichero}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps({"familias": {k: {"grupos": v[0], "patrones": v[1]} for k, v in por_familia.items()},
                                            "grupos": filas}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
