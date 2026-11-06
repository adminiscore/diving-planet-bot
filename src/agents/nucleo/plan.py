"""El plan (CALN-8 (5), 5-nov): cuántos días dura el plan elegido, si está en duda, si hace falta dormir en las islas o
es de un día, la presentación del plan que se recomienda y el plan del buzo certificado; y la pregunta del origen,
que cambia si el plan es de ida y vuelta el mismo día.

Movido tal cual desde `conversational_core.py`, que lo re-exporta. Ver `src/agents/nucleo/__init__.py`.
"""

from __future__ import annotations

from src.domain import activities as dom
from src.flows import cart_render
from src.flows.plan_de_buceo import paquetes_de, plan_del_estado, servicio_del_plan
from src.flows.state import ConversationState


def _dias_del_plan(state: ConversationState) -> int | None:
    """Cuántos días dura el plan elegido, de la ficha (`duration_days` de services.json): el servicio ya
    resuelto, o la actividad si todos sus servicios duran lo mismo (Open Water y su referido: 2). None si
    no se sabe (sin plan, o un paquete sin concretar, que va de 2 a 4 días)."""
    from src.flows.catalog import RAW_SERVICES  # lazy

    def _dias(sid: str) -> int | None:
        return (RAW_SERVICES.get(sid) or {}).get("duration_days")

    if state.detected_service_id and _dias(state.detected_service_id):
        return _dias(state.detected_service_id)
    act = dom.by_id(state.detected_activity) if state.detected_activity else None
    dias = {_dias(sid) for sid in (act.all_services() if act else ())}
    return dias.pop() if len(dias) == 1 and None not in dias else None


def _pregunta_origen(lang: str, mismo_dia: bool = False) -> str:
    """La pregunta del origen (gen, 20-oct, textos en el español de Cartagena): desde Cartagena se sale del Muelle de la
    Bodeguita ("podemos recogerte saliendo desde Cartagena" sugería una recogida que no existe)."""
    if lang == "es":
        dia = ", ida y vuelta el mismo día" if mismo_dia else ""
        return (f"¿Desde dónde saldrías? Puedes salir *desde Cartagena* (desde el Muelle de la Bodeguita{dia}) o, si ya "
            "estás *en las islas*, coordinamos la recogida en tu hotel.")
    dia = ", round trip, same day" if mismo_dia else ""
    return (f"Where would you be departing from? You can leave *from Cartagena* (from Muelle de la Bodeguita{dia}) or, "
        "if you're already *on the islands*, we arrange pickup at your hotel.")


def _plan_en_duda(state: ConversationState) -> bool:
    """CAL-F (flag `origen_neutro_con_dos_planes`, 18-oct; precios-y-disponibilidad-con-negociacion, turno 3): "los
    valores de dos buceos o del pack de 5 buceos en 2 días" dejaba el servicio de un día (el de la actividad) y la
    duración de varios días (la del pack nombrado). La pregunta del origen mezclaba los dos: "Este plan dura 1 día y hay
    que dormir en las islas". Si el servicio es de un día y la duración dice varios, el plan no está elegido."""
    from src.flows.catalog import MULTI_DAY_SERVICES, OVERNIGHT_SERVICES  # lazy

    servicio = state.detected_service_id
    return bool(
        state.detected_activity == "certified_diving"
        and state.detected_duration == "multi_day" and servicio
        and servicio not in (MULTI_DAY_SERVICES | OVERNIGHT_SERVICES)
    )


def _plan_needs_overnight(state: ConversationState) -> bool:
    """¿El plan elegido obliga a dormir en las islas? Del catalogo (`OVERNIGHT_SERVICES`: varios dias
    o buceo nocturno, salvo los marcados "overnight": "optional", como el Curso Referido), no de una
    lista: el servicio ya resuelto, una actividad cuyos servicios obligan todos, o el paquete multi-dia
    que el cliente ya pidio."""
    from src.flows.catalog import OVERNIGHT_SERVICES  # lazy

    if state.detected_service_id and state.detected_service_id in OVERNIGHT_SERVICES:
        return True
    act = dom.by_id(state.detected_activity) if state.detected_activity else None
    services = act.all_services() if act else ()
    if services and all(sid in OVERNIGHT_SERVICES for sid in services):
        return True
    return state.detected_activity == "certified_diving" and state.detected_duration == "multi_day"


