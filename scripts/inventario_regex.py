"""Inventario de las expresiones regulares del bot (estudio del 9-oct, Gadea): cuántas hay, dónde y QUÉ deciden.

Recorre `src/`, encuentra cada grupo de patrones (una asignación con `re.compile` o con patrones r'...') y lo clasifica
por familia: no es lo mismo un regex que ENTIENDE al cliente (riesgo de vocabulario) que uno que tapa un número de
tarjeta. La familia sale de las reglas de abajo (fichero + nombre); lo que no casa queda "sin clasificar" para revisarlo.

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
ATAJO_OFF = "atajo de texto fijo (APAGADO: código muerto con RAG_V2/S4_FIXES)"
GUARDA = "guarda sobre la respuesta del bot"
LLM = "leer la salida de un LLM"
FORMATO = "formato y datos internos"
PRIVACIDAD = "privacidad"

# (fichero, nombre exacto o prefijo) -> familia. El orden importa: la primera que casa.
REGLAS = [
    ("privacy.py", "*", PRIVACIDAD),
    ("formato.py", "*", FORMATO),
    ("fuzzy.py", "*", FORMATO),
    ("cart_render.py", "*", FORMATO),
    ("activities.py", "*", FORMATO),
    ("lead_summary.py", "*", FORMATO),
    ("grounding_check.py", "_FACT_NO", LLM),
    ("grounding_check.py", "frases", LLM),
    ("grounding_check.py", "*", GUARDA),
    ("vector_store.py", "*", ENTENDER),  # TOPIC_PATTERNS: temas de la pregunta para la búsqueda
    ("rag_agent.py", ("FOOD_QUERY_PATTERN", "DIETARY_QUERY_PATTERN", "_FOOD_HIJACK_GUARD", "_PRICE_QUESTION",
                      "_PRICE_SPECIFIC", "_PRICE_SINGLE_SERVICE_PATTERNS", "_PRICE_NON_CATALOG_RE",
                      "_REFRESHER_COST_QUESTION_RE"), ATAJO_OFF),
    ("rag_agent.py", ("_OVERVIEW_PHRASE", "_OVERVIEW_BARE_WORD_RE", "_OVERVIEW_DIVING_WORD", "_OVERVIEW_EXCLUDE"), ATAJO_ON),
    ("rag_agent.py", "*", ENTENDER),
    ("supervisor.py", ("_ALCOHOL_BEFORE_DIVING_RE", "_ALLERGY_WORD_RE", "_FOOD_ALLERGEN_RE", "_AI_IDENTITY_RE",
                       "_SAME_PRICE_DIFFERENT_NATIONALITY_RE"), ATAJO_ON),
    ("supervisor.py", "*", ENTENDER),
    ("conversational_core.py", ("_PREGUNTA_ORIGEN_RE", "_IMPORTE_RE", "_FRASE_RE", "_DEPENDE_DEL_ORIGEN_RE",
                                "_HORA_DEL_RESUMEN", "_PIDE_PRECIO_RE", "_PRECIO_AJENO_RE", "_PISTA_ORIGEN_RE"), GUARDA),
    ("conversational_core.py", "*", ENTENDER),
    ("intent_detector.py", "*", ENTENDER),
]


def familia(fichero: str, nombre: str) -> str:
    for f, nombres, fam in REGLAS:
        if fichero.endswith(f) and (nombres == "*" or nombre in (nombres if isinstance(nombres, tuple) else (nombres,))):
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
