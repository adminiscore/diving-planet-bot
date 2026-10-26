"""ARQ-1d (22-oct, fase ARQ: el modelo interpreta, el código decide, el modelo redacta): el REDACTOR de hechos.

Diseño: `docs/robustness/arq/diseno-intenciones-y-hechos.md` §3. Si Jev dice que el mensaje solo pide intenciones de la
tabla (precio, qué incluye, requisitos, horario, disponibilidad, edad, enlace) y se sabe de qué actividad habla, el
código saca los hechos (`src/flows/hechos.py`) y Luna solo los pone en palabras, con el estilo de Coral y sin el
catálogo, las políticas ni las reglas del RAG (el 21-oct, con todo eso delante, recortaba las listas que tenía). Lo
demás sigue en el RAG de siempre: aquí se devuelve None y contesta él. Con el flag `hechos_por_codigo` apagado no se
llama.
"""
from __future__ import annotations

import copy
import json
import logging
import re

from openai import AsyncOpenAI

from src.agents.grounding_check import (
    contains_phone_number,
    currency_amounts_grounded,
    is_coherent_text,
    urls_grounded,
)
from src.config import settings
from src.domain import activities as dom
from src.flows import hechos as hechos_mod
from src.flows.state import ConversationState
from src.llm_client import trace_openai
from src.privacy import redact_pii
from src.utils.text import strip_accents

logger = logging.getLogger("uvicorn.error")

# Mensajes anteriores que ve el redactor: para el tono y no volver a saludar, no para sacar datos (los datos son los
# hechos).
_HISTORIAL = 6
_LUGAR_DE_JEV = {"cartagena": "cartagena", "islands": "island"}
# La palabra con la que el redactor dice que los hechos no contestan lo que pregunta (ver REDACTOR_HECHOS_*).
_FALTA = "FALTA"


def _actividad(state: ConversationState, datos: dict) -> str | None:
    """La actividad de la que pregunta ESTE mensaje (extractor) o, si no nombra ninguna, la de la conversación SI es
    una sola. arq-1k (G10 nº 2): hablaban de snorkel para los niños y de buceo para el padre, «¿qué incluye?» y el
    redactor contestaba lo del buceo; con varias en juego no se adivina: contesta el RAG, que ve la conversación."""
    for actividad in (datos.get("actividad_preguntada"), datos.get("activity")):
        if actividad and dom.by_id(actividad) is not None:
            return actividad
    elegida = dom.activity_for_service(state.selected_service) if state.selected_service else None
    reparto = state.detected_group_allocation or {}
    en_juego = {a for a in (state.actividad_preguntada, state.detected_activity, elegida.id if elegida else None,
                            *(a for a, n in reparto.items() if n)) if a and dom.by_id(a) is not None}
    repaso = any(x is True for x in (datos.get("refresher_interested"), datos.get("last_dive_over_2_years"),
                                     state.refresher_interested, state.last_dive_over_2_years))
    if repaso and en_juego <= {"certified_diving", "minicourse", "refresher"}:
        # arq-1n (G10 nº 2): el certificado con más de 2 años sin bucear hace primero el refresher (se reserva como el
        # minicurso); sin esto, «¿qué incluye?» desde Ubuntu salía con el almuerzo del buceo desde Cartagena.
        return "refresher"
    if len(en_juego) == 1:
        return en_juego.pop()
    if not en_juego and state.suggested_activity and dom.by_id(state.suggested_activity) is not None:
        return state.suggested_activity  # la que acaba de proponer el bot («¿y qué incluye?»)
    return None


def _actividades(state: ConversationState, datos: dict) -> list[str]:
    """La actividad del mensaje (y, si es genérica, las concretas de su familia)."""
    una = _actividad(state, datos)
    registro = dom.by_id(una) if una else None
    if registro is not None and registro.generic:
        # arq-1n (G10 nº 2): «¿cuánto cuestan las especialidades?» no tenía hechos (lo genérico no tiene planes) y el
        # RAG las nombraba sin precio. Se abre en las actividades concretas de su familia, con plan.
        return [a.id for a in dom.registry().activities if a.family == registro.family and not a.generic
                and (dom.service_ids(a.id, "cartagena") or dom.service_ids(a.id, "island"))]
    return [una] if una else []


