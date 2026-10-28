"""ARQ-1d (22-oct, fase ARQ: el modelo interpreta, el código decide, el modelo redacta): los HECHOS del turno.

Diseño: `docs/robustness/arq/diseno-intenciones-y-hechos.md` §3. Si Jev dice que el mensaje pide intenciones de la
tabla (precio, qué incluye, requisitos, horario, disponibilidad, edad, enlace) y se sabe de qué actividad habla, el
código saca los hechos (`src/flows/hechos.py`). lat-9 paso 3 (26-oct): los escribe el escritor único (el del RAG), con
los hechos y sin búsqueda si el mensaje solo pide eso (`responder`), o con la búsqueda si trae algo más (arq-1g). El
redactor con su propio prompt y su «FALTA» ya no existe.
"""
from __future__ import annotations

import copy
import json
import logging
import re

from src.domain import activities as dom
from src.flows import cotizar
from src.flows import hechos as hechos_mod
from src.flows.state import ConversationState
from src.utils.text import strip_accents

logger = logging.getLogger("uvicorn.error")

_LUGAR_DE_JEV = {"cartagena": "cartagena", "islands": "island"}


def _actividad(state: ConversationState, datos: dict) -> str | None:
    """La actividad de la que pregunta ESTE mensaje (extractor) o, si no nombra ninguna, la de la conversación SI es
    una sola. arq-1k (G10 nº 2): hablaban de snorkel para los niños y de buceo para el padre, «¿qué incluye?» y el
    redactor contestaba lo del buceo; con varias en juego no se adivina: contesta el RAG, que ve la conversación."""
    repaso = any(x is True for x in (datos.get("refresher_interested"), datos.get("last_dive_over_2_years"),
                                     state.refresher_interested, state.last_dive_over_2_years))
    for clave in ("actividad_preguntada", "activity"):
        actividad = datos.get(clave)
        if actividad and dom.by_id(actividad) is not None:
            # CALN-7 (28-oct): «¿hay que completar algo antes? Necesitaré un refresher» es el buzo que hace el refresher
            # (arq-1n); el extractor da el buceo certificado de la conversación y los requisitos salían sin el formulario
            # médico. Si el cliente PREGUNTA por el buceo certificado, se le contesta de eso (arq-1n).
            return "refresher" if repaso and clave == "activity" and actividad == "certified_diving" else actividad
    elegida = dom.activity_for_service(state.selected_service) if state.selected_service else None
    reparto = state.detected_group_allocation or {}
    en_juego = {a for a in (state.actividad_preguntada, state.detected_activity, elegida.id if elegida else None,
                            *(a for a, n in reparto.items() if n)) if a and dom.by_id(a) is not None}
    if repaso and en_juego <= {"certified_diving", "minicourse", "refresher"}:
        # arq-1n (G10 nº 2): el certificado con más de 2 años sin bucear hace primero el refresher (se reserva como el
        # minicurso); sin esto, «¿qué incluye?» desde Ubuntu salía con el almuerzo del buceo desde Cartagena.
        return "refresher"
    if len(en_juego) == 1:
        return en_juego.pop()
    if not en_juego and state.suggested_activity and dom.by_id(state.suggested_activity) is not None:
        return state.suggested_activity  # la que acaba de proponer el bot («¿y qué incluye?»)
    return None


def _actividades_en_juego(state: ConversationState) -> bool:
    """¿Hay alguna actividad en la conversación? Con varias, `_actividad` no adivina (arq-1k) y contesta el RAG; los
    candidatos de CALN-3 son solo para cuando no hay ninguna."""
    return bool(state.selected_service or state.actividad_preguntada or state.detected_activity
                or any(n for n in (state.detected_group_allocation or {}).values()))


def _actividades(state: ConversationState, datos: dict) -> list[str]:
    """La actividad del mensaje (y, si es genérica, las concretas de su familia)."""
    una = _actividad(state, datos)
    registro = dom.by_id(una) if una else None
    if registro is not None and registro.generic:
        # arq-1n (G10 nº 2): «¿cuánto cuestan las especialidades?» no tenía hechos (lo genérico no tiene planes) y el
        # RAG las nombraba sin precio. Se abre en las actividades concretas de su familia, con plan.
        return [a.id for a in dom.registry().activities if a.family == registro.family and not a.generic
                and (dom.service_ids(a.id, "cartagena") or dom.service_ids(a.id, "island"))]
    if not una:
        return []
    # CALN (27-oct, sparring CALN1-04): en un grupo ya repartido, también las del resto del grupo. «Mi marido bucea, yo y
    # la de 14 el minicurso, la pequeña Bubble Makers: ¿cuánto todo?» llevaba solo los de Bubble Makers y el escritor
    # contestaba «no tengo aquí los precios de las otras actividades». El reparto de ESTE mensaje lo trae la lectura del
    # extractor: el del estado se guarda después de contestar.
    repartos = (state.detected_group_allocation or {}, datos.get("group_allocation") or {})
    del_grupo = list(dict.fromkeys(a for reparto in repartos for a, n in reparto.items()
                                   if n and a != una and dom.by_id(a) is not None and not dom.by_id(a).generic))
    return [una, *del_grupo]


