"""Los AVISOS que un buen asesor da sin que se los pidan, elegidos y puestos por el CÓDIGO al final de la respuesta.

Historia: CAL-A (16-oct, hallazgo de Álvaro) vio que muchos fallos no eran preguntas sin contestar sino avisos que
faltaban ("el minicurso no certifica", "sin cédula pagas en USD"). Se probó a darlos con modelos (A4 elegía mal, CAL-A6
los añadía con una llamada de Luna al final de cada turno) y la fase LAT (24-oct, corte A) quitó esa llamada: la
calidad bajó porque los avisos dejaron de salir. lat-deuda (26-oct, diseño aprobado por Gadea): los pone el código, sin
ninguna llamada.

- Los avisos son DATOS (`data/knowledge_base/avisos.json`, lo edita el negocio como `policies.json`): cuándo aplican
  y el texto para el cliente en español y en inglés, sacado de su política o ficha.
- `hechos_del_estado(state)`: lo que ya sabemos del cliente en campos estructurados (actividades, origen,
  nacionalidad, inactividad, tamaño del grupo), nunca leyendo el texto del mensaje con patrones.
- El TEMA del mensaje sale de las intenciones de Jev del turno (`state._intenciones`: precio, pago, enlace…), las
  mismas que usa la tabla de hechos; `temas` del fichero dice qué intenciones cuentan para cada tema.
- `poner_avisos(state, respuesta)`: como mucho UNO por turno, los de `una_vez` una sola vez por conversación, y si la
  respuesta ya lo dice no se repite (se apunta como dado). Va al final, delante de la pregunta con la que acaba la
  respuesta si acaba en una.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("uvicorn.error")

AVISOS_PATH = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "avisos.json"

# Cuántos avisos como máximo van en un turno. Empezó en 3, bajó a 2 (se leía como un folleto) y está en UNO desde la
# ronda A/B del golden core del 17-oct: con dos, la respuesta DESPLAZABA lo que ya tenía que decir y en un diálogo se
# quedó sin dar el enlace de reserva (docs/robustness/cal/cal-a5-avisos-condicionados.md §9). Un aviso de más nunca
# vale lo que cuesta perder la respuesta.
MAX_AVISOS = 1


@lru_cache(maxsize=1)
def _datos() -> dict:
    """El fichero de avisos (una vez por proceso). Si no se puede leer, no hay avisos: el turno sigue como hoy."""
    try:
        return json.loads(AVISOS_PATH.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 — nunca romper el turno por los datos
        logger.warning(f"[AVISOS] no se pudo leer {AVISOS_PATH.name}: {exc}")
        return {}


def avisos() -> list[dict]:
    return [a for a in (_datos().get("avisos") or []) if a.get("id") and a.get("aviso_es") and a.get("aviso_en")]


def _temas() -> dict[str, list[str]]:
    return {k: v for k, v in (_datos().get("temas") or {}).items() if not k.startswith("_")}


def temas_del_turno(intenciones: list[str] | None) -> set[str]:
    """Los temas del mensaje según las intenciones de Jev del turno (vacío si Jev calla)."""
    pedidas = set(intenciones or [])
    return {tema for tema, de_jev in _temas().items() if pedidas & set(de_jev)}


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


def _grupo(state) -> int:
    """Cuántas personas constan: el tamaño que leyó el extractor o, si es mayor, la suma del reparto del grupo."""
    reparto = sum(int(n or 0) for n in (getattr(state, "detected_group_allocation", None) or {}).values())
    return max(int(getattr(state, "detected_group_size", None) or 0), reparto)


def hechos_del_estado(state) -> dict:
    """Lo que ya sabemos del cliente, en los campos del estado, para decidir qué avisos aplican (y para que la consulta
    de búsqueda nombre el asunto, CAL-D)."""
    inactivo = getattr(state, "last_dive_over_2_years", None)
    if inactivo is None:
        inactivo = getattr(state, "detected_last_dive_over_2_years", None)
    return {
        "actividades": _actividades_del_estado(state),
        "origen": getattr(state, "location", None),
        "nacionalidad": _nacionalidad(state),
        "inactivo_mas_de_2_anos": bool(inactivo),
        "grupo": _grupo(state),
        "dados": list(getattr(state, "avisos_dados", None) or []),
    }


def _cumple_uno(aviso_id: str, cuando: dict, hechos: dict, temas: set[str]) -> bool:
    if not cuando:
        return False  # un aviso sin ninguna condición saldría en cualquier turno
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
        elif campo == "inactivo_mas_de_2_anos":
            if bool(hechos.get(campo)) != bool(esperado):
                return False
        elif campo == "grupo_min":
            if (hechos.get("grupo") or 0) < esperado:
                return False
        else:
            logger.warning(f"[AVISOS] condición desconocida en {aviso_id}: {campo}")
            return False
    return True


def _cumple(aviso: dict, hechos: dict, temas: set[str]) -> bool:
    """`cuando` es un juego de condiciones (TODAS se cumplen) o una lista de juegos (basta con uno)."""
    cuando = aviso.get("cuando") or {}
    juegos = cuando if isinstance(cuando, list) else [cuando]
    return any(_cumple_uno(aviso["id"], juego, hechos, temas) for juego in juegos)


def seleccionar(hechos: dict, temas: set[str]) -> list[dict]:
    """Los avisos que aplican a este turno, en el orden del fichero: se cumplen sus condiciones y, si son de
    `una_vez`, no se han dado."""
    dados = set(hechos.get("dados") or [])
    return [a for a in avisos() if not (a.get("una_vez") and a["id"] in dados) and _cumple(a, hechos, temas)]


def _ya_lo_dice(texto: str, respuesta: str) -> bool:
    """La respuesta ya lo dice: la misma comprobación que la tabla de hechos usa para un dato (sus palabras con
    contenido, recortadas, están casi todas)."""
    from src.flows import hechos as hechos_mod  # lazy

    return hechos_mod._elemento_dado(texto, hechos_mod._raices(respuesta), respuesta)


_PREGUNTA_AL_FINAL = re.compile(r"\?[^\w]*$")
_FRASES = re.compile(r"(?<=[.!?…])\s+")
_CON_LETRAS = re.compile(r"\w")


def _insertar(respuesta: str, aviso: str) -> str:
    """El aviso va al final; si la respuesta acaba preguntando algo, delante de esa pregunta, que sigue siendo lo
    último que lee el cliente."""
    cuerpo = respuesta.rstrip()
    antes, salto, ultima = cuerpo.rpartition("\n")
    frases: list[str] = []
    for trozo in _FRASES.split(ultima):
        if frases and not _CON_LETRAS.search(trozo):
            frases[-1] = f"{frases[-1]} {trozo}"  # un emoji suelto tras la pregunta es de esa frase
        else:
            frases.append(trozo)
    corte = len(frases)
    while corte > 0 and _PREGUNTA_AL_FINAL.search(frases[corte - 1]):
        corte -= 1
    if corte == len(frases):
        return f"{cuerpo}\n\n{aviso}"
    previas, preguntas = " ".join(frases[:corte]), " ".join(frases[corte:])
    delante = f"{antes}{salto}{previas}" if previas else antes
    return "\n\n".join(p for p in (delante.rstrip(), aviso, preguntas) if p)


def poner_avisos(state, respuesta: str) -> str:
    """Añade a la respuesta del turno el aviso que el cliente necesita y no ha preguntado (como mucho uno)."""
    if not isinstance(respuesta, str) or not respuesta.strip():
        return respuesta
    from src.observability import note_turn  # lazy

    lang = "en" if getattr(state, "language", "es") == "en" else "es"
    hechos = hechos_del_estado(state)
    temas = temas_del_turno(getattr(state, "_intenciones", None))
    puestos = 0
    for aviso in seleccionar(hechos, temas):
        if puestos >= MAX_AVISOS:
            break
        texto = aviso[f"aviso_{lang}"]
        if aviso.get("una_vez"):
            state.avisos_dados.append(aviso["id"])
        if _ya_lo_dice(texto, respuesta):
            logger.info(f"[AVISOS] {aviso['id']}: la respuesta ya lo dice")
            continue
        respuesta = _insertar(respuesta, texto)
        puestos += 1
        logger.info(f"[AVISOS] {aviso['id']} al final de la respuesta")
        note_turn(aviso=aviso["id"])
    return respuesta