def _origen(state: ConversationState, datos: dict, leido: bool = False) -> str | None:
    """`leido`: el extractor leyó el mensaje (aunque no traiga nada). DEUDA-ORIGEN (26-oct): entonces el lugar de Jev
    no fija el origen ("Estaremos visitando Cartagena…" no dice la salida): van los dos precios y se pregunta."""
    for lugar in (state.location, state.detected_location, datos.get("location")):
        if lugar in hechos_mod.ORIGENES:
            return lugar
    from src.agents.jev_router import CUSTOMER_PLACE_MIN  # lazy

    lugar = getattr(state, "_jev_lugar", None) or {}  # gen-15: «nos alojamos en Mulata» lo dice Jev, no una palabra
    if not leido and (lugar.get("confidence") or 0.0) >= CUSTOMER_PLACE_MIN:
        return _LUGAR_DE_JEV.get(lugar.get("choice"))
    if datos.get("hotel"):
        # arq-8b: «We'll be staying at the Ubuntu hotel… how much…?» con Jev a 0,52 en el lugar: el extractor lee el hotel
        # y CAL-C3e lo sabe de las islas, pero el origen lo pone al guardar, después de contestar; el redactor daba las
        # dos variantes y preguntaba desde dónde sale (banco arq-8b variantes, v5 3/3).
        if _hotel_de_las_islas(str(datos["hotel"])):
            return "island"
    return None


_GENERICAS_DE_HOTEL = {"hotel", "eco", "the", "el"}


def _sin_genericas(nombre: str) -> str:
    plano = strip_accents((nombre or "").lower())
    return " ".join(p for p in re.findall(r"[a-z0-9]+", plano) if p not in _GENERICAS_DE_HOTEL)


def _hotel_de_las_islas(nombre: str) -> bool:
    """arq-8b: ¿el hotel que nombra el cliente es de las islas? En cualquiera de las dos listas que ya usa el bot: el
    catálogo del detector (CAL-C3e: Ubuntu, Secreto, Pao Pao…) y los de la base (gen-15, policies.json: Mulata, Rosario
    de Mar, Eco Hotel Las Palmeras…, que el detector no tiene). Sin tildes, mayúsculas ni «hotel»/«eco»."""
    from src.agents.extractor_turno import HOTELES_DE_LA_BASE  # lazy
    from src.agents.nucleo.extractor import _hotel_del_catalogo  # lazy

    if _hotel_del_catalogo(nombre):
        return True
    dicho = _sin_genericas(nombre)
    if len(dicho) < 4:
        return False
    # Solo «el nombre de la base está en lo que dijo» (no al revés: «Hotel San Pedro», en Cartagena, no es Majagua).
    return any((base := _sin_genericas(h)) and base in dicho for h in HOTELES_DE_LA_BASE)


def _foto(state: ConversationState, datos: dict, origen: str | None, message: str = "",
          history: list[dict] | None = None) -> ConversationState:
    """Una copia del estado con lo que dice ESTE mensaje (origen y nacionalidad): la extracción aún no lo ha guardado
    cuando se contesta (como gen-14 en el RAG). El estado de verdad lo sigue escribiendo la extracción."""
    foto = copy.copy(state)
    foto.location = origen
    if foto.is_colombian is None and datos.get("is_colombian") is not None:
        foto.is_colombian = datos["is_colombian"]
    if datos.get("mixed_nationality") is True:
        foto.mixed_nationality_notice = True
    if datos.get("paquete_varios_dias") is True:
        foto.detected_duration = "multi_day"  # arq-1t: «el paquete de varios días» en ESTE mensaje
    if origen == "cartagena":
        # arq-5f: el extractor deja Barú como Cartagena (gen-6) sin otra marca; los hechos dicen por qué sale de allí.
        from src.agents.extractor_turno import _solo_baru  # lazy

        dicho = [message, *(m.get("content") or "" for m in (history or []) if m.get("role") == "user")]
        foto._aloja_en_baru = any(_solo_baru(t) for t in dicho)
    reparto = datos.get("group_allocation")
    if isinstance(reparto, dict) and not foto.detected_group_allocation:
        # arq-5f: «dos bucean y dos hacen snorkel» en ESTE mensaje (la extracción aún no lo ha guardado): la misma lancha.
        foto.detected_group_allocation = {k: v for k, v in reparto.items() if isinstance(v, int) and v > 0}
    return foto


