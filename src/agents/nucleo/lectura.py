"""CALN-8 (5) paso 1 (4-nov, #3300): lo que dice ESTE mensaje, en un sitio.

Quien contesta lo hace antes de que la extracción guarde lo que trae el mensaje, así que trabaja con una copia del
estado con lo que el mensaje dice (`foto_del_turno`): el origen (`origen_del_mensaje`), la nacionalidad y el grupo
mezclado, la duración, el paquete y el plan nombrados, el nocturno, el tamaño del grupo y el reparto. Vivía en
`redactor_hechos` (`_foto`), y gen-14 hace otra copia solo con la nacionalidad: el venezolano con cédula y esposa
colombiana necesitó tres arreglos (9e464ce5, aa6a45ed, 79a2bf1c), uno por copia. Las reglas de cada dato son las de la
extracción (`con_la_cedula`, `mezclado_del_mensaje`, `duracion_del_extractor`, `paquete_nocturno_pedido`); el estado de
verdad lo sigue escribiendo ella (`nucleo/extractor._poner_*`).
"""
from __future__ import annotations

import copy
import re

from src.domain import activities as dom
from src.flows import hechos as hechos_mod
from src.flows.state import ConversationState
from src.utils.text import strip_accents

_LUGAR_DE_JEV = {"cartagena": "cartagena", "islands": "island"}


def origen_del_mensaje(state: ConversationState, datos: dict, leido: bool = False) -> str | None:
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
    from src.agents.conversational_core import _jev_duda_del_lugar  # lazy

    # CALN-9: lo que el extractor lee en este mensaje y Jev no respalda no fija el precio (una hipótesis).
    for guardado in (state.location, state.detected_location, None if _jev_duda_del_lugar(state, datos) else del_mensaje):
        if guardado in hechos_mod.ORIGENES:
            return guardado
    if not leido and (lugar.get("confidence") or 0.0) >= CUSTOMER_PLACE_MIN:
        return _LUGAR_DE_JEV.get(lugar.get("choice"))
    if datos.get("hotel"):
        # arq-8b: «We'll be staying at the Ubuntu hotel… how much…?» con Jev a 0,52 en el lugar: el extractor lee el hotel
        # y CAL-C3e lo sabe de las islas, pero el origen lo pone al guardar, después de contestar; el redactor daba las
        # dos variantes y preguntaba desde dónde sale (banco arq-8b variantes, v5 3/3).
        if hotel_de_las_islas(str(datos["hotel"])):
            return "island"
    return None


_GENERICAS_DE_HOTEL = {"hotel", "eco", "the", "el"}


def _sin_genericas(nombre: str) -> str:
    plano = strip_accents((nombre or "").lower())
    return " ".join(p for p in re.findall(r"[a-z0-9]+", plano) if p not in _GENERICAS_DE_HOTEL)


def hotel_de_las_islas(nombre: str) -> bool:
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


def foto_del_turno(state: ConversationState, datos: dict, origen: str | None, message: str = "",
          history: list[dict] | None = None) -> ConversationState:
    """Una copia del estado con lo que dice ESTE mensaje (origen y nacionalidad): la extracción aún no lo ha guardado
    cuando se contesta (como gen-14 en el RAG). El estado de verdad lo sigue escribiendo la extracción."""
    from src.agents.nucleo.extractor import con_la_cedula, mezclado_del_mensaje  # lazy

    foto = copy.copy(state)
    foto.location = origen
    # La nacionalidad y el grupo mezclado como los guarda la extracción (la cédula y el mixto de Jev): con los del extractor a
    # secas, el venezolano con cédula y esposa colombiana quedaba residente en el estado, pero los hechos y su pieza salían
    # en USD (banco-graves g-venezolano-cedula, 0/3).
    if foto.is_colombian is None and (nacional := con_la_cedula(state, datos.get("is_colombian"))) is not None:
        foto.is_colombian = nacional
    if mezclado_del_mensaje(state, datos):
        foto.mixed_nationality_notice = True
    if datos.get("paquete_varios_dias") is True:
        foto.detected_duration = "multi_day"  # arq-1t: «el paquete de varios días» en ESTE mensaje
    # Sparring s04b (conv 6844): «un plan de 2 días» en ESTE mensaje no llegaba a los hechos, que daban los planes de un día
    # (2, 3 y 4 inmersiones) y no el de 5; en el turno siguiente, ya guardado, sí. Lo que dice la extracción (`_poner_duracion`).
    from src.agents.nucleo.extractor import duracion_del_extractor  # lazy

    duracion, de_buceo = duracion_del_extractor(datos, foto)
    if duracion is not None:
        foto.detected_duration = duracion
        foto.duracion_de_buceo = foto.duracion_de_buceo or de_buceo
    if origen == "cartagena":
        # arq-5f: el extractor deja Barú como Cartagena (gen-6) sin otra marca; los hechos dicen por qué sale de allí.
        from src.agents.extractor_turno import _solo_baru  # lazy

        dicho = [message, *(m.get("content") or "" for m in (history or []) if m.get("role") == "user")]
        foto._aloja_en_baru = any(_solo_baru(t) for t in dicho)
    if isinstance(datos.get("group_size"), int) and datos["group_size"] > (foto.detected_group_size or 0):
        foto.detected_group_size = datos["group_size"]  # CALN-3: «somos 5» en ESTE mensaje, para el descuento de grupo
    if not foto.selected_service and (plan := _paquete_nombrado(message, None) or _paquete_nocturno(foto, datos, message)
                                      or _paquete_nombrado(message, history)):
        # CALN-3 paso 3 «A» (p11, p12): «¿cuánto cuesta el paquete de 5 inmersiones?» no dejaba el plan en el estado y los
        # hechos daban la salida de 2; con el catálogo delante el escritor lo arreglaba, con la pieza ya no.
        foto.detected_service_id = plan
    reparto = datos.get("group_allocation")
    if isinstance(reparto, dict) and not foto.detected_group_allocation:
        # arq-5f: «dos bucean y dos hacen snorkel» en ESTE mensaje (la extracción aún no lo ha guardado): la misma lancha.
        foto.detected_group_allocation = {k: v for k, v in reparto.items() if isinstance(v, int) and v > 0}
    return foto


def _paquete_nocturno(foto: ConversationState, datos: dict, message: str) -> str | None:
    """CALN-20: pide el nocturno en ESTE mensaje sin cifra → el paquete que lo lleva, como en la extracción."""
    from src.agents.nucleo.extractor import paquete_nocturno_pedido  # lazy

    dives = paquete_nocturno_pedido(foto, datos, message)
    return dom.dive_packages()[dives][1] if dives else None


def _paquete_nombrado(message: str, history: list[dict] | None) -> str | None:
    """El plan de buceo que nombra el cliente por sus inmersiones («el paquete de 5 inmersiones», «the 2-dive trip»), en
    este mensaje o, si no nombra ninguno, en el último suyo que lo haga; None si nombra varios o ninguno. La lectura es
    la de siempre (`dive_counts_in`: cifra y unidad del catálogo)."""
    from src.agents.intent_detector import dive_counts_in  # lazy

    suyos = [message, *(m.get("content") or "" for m in reversed(history or []) if m.get("role") == "user")]
    for texto in suyos:
        cuentas = dive_counts_in(texto)
        if cuentas:
            return dom.dive_packages()[cuentas[0]][1] if len(cuentas) == 1 else None
    return None
