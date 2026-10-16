"""CAL-A (fase CAL, 16-oct, reabierta por Gadea): los AVISOS que un buen asesor da sin que se los pidan, elegidos por
el código con el estado de la conversación.

Hallazgo de Álvaro (A0-A4, docs/robustness/cal/revision-plan-2026-10-16.md): estos fallos del RAG no son preguntas sin
contestar sino avisos que faltan ("el minicurso no certifica", "sin cédula pagas en USD", "no operamos en Barú"). El
plan (A2) no podía saberlos porque no lee la información de la empresa; el revisor de avisos (A4) sí la lee y fue lo
único que movió la aguja (47 -> 42 de 48), pero ELEGÍA mal con un modelo pequeño (metía avisos que no tocaban).

Aquí la elección la hace el código y los avisos son DATOS (`data/knowledge_base/avisos.json`, lo edita el negocio como
`policies.json`):

- `hechos_del_estado(state)`: lo que ya sabemos del cliente en campos estructurados (actividad elegida o detectada,
  origen, nacionalidad, inactividad), nunca leyendo el texto del mensaje con patrones. NO hay listas de nombres de
  lugares ni de palabras: un aviso que depende de dónde está el cliente espera a que el dato esté en el estado.
- `temas_de_los_docs(docs)`: de qué va la pregunta según los documentos que la BÚSQUEDA recuperó (sus `topics` y su
  clave de política o ficha), no según el texto del cliente.
- `seleccionar(hechos, temas)`: los avisos cuyas condiciones se cumplen todas; los de `una_vez` solo si no se han dado.
- `bloque_de_avisos(...)`: lo que se añade al mensaje de la redacción como puntos OBLIGATORIOS. El texto final lo
  redacta el RAG con la política o ficha (están en su contexto); el aviso solo obliga a decirlo.

El revisor de completitud de A3 (`rag_plan.puntos_sin_cubrir`) comprueba que estén, y si falta alguno se reintenta una
vez: el mecanismo de A4 con la elección hecha por datos. Todo detrás del flag `avisos_condicionados` (apagado hasta
medirlo con el banco, 3 repeticiones).
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("uvicorn.error")

AVISOS_PATH = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "avisos.json"

# Cuántos avisos como máximo van en un turno: con más, la respuesta deja de ser una respuesta y se lee como un folleto
# (visto el 16-oct con tres avisos pegados al final). A4 usaba 2.
MAX_AVISOS = 2


@lru_cache(maxsize=1)
def _datos() -> dict:
    """El fichero de avisos (una vez por proceso). Si no se puede leer, no hay avisos: el turno sigue como hoy."""
    try:
        return json.loads(AVISOS_PATH.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 — nunca romper el turno por los datos
        logger.warning(f"[AVISOS] no se pudo leer {AVISOS_PATH.name}: {exc}")
        return {}


def avisos() -> list[dict]:
    return [a for a in (_datos().get("avisos") or []) if a.get("id") and a.get("aviso_es")]


def _temas() -> dict[str, list[str]]:
    return {k: v for k, v in (_datos().get("temas") or {}).items() if not k.startswith("_")}


def _actividades_del_estado(state) -> set[str]:
    """Las actividades que constan: la elegida en el árbol, la que detectó el extractor, las del carrito y las del
    reparto del grupo. Ids del registro (`src/domain/activities.py`), nunca deducidas del texto."""
    from src.domain import activities as dom  # lazy (el registro lee ficheros)

    ids: set[str] = set()
    for servicio in (getattr(state, "selected_service", None), getattr(state, "detected_service_id", None)):
        actividad = dom.activity_for_service(servicio) if servicio else None
        if actividad:
            ids.add(actividad.id)
    for directa in (getattr(state, "detected_activity", None),):
        if directa:
            ids.add(directa)
    for item in getattr(state, "mixed_cart", None) or []:
        servicio = item.get("service_id") if isinstance(item, dict) else None
        actividad = dom.activity_for_service(servicio) if servicio else None
        if actividad:
            ids.add(actividad.id)
        tipo = item.get("type") if isinstance(item, dict) else None
        por_tipo = dom.cart_activity_for_type(tipo) if tipo else None
        if por_tipo:
            ids.add(por_tipo)
    for actividad_id, cuantos in (getattr(state, "detected_group_allocation", None) or {}).items():
        if cuantos and actividad_id != "undecided":
            ids.add(actividad_id)
    # El refresher no es una actividad que el cliente elija (se vende como el minicurso): consta por sus campos.
    if getattr(state, "refresher_interested", None) or getattr(state, "last_dive_over_2_years", None):
        ids.add("refresher")
    # Buzo certificado: la actividad que haría es el buceo certificado (lo dice el extractor, no se deduce del texto).
    if getattr(state, "is_certified", None) is True:
        ids.add("certified_diving")
    return {dom.resolved_activity_id(i) for i in ids if i}


def _nacionalidad(state) -> str | None:
    """'mixto' manda sobre lo demás: con el grupo mezclado la nacionalidad de quien escribe se guarda como extranjera
    (decisión de Gadea del 14-sep: todo en USD), así que primero se mira el aviso de grupo mixto."""
    if getattr(state, "mixed_nationality_notice", False) or getattr(state, "mixed_final_is_colombian", None) is False \
            and getattr(state, "mixed_nationality_notice", False):
        return "mixto"
    es_colombiano = getattr(state, "is_colombian", None)
    if es_colombiano is True:
        return "colombiano"
    if es_colombiano is False:
        return "extranjero"
    return None


def hechos_del_estado(state) -> dict:
    """Lo que ya sabemos del cliente, en los campos del estado, para decidir qué avisos aplican."""
    inactivo = getattr(state, "last_dive_over_2_years", None)
    if inactivo is None:
        inactivo = getattr(state, "detected_last_dive_over_2_years", None)
    return {
        "actividades": _actividades_del_estado(state),
        "origen": getattr(state, "location", None),
        "nacionalidad": _nacionalidad(state),
        "inactivo_mas_de_2_anos": bool(inactivo),
        # Pendiente: las fechas del cliente no están en el estado (campo del extractor, CAL-C), así que el aviso de
        # "el plan no cabe en tu estancia" todavía no puede cumplirse.
        "estancia_menor_que_plan": False,
        "dados": list(getattr(state, "avisos_dados", None) or []),
    }


# Cuántos documentos cuentan como "lo más parecido a la pregunta". Medido con `scripts/sonda_avisos.py` (16-oct): la
# búsqueda devuelve 8-12 documentos y los `topics` de todos juntos cubren 10 de los 13 temas, así que valen de poco; la
# CLAVE de los primeros sí dice de qué va la pregunta (la política de la comida para la comida, la del pago para el pago).
TOPE_FUENTES = 4
TOPE_TOPICS = 2


def _claves(doc: dict) -> set[str]:
    """Lo que identifica al documento, sin prefijos: su clave (`politica:food_policy` -> `food_policy`, `faq:20` -> `20`,
    `ficha:refresher:minicourse` -> `minicourse`), su sección y su subtipo (de una ficha de servicio: `pricing`,
    `included`, `requirements`…, que dice QUÉ PARTE de la ficha casó con la pregunta).

    Sin quitar el prefijo no casaba ninguna clave de política y el tema salía solo de los `topics` (16-oct)."""
    metadata = doc.get("metadata") or {}
    return {str(v).split(":")[-1] for k in ("key", "section", "subtype") if (v := metadata.get(k))}


def _clave(doc: dict) -> str | None:
    """La clave principal del documento (para la traza y las sondas)."""
    metadata = doc.get("metadata") or {}
    bruta = metadata.get("key") or metadata.get("section") or metadata.get("subtype")
    return str(bruta).split(":")[-1] if bruta else None


def temas_de_los_docs(docs: list[dict] | None) -> set[str]:
    """De qué va la pregunta, según los documentos que trajo la búsqueda: la CLAVE de todos ellos (política, sección o
    subtipo de ficha, que identifica el documento) y los `topics` solo de los primeros que NO son fichas de servicio.

    Los `topics` los detecta una expresión regular sobre el texto del documento: una pregunta frecuente o una política
    trae dos o tres y dicen de qué va; una ficha de servicio trae DIEZ (su itinerario habla de horarios, profundidad,
    equipo, fotos…), así que en una pregunta de precio hacía saltar "la profundidad depende del nivel" (medido el
    16-oct con la sonda sobre los casos de CAL-C)."""
    senales = {c for doc in (docs or []) for c in _claves(doc)}
    sin_fichas = [d for d in (docs or []) if (d.get("metadata") or {}).get("source") != "services"]
    for doc in sin_fichas[:TOPE_TOPICS]:
        senales |= {str(t) for t in ((doc.get("metadata") or {}).get("topics") or [])}
    return {tema for tema, claves in _temas().items() if senales & set(claves)}


def fuentes_recuperadas(docs: list[dict] | None) -> set[str]:
    """Las claves de los PRIMEROS documentos: lo que la búsqueda considera más parecido a la pregunta. Un aviso que no
    depende de nada del cliente solo se da si la búsqueda ha traído SU PROPIA fuente aquí (si la pregunta va de eso)."""
    return {c for doc in (docs or [])[:TOPE_FUENTES] for c in _claves(doc)}


def _depende_del_cliente(aviso: dict) -> bool:
    """Si el aviso tiene alguna condición sobre lo que sabemos del cliente (y no solo sobre la pregunta)."""
    return bool((aviso.get("cuando") or {}).keys() - {"tema"})


def _cumple(aviso: dict, hechos: dict, temas: set[str], fuentes: set[str]) -> bool:
    cuando = aviso.get("cuando") or {}
    actividades = hechos.get("actividades") or set()
    for campo, esperado in cuando.items():
        if campo in ("actividad", "actividad_tambien"):
            if not (set(esperado) & actividades):
                return False
        elif campo == "tema":
            if not (set(esperado) & temas):
                return False
        elif campo in ("origen", "nacionalidad"):
            if hechos.get(campo) != esperado:
                return False
        elif campo in ("inactivo_mas_de_2_anos", "estancia_menor_que_plan"):
            if bool(hechos.get(campo)) != bool(esperado):
                return False
        else:
            logger.warning(f"[AVISOS] condición desconocida en {aviso['id']}: {campo}")
            return False
    if not _depende_del_cliente(aviso):
        # Avisos que solo dependen de la pregunta (las fotos, los horarios, el cierre del sistema): el tema del montón
        # de documentos los hacía salir en cualquier turno (medido el 16-oct). Hace falta que la búsqueda haya traído
        # su propia fuente entre las primeras: entonces la pregunta va de eso.
        return _fuente(aviso) in fuentes
    return True


def _fuente(aviso: dict) -> str:
    return str(aviso.get("fuente", "")).split(":")[-1]


def seleccionar(hechos: dict, temas: set[str], fuentes: set[str] | None = None) -> list[dict]:
    """Los avisos que aplican a este turno: se cumplen TODAS sus condiciones y, si son de `una_vez`, no se han dado.
    `fuentes`: las claves de los primeros documentos recuperados (ver `fuentes_recuperadas`)."""
    dados = set(hechos.get("dados") or [])
    fuentes = fuentes or set()
    elegidos = [a for a in avisos()
                if not (a.get("una_vez") and a["id"] in dados) and _cumple(a, hechos, temas, fuentes)]
    # Si aplican más de `MAX_AVISOS`, primero los que la BÚSQUEDA señala como más relacionados con la pregunta (su
    # fuente está entre los primeros documentos): así los dos huecos no se los queda el orden del fichero.
    elegidos.sort(key=lambda a: _fuente(a) not in fuentes)
    if elegidos:
        logger.info(f"[AVISOS] {len(elegidos)} aplican: {[a['id'] for a in elegidos[:MAX_AVISOS]]}")
    return elegidos[:MAX_AVISOS]


def textos(elegidos: list[dict]) -> list[str]:
    return [a["aviso_es"] for a in elegidos]


def bloque_de_avisos(elegidos: list[dict], lang: str) -> str:
    """Lo que se añade al mensaje de la redacción: lo que hay que avisar, con su fuente, en el idioma del cliente."""
    lista = "\n".join(f"- {a['aviso_es']} (fuente: {a.get('fuente', '')})" for a in elegidos)
    if lang == "es":
        return ("AVISOS QUE TU RESPUESTA TIENE QUE DAR (el cliente los necesita aunque no los pregunte): "
                "dilos DENTRO de lo que contestas, cada uno en una frase y con el dato del contexto, donde encajen "
                "con lo que está preguntando. No los pongas como lista ni como párrafos aparte al final, y no cambies "
                "lo que ya contestabas bien:\n" + lista)
    return ("WARNINGS YOUR ANSWER MUST GIVE (the customer needs them even if they don't ask): say them INSIDE what "
            "you answer, one sentence each, with the fact from the context, where they fit what they are asking. Not "
            "as a list or as separate paragraphs at the end, and without changing what you already answered well. "
            "They are written in Spanish for you; say them in English:\n" + lista)