def _cubierta(bloque: dict, intencion: str) -> bool:
    """¿Los hechos traen algo para esta intención? Si no (una edad que el registro no tiene, un plan sin horario),
    contesta el RAG."""
    valor = bloque.get(intencion)
    if intencion == "horario" and not valor:
        valor = bloque.get("horario_general")
    if isinstance(valor, dict):
        return any(v for v in valor.values())
    return bool(valor)


def _mensajes(lang: str, history: list[dict], message: str, texto_hechos: str) -> list[dict]:
    from src.agents.rag_agent import _build_tone_section  # lazy
    from src.prompts.info import (  # lazy
        RAG_INTRO_EN,
        RAG_INTRO_ES,
        RAG_SECURITY_EN,
        RAG_SECURITY_ES,
        REDACTOR_HECHOS_EN,
        REDACTOR_HECHOS_ES,
    )

    if lang == "es":
        system = (f"{RAG_INTRO_ES}\n\n{RAG_SECURITY_ES}\nEstilo y tono:\n{_build_tone_section('es')}\n\n"
                  f"{REDACTOR_HECHOS_ES}")
        user = f"Hechos:\n{texto_hechos}\n\nPregunta del cliente: {redact_pii(message)}"
    else:
        system = (f"{RAG_INTRO_EN}\n\n{RAG_SECURITY_EN}\nStyle and tone:\n{_build_tone_section('en')}\n\n"
                  f"{REDACTOR_HECHOS_EN}")
        user = f"Facts:\n{texto_hechos}\n\nCustomer's question: {redact_pii(message)}"
    from src.prompts.info import (  # lazy
        REDACTOR_CLIMA_PAGO_EN,
        REDACTOR_CLIMA_PAGO_ES,
        REDACTOR_EN_QUE_CONSISTE_EN,
        REDACTOR_EN_QUE_CONSISTE_ES,
        REDACTOR_FRASES_POR_CODIGO_EN,
        REDACTOR_FRASES_POR_CODIGO_ES,
        REDACTOR_LISTAS_POR_CODIGO_EN,
        REDACTOR_LISTAS_POR_CODIGO_ES,
        REDACTOR_QUE_FALTABAN_EN,
        REDACTOR_QUE_FALTABAN_ES,
        REDACTOR_SIN_PREGUNTAS_EN,
        REDACTOR_SIN_PREGUNTAS_ES,
        reglas_del_escritor,
    )

    system += REDACTOR_LISTAS_POR_CODIGO_ES if lang == "es" else REDACTOR_LISTAS_POR_CODIGO_EN
    system += REDACTOR_FRASES_POR_CODIGO_ES if lang == "es" else REDACTOR_FRASES_POR_CODIGO_EN
    system += REDACTOR_EN_QUE_CONSISTE_ES if lang == "es" else REDACTOR_EN_QUE_CONSISTE_EN  # arq-8d
    system += REDACTOR_SIN_PREGUNTAS_ES if lang == "es" else REDACTOR_SIN_PREGUNTAS_EN
    system += REDACTOR_QUE_FALTABAN_ES if lang == "es" else REDACTOR_QUE_FALTABAN_EN  # arq-5f
    system += REDACTOR_CLIMA_PAGO_ES if lang == "es" else REDACTOR_CLIMA_PAGO_EN  # arq-1i
    # lat-9 paso 1 (26-oct): las reglas de cualquier escritor (las mismas que el RAG) y las decisiones del negocio. Antes
    # el redactor no tenía las de no adivinar, el género o abrir con la respuesta, y la moneda iba escrita aparte.
    system += "\n\n" + reglas_del_escritor(lang)
    previos = list(history or [])
    if previos and previos[-1].get("role") == "user" and previos[-1].get("content") == message:
        previos = previos[:-1]  # el mensaje va abajo, con los hechos
    return [{"role": "system", "content": system},
            *({"role": m["role"], "content": redact_pii(m.get("content") or "")} for m in previos[-_HISTORIAL:]),
            {"role": "user", "content": user}]


async def _redactar(client, mensajes: list[dict]) -> str | None:
    from src.agents.rag_agent import generar_con_respaldo  # lazy

    try:
        respuesta = await generar_con_respaldo(client, mensajes, pieza="redactor_hechos")
    except Exception as exc:  # noqa: BLE001 — sin redacción, contesta el RAG
        logger.warning(f"[HECHOS] el redactor falló: {exc!r}")
        return None
    return (respuesta.choices[0].message.content or "").strip()