def _plan_is_single_day(state: ConversationState) -> bool:
    """¿Se SABE que el plan es de un dia (ida y vuelta desde Cartagena)? El servicio ya resuelto, o
    una actividad cuyos servicios son todos de un dia sin pernocta. Sin actividad, o con una que mezcla
    (curso PADI generico: Open Water de 2 dias y especialidades de 1), no se sabe."""
    from src.flows.catalog import MULTI_DAY_SERVICES, OVERNIGHT_SERVICES  # lazy

    not_single = MULTI_DAY_SERVICES | OVERNIGHT_SERVICES
    if state.detected_service_id:
        return state.detected_service_id not in not_single
    if state.detected_activity == "certified_diving":
        # EX-EST-2 (14-oct): "el plan de 5 buceos para el finde" sin duración detectada recibía "ida y vuelta el mismo
        # día". Solo se afirma un día si se SABE.
        return state.detected_duration == "single_day"
    act = dom.by_id(state.detected_activity) if state.detected_activity else None
    services = act.all_services() if act else ()
    return bool(services) and not any(sid in not_single for sid in services)


def _recommended_plan_intro(state: ConversationState) -> str:
    """Recomendación del plan (determinista, del catálogo) antepuesta a la
    pregunta de seguridad — mismo criterio que v0.20.27: al certificado que ya
    dijo que quiere bucear no se le manda a un menú, se le recomienda el plan
    más popular y puede cambiarlo por texto. CALN-6 (27-oct, sparring q2/q5): si el cliente ya dijo cuántas
    inmersiones o días, el plan es suyo y no hay nada que recomendar, tampoco si son las 2 de siempre («I'd do the 2
    dives» recibía «I recommend the 2 dives in 1 day plan» debajo de sus enlaces)."""
    lang = state.language
    if getattr(state, "sin_nocturna", False) or getattr(state, "salidas_sueltas", None):
        return ""  # Lo pidió así: la tabla ya decide, y la tarjeta lo dice
    paquetes = paquetes_de(state.detected_cert_days)
    if state.detected_cert_dives is None and len(paquetes) > 1:
        # CALN-39: solo dijo los días, y hay más de un paquete: se propone el pequeño y se le dice qué más hay.
        menor, mayor = paquetes[0], paquetes[-1]
        return (f"Para esos días te propongo el paquete de *{menor} inmersiones*. Si prefieres más, hay de *{mayor}* con una nocturna, o "
                "salidas sueltas de un día; dímelo.\n\n" if lang == "es" else
                f"For those days I suggest the *{menor}-dive* package. If you'd like more, there is a *{mayor}-dive* one with a night dive, or "
                "separate one-day trips; just tell me.\n\n")
    if state.detected_cert_dives is not None or paquetes:
        return ""
    if lang == "es":
        # Sparring s29: «paquete multi-día de 3 o más» debajo del «Paquete de 3 inmersiones (1 día…)».
        return ("Te recomiendo el plan de *2 inmersiones en 1 día* en las "
                "Islas del Rosario. (Si prefieres más inmersiones, hay *paquetes* de 3 o más; "
                "dímelo.)\n\n")
    return ("I recommend the *2 dives in 1 day* plan in the Rosario "
            "Islands. (If you'd rather do more dives, there are *packages* of 3 or more; just tell "
            "me.)\n\n")


def _resolve_cert_plan(state: ConversationState) -> str | None:
    """Plan de buceo certificado desde lo que ha dicho (sin consumirlo), o el recomendado por defecto. Lo decide la tabla (`flows/plan_de_buceo.py`)."""
    return cart_render.service_for_location(servicio_del_plan(plan_del_estado(state)), state)