def _origen(state: ConversationState, datos: dict, leido: bool = False) -> str | None:
    """`leido`: el extractor leyó el mensaje (aunque no traiga nada). DEUDA-ORIGEN (26-oct): entonces el lugar de Jev
    no fija el origen ("Estaremos visitando Cartagena…" no dice la salida): van los dos precios y se pregunta."""
    from src.agents.jev_router import CUSTOMER_PLACE_MIN  # lazy

    lugar = getattr(state, "_jev_lugar", None) or {}  # gen-15: «nos alojamos en Mulata» lo dice Jev, no una palabra
    del_mensaje = datos.get("location")
    if (del_mensaje in hechos_mod.ORIGENES and _LUGAR_DE_JEV.get(lugar.get("choice")) == del_mensaje
            and (lugar.get("confidence") or 0.0) >= CUSTOMER_PLACE_MIN):
        # CALN-3 (27-oct, CALN1-03 / CALN2 de Gadea #2136): «al final vamos a estar en Isla Grande, ¿cambia el precio?»
        # se cotizaba desde Cartagena, lo guardado ANTES del turno. Si los dos lectores de ESTE mensaje dicen el mismo
        # origen (extractor y Jev seguro), manda ese. Con uno solo no («snorkel en las islas»: Jev dice none, CAL-C3c).
        return del_mensaje
    for guardado in (state.location, state.detected_location, del_mensaje):
        if guardado in hechos_mod.ORIGENES:
            return guardado
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
    if isinstance(datos.get("group_size"), int) and datos["group_size"] > (foto.detected_group_size or 0):
        foto.detected_group_size = datos["group_size"]  # CALN-3: «somos 5» en ESTE mensaje, para el descuento de grupo
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
    if (not actividades and "precio" in intenciones and not _actividades_en_juego(state)
            and not (state.ya_reservado or datos.get("ya_reservado"))):
        # CALN-3 paso 2 (CALN3-P01): el precio sin actividad elegida, con los candidatos que deja lo que se sabe. Quien
        # ya reservó algo que no nombra no elige entre candidatos: contesta el RAG (arq-1p).
        foto = _foto(state, datos, _origen(state, datos, leido), message, history)
        for campo in ("is_certified", "quiere_bucear"):
            if getattr(foto, campo) in (None, False) and datos.get(campo) is not None:
                setattr(foto, campo, datos[campo])
        if bloques := cotizar.hechos_de_los_candidatos(foto, intenciones):
            cubiertas = [i for i in intenciones if any(_cubierta(b, i) for b in bloques)]
            logger.info(f"[HECHOS][CALN3] sin actividad elegida: los candidatos {[b['actividad'] for b in bloques]}")
            return (bloques, cubiertas) if cubiertas else None
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
    return await _con_el_escritor(state, message, history, bloques, intenciones)


async def _con_el_escritor(state: ConversationState, message: str, history: list[dict], bloques: list[dict],
                           intenciones: list[str]) -> str | None:
    """lat-9 paso 3 (26-oct): un solo escritor. Lo que pide el mensaje lo cubren entero los hechos del código: lo escribe
    el mismo escritor que el RAG (su prompt, las reglas del negocio, el catálogo y las políticas), con los hechos y sin
    reescritura ni búsqueda; las listas que se le escapen las añade el código (arq-7b), y el revisor va con la regla de
    lat-5. Antes era otra llamada con otro prompt (el redactor), que si no sabía decía FALTA y pagaba además el RAG."""
    from src.agents import conversational_core as core  # lazy
    from src.agents import supervisor  # lazy
    from src.agents.rag_agent import is_fallback_answer  # lazy
    from src.observability import note_turn  # lazy

    lang = "es" if state.language == "es" else "en"
    origen_pendiente = any(b.get("pregunta_pendiente") == "origen" for b in bloques)
    entradas = core._entradas_rag(state, history, message)
    if origen_pendiente:
        entradas.pop("pregunta_final", None)  # la pregunta del origen la pone el código, abajo
    entradas.update(hechos=texto_de_los_hechos(bloques), hechos_bloques=(bloques, intenciones), sin_busqueda=True)
    answer = await supervisor.rag_answer(message, **entradas)
    if not answer or is_fallback_answer(answer):
        note_turn(hechos_por_codigo="fallo")
        return None
    if origen_pendiente:
        tras = ((core.ORIGEN_TRAS_LOS_ENLACES_ES, core.ORIGEN_TRAS_LOS_ENLACES_EN) if "enlace" in intenciones
                else (core.ORIGEN_TRAS_LAS_VARIANTES_ES, core.ORIGEN_TRAS_LAS_VARIANTES_EN))
        answer = f"{core._sin_la_pregunta_final(answer).rstrip()}\n\n{tras[0] if lang == 'es' else tras[1]}"
    general = all(b.get("actividad") is None for b in bloques)
    logger.info(f"[HECHOS] contesta el escritor con los hechos: {bloques[0]['actividad']} {intenciones}")
    note_turn(rag_used=True, hechos_por_codigo="redactor_general" if general else "redactor",
              intenciones=",".join(intenciones))
    return answer