_EN_SU_IDIOMA = {"es": "Escríbela de nuevo entera en español.", "en": "Write it again in full in English."}

# arq-7a (23-oct, latencia): en el G10 nº 5 el redactor escribía dos veces en 53 de 79 turnos:
# el primer borrador resumía las listas largas y arq-3 pedía rehacerlo (+2,5 s). Esas listas las pone ahora el código,
# copiadas del dato, donde el modelo deja su marca («[[incluye]]»); el modelo escribe solo las frases.
_LISTAS_DEL_CODIGO = ("incluye", "requisitos", "descuento")
_ROTULO_DEL_ORIGEN = {"es": {"cartagena": "Desde Cartagena", "island": "Si ya estás en las Islas del Rosario"},
                      "en": {"cartagena": "From Cartagena", "island": "If you're already on the Rosario Islands"}}


def _listas_del_codigo() -> tuple[str, ...]:
    """arq-8d: también lo que se hace en la actividad (va con «incluye»)."""
    return (*_LISTAS_DEL_CODIGO, "en_que_consiste")


def _en_vinetas(valor, lang: str) -> str:
    """Una lista del dato en viñetas «•»; si viene por origen y hay dos, cada una con su rótulo en negrita."""
    if isinstance(valor, dict):
        partes = [(o, items) for o, items in valor.items() if items]
        return "\n\n".join((f"*{_ROTULO_DEL_ORIGEN[lang].get(o, o)}:*\n" if len(partes) > 1 else "")
                           + "\n".join(f"• {x}" for x in items) for o, items in partes)
    return "\n".join(f"• {x}" for x in valor or [])


def _poner_listas(answer: str, bloques: list[dict], intenciones: list[str], lang: str) -> str:
    """Cambia cada marca «[[campo]]» por la lista entera del dato. Si el modelo no dejó la marca y tampoco escribió la
    lista (arq-3 ve que faltan sus puntos), la lista va al final; si la escribió él, se queda la suya."""
    for campo in _listas_del_codigo():
        if (campo if campo != "en_que_consiste" else "incluye") not in intenciones:
            continue
        piezas = [(b, _en_vinetas(b.get(campo), lang)) for b in bloques]
        piezas = [(b, t) for b, t in piezas if t]
        if not piezas:
            continue
        texto = _una_vez(piezas)
        marca = f"[[{campo}]]"
        if marca in answer:
            answer = answer.replace(marca, texto, 1).replace(marca, "")
        elif hechos_mod.faltan(answer, [{campo: b.get(campo)} for b, _ in piezas],
                               ["incluye" if campo == "en_que_consiste" else campo]):
            answer = f"{answer.rstrip()}\n\n{texto}"
    answer = _poner_frases(answer, bloques, lang)
    answer = _sin_rotulos_sueltos(answer, lang)
    return _sin_marcas(answer)


def _una_vez(piezas: list[tuple[dict, str]]) -> str:
    """arq-8f: la lista que sale igual en varias actividades va una vez, con el nombre de todas ellas; si es igual en
    todas, sin nombre (G10 nº 6: los descuentos ×5 en las cinco especialidades)."""
    grupos: dict[str, list[str]] = {}
    for b, t in piezas:
        grupos.setdefault(t, []).append(b.get("nombre") or "")
    if len(grupos) == 1:
        return next(iter(grupos))
    return "\n\n".join((f"*{', '.join(n for n in nombres if n)}*\n" if any(nombres) else "") + t
                       for t, nombres in grupos.items())


def _rotulo_solo(linea: str, lang: str) -> bool:
    """¿La línea es solo un rótulo de origen («*Desde Cartagena*», «*From Cartagena:*»), sin nada detrás?"""
    limpia = linea.strip().strip("*").strip().rstrip(":").strip("*").strip()
    return limpia.lower() in {r.lower() for r in _ROTULO_DEL_ORIGEN[lang].values()}


def _sin_rotulos_sueltos(answer: str, lang: str) -> str:
    """arq-8f (#1631; arq-7e, 2 de 98 respuestas): el modelo escribe su rótulo de origen justo antes de la marca y el
    código pone el suyo (rótulo doble), o queda un rótulo sin nada debajo. Fuera el rótulo solo en su línea si lo que
    sigue es otro rótulo, una línea en blanco o el final."""
    lineas = answer.split("\n")
    fuera = set()
    for i, linea in enumerate(lineas):
        if not _rotulo_solo(linea, lang):
            continue
        siguiente = lineas[i + 1] if i + 1 < len(lineas) else ""
        if not siguiente.strip() or _empieza_por_rotulo(siguiente, lang):
            fuera.add(i)
    if not fuera:
        return answer
    return re.sub(r"\n{3,}", "\n\n", "\n".join(x for i, x in enumerate(lineas) if i not in fuera)).strip()


def _empieza_por_rotulo(linea: str, lang: str) -> bool:
    cabeza = linea.strip().lstrip("*").lower()
    return any(cabeza.startswith(r.lower()) for r in _ROTULO_DEL_ORIGEN[lang].values())


# G10 nº 6: con el enlace, los hechos traen `descuento_online` y no la lista `descuento` (no se preguntó por descuentos);
# el modelo dejó igual «[[descuento]]» y la marca le llegó al cliente en 2 respuestas. Lo que el código no rellena, se quita.
_MARCA = re.compile(r"[ \t]*\[\[[a-z_]+\]\][ \t]*")


def _sin_marcas(answer: str) -> str:
    if "[[" not in answer:
        return answer
    return re.sub(r"\n{3,}", "\n\n", _MARCA.sub("", answer)).strip()


# arq-7d (23-oct, latencia): tras arq-7a, en el banco fijo quedaban 28 de 96 turnos con
# segunda redacción, casi todos por las frases de la recogida y del alojamiento (políticas que el modelo parafraseaba
# y arq-3 no reconocía). También las pone el código, tal cual, donde el modelo deja «[[recogida]]» o «[[alojamiento]]».
_FRASES_DEL_CODIGO = ("recogida", "alojamiento")


def _poner_frases(answer: str, bloques: list[dict], lang: str) -> str:
    for campo in _FRASES_DEL_CODIGO:
        valores = [b.get(campo) for b in bloques if b.get(campo)]
        if not valores:
            continue
        if campo == "alojamiento":
            texto = "\n\n".join(dict.fromkeys(valores))
        else:
            partes = [(o, frases) for v in valores for o, frases in v.items() if frases]
            partes = list(dict.fromkeys((o, tuple(f)) for o, f in partes))  # arq-8f: el punto de encuentro, una vez
            texto = "\n\n".join((f"*{_ROTULO_DEL_ORIGEN[lang].get(o, o)}:* " if len(partes) > 1 else "")
                                + " ".join(frases) for o, frases in partes)
        marca = f"[[{campo}]]"
        if marca in answer:
            answer = answer.replace(marca, texto, 1).replace(marca, "")
        elif hechos_mod.faltan(answer, [{campo: v} for v in valores], []):
            answer = f"{answer.rstrip()}\n\n{texto}"
    return answer
def _en_otro_idioma(answer: str, lang: str) -> bool:
    """arq-5d: ¿la redacción salió en otro idioma que el de la conversación? Las mismas palabras vacías con las que el
    flujo detecta el idioma del cliente, con margen claro (el doble y al menos 4): los nombres propios en español de
    una respuesta en inglés («Muelle de la Bodeguita», «Islas del Rosario») no bastan para tomarla por otro idioma."""
    from src.flows.catalog import _ENGLISH_STOPWORDS, _SPANISH_STOPWORDS  # lazy

    palabras = [p.strip(".,!?¡¿:;()[]{}\"'*•") for p in answer.lower().split()]
    es, en = sum(p in _SPANISH_STOPWORDS for p in palabras), sum(p in _ENGLISH_STOPWORDS for p in palabras)
    propio, ajeno = (es, en) if lang == "es" else (en, es)
    return ajeno >= 4 and ajeno >= 2 * propio


def _pasa_las_guardas(answer: str, texto_hechos: str, message: str) -> bool:
    """Las guardas deterministas de siempre: ni importes, ni enlaces, ni teléfonos que no estén en los hechos."""
    return (is_coherent_text(answer) and currency_amounts_grounded(answer, f"{texto_hechos}\n{message}")
            and urls_grounded(answer, texto_hechos) and not contains_phone_number(answer))


async def hechos_del_turno(state: ConversationState, message: str, history: list[dict]) -> tuple[list[dict], list[str]] | None:
    """Los hechos de las intenciones de este mensaje que el código sabe dar (bloques, intenciones cubiertas), o None si
    no hay: Jev no da intenciones, la pregunta no es la del mensaje de ahora o no se sabe la actividad. No mira si el
    mensaje trae algo más: eso lo decide quien llama (el redactor, o el RAG en los mensajes mezclados, arq-1g)."""
    from src.observability import note_turn  # lazy

    intenciones = list(getattr(state, "_intenciones", None) or [])
    if not intenciones:
        note_turn(hechos_por_codigo="sin_intenciones")
        return None
    ultimo = next((h.get("content") for h in reversed(history or []) if h.get("role") == "user"), None)
    if ultimo != message:
        # La pregunta guardada que se contesta en un turno posterior (el precio tras decir el origen): las intenciones
        # de Jev son las del mensaje de ahora, no las suyas.
        note_turn(hechos_por_codigo="pregunta_guardada")
        return None
    from src.agents.nucleo.extractor import lectura_del_extractor  # lazy

    leida = await lectura_del_extractor(state, message)
    datos, leido = leida or {}, leida is not None
    actividades = _actividades(state, datos)
    if not actividades:
        if set(intenciones) <= hechos_mod.INTENCIONES_SIN_ACTIVIDAD:
            # arq-1p: la hora, la recogida, qué llevar o si hay sitio son iguales para todas las actividades.
            foto = _foto(state, datos, _origen(state, datos, leido), message, history)
            if foto.is_certified is None and datos.get("is_certified") is not None:
                foto.is_certified = datos["is_certified"]  # arq-1s: el certificado lleva el carné en los requisitos
            bloques = hechos_mod.hechos_sin_actividad(foto, intenciones)
            cubiertas = [i for i in intenciones if any(_cubierta(b, i) for b in bloques)]
            return (bloques, cubiertas) if cubiertas else None
        note_turn(hechos_por_codigo="sin_actividad" if datos else "sin_lectura")
        return None
    bloques = hechos_mod.hechos(_foto(state, datos, _origen(state, datos, leido), message, history), intenciones,
                                actividades)
    cubiertas = [i for i in intenciones if any(_cubierta(b, i) for b in bloques)]
    if not cubiertas:
        note_turn(hechos_por_codigo="sin_cubrir")
    return (bloques, cubiertas) if cubiertas else None


def texto_de_los_hechos(bloques: list[dict]) -> str:
    """Los hechos en JSON para el modelo. `pregunta_pendiente` es del código (la pregunta la pone él): con ella delante,
    Luna preguntaba el origen en vez de dar los dos enlaces (banco arq-1d, k2 2 de 3)."""
    return json.dumps([{k: v for k, v in b.items() if k != "pregunta_pendiente"} for b in bloques],
                      ensure_ascii=False, indent=1)


async def responder(state: ConversationState, message: str, history: list[dict]) -> str | None:
    """La respuesta escrita con los hechos del código, o None si este mensaje no es para el redactor (y contesta el
    RAG): Jev no da intenciones o no está seguro de que no traiga otra cosa, no se sabe la actividad, los hechos no
    cubren alguna intención, o la redacción no pasa las guardas deterministas (importes, enlaces, teléfonos).
    Cada salida apunta en [TURN_METRICS] (`hechos`) quién contestó o por qué no el redactor: en el G10 nº 3 contestó en
    37 turnos frente a 72 en el nº 2, con el mismo código, y las métricas no decían por qué."""
    from src.observability import note_turn  # lazy

    otra_cosa = getattr(state, "_otra_cosa", None)
    if otra_cosa is not False:
        note_turn(hechos_por_codigo="jev_calla" if otra_cosa is None else "otra_cosa")
        return None
    turno = await hechos_del_turno(state, message, history)
    if turno is None:
        return None
    bloques, cubiertas = turno
    intenciones = list(getattr(state, "_intenciones", None) or [])
    actividad = bloques[0]["actividad"]
    if cubiertas != intenciones:
        logger.info(f"[HECHOS] {actividad}: los hechos no cubren {intenciones}; contesta el RAG")
        note_turn(hechos_por_codigo="no_cubre")
        return None
    return await _escribir(state, message, history, bloques, intenciones)


async def _escribir(state: ConversationState, message: str, history: list[dict], bloques: list[dict],
                    intenciones: list[str]) -> str | None:
    """La redacción con los hechos: guardas, idioma, comprobación de que no falta ninguno (arq-3) y, si hace falta, la
    pregunta del origen."""
    from src.observability import note_turn  # lazy

    actividad = bloques[0]["actividad"]
    origen = bloques[0].get("origen")
    lang = "es" if state.language == "es" else "en"
    texto_hechos = texto_de_los_hechos(bloques)
    client = trace_openai(AsyncOpenAI(api_key=settings.openai_api_key))
    mensajes = _mensajes(lang, history, message, texto_hechos)
    answer = await _redactar(client, mensajes)
    if answer is not None and _en_otro_idioma(answer, lang):
        # arq-5d (G10 nº 5, g10-020): a quien escribía en portugués el redactor le contestó en portugués, aunque la
        # conversación es en inglés (decisión de Gadea). Se rehace una vez diciéndolo; si sigue igual, contesta el RAG.
        logger.info(f"[HECHOS] la redacción no está en {lang}: se rehace")
        answer = await _redactar(client, [*mensajes, {"role": "assistant", "content": answer},
                                          {"role": "user", "content": _EN_SU_IDIOMA[lang]}])
        if answer is not None and _en_otro_idioma(answer, lang):
            answer = None
    if answer is None:
        note_turn(hechos_por_codigo="fallo")
        return None
    if _FALTA in answer:
        # Pregunta algo que los hechos no traen (Jev no marcó esa intención: «what time do we meet» a 0,72 en un mensaje
        # de tres preguntas, banco arq-1d v3). Mejor el RAG, con toda la base, que un «no tengo ese dato». Se mira en
        # todo el texto, en mayúsculas: la escribió en medio (banco D, v2) y al final de una frase (core B2: «I don't
        # have the price for the refresher. FALTA»), y las dos veces le habría llegado al cliente.
        logger.info(f"[HECHOS] el redactor dice que falta algo ({intenciones}); contesta el RAG")
        note_turn(hechos_por_codigo="falta")
        state._redactor_dijo_falta = True  # arq-1g: el mensaje era mezclado; el RAG recibe los hechos
        return None
    answer = _poner_listas(answer, bloques, intenciones, lang)
    if not _pasa_las_guardas(answer, texto_hechos, message):
        logger.info("[HECHOS] la redacción no pasa las guardas deterministas; contesta el RAG")
        note_turn(hechos_por_codigo="guardas")
        return None
    perdidos = hechos_mod.faltan(answer, bloques, intenciones)
    if perdidos:
        # lat-2 (24-oct, fase LAT): ya no se rehace la respuesta cuando le falta un hecho (ARQ-3 la rehacía en el 38 % de
        # los turnos del redactor de real-1, ~2,5 s más). Las listas y las frases ya las pone el código; lo demás que
        # falte se apunta en [TURN_METRICS] y es deuda de calidad de la fase.
        logger.info(f"[HECHOS][ARQ3] faltan {len(perdidos)} (no se rehace): {[p[:60] for p in perdidos]}")
        note_turn(hechos_faltaban=len(perdidos), hechos_quedan=len(perdidos))
    if any(b.get("pregunta_pendiente") == "origen" for b in bloques):
        # La pregunta del origen la pone el código, con el texto que reconoce el flujo (`_es_pregunta_de_origen`): así
        # queda pendiente el origen y, cuando lo diga, se le contesta el plan exacto, como en ord-7.
        from src.agents import conversational_core as core  # lazy

        tras = ((core.ORIGEN_TRAS_LOS_ENLACES_ES, core.ORIGEN_TRAS_LOS_ENLACES_EN) if "enlace" in intenciones
                else (core.ORIGEN_TRAS_LAS_VARIANTES_ES, core.ORIGEN_TRAS_LAS_VARIANTES_EN))
        answer = f"{answer}\n\n{tras[0] if lang == 'es' else tras[1]}"
    logger.info(f"[HECHOS] contesta el redactor: {actividad} {intenciones} origen={origen}")
    # arq-1p: «redactor_general» cuando contestó con el bloque sin actividad (se ve en [TURN_METRICS] `hechos`).
    general = all(b.get("actividad") is None for b in bloques)
    note_turn(rag_used=True, hechos_por_codigo="redactor_general" if general else "redactor",
              intenciones=",".join(intenciones))
    return answer
