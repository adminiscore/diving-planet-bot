"""
Catálogo de servicios y formateadores.

Extraído de ``decision_tree.py`` (reorg §1): carga los datos de servicios/precios
desde JSON (``SERVICES``, ``ISLAND_SERVICE_MAP``, ``MULTI_DAY_SERVICES``,
``COMPANION_PRICE``, …) y expone los formateadores de precio/duración/notas y la
heurística de idioma por stopwords. Casi hoja: depende de la stdlib y de
``src.domain`` (el registro de actividades, a su vez hoja).
"""

import json
from pathlib import Path

from src.domain import activities as dom
from src.domain import lugares
from src.domain.calendario import dias_cerrados
from src.domain.politicas import (  # noqa: F401 — politica(_breve): la usan otros por aquí
    politica,
    politica_breve,
    politicas,
)
from src.utils import money

# Common Spanish/English words used to guess the language of ANY free-text
# first message (not just exact greetings), so the bot never re-asks something
# the user already revealed implicitly. Single-letter tokens are intentionally
# excluded (too ambiguous / often punctuation leftovers).
_SPANISH_STOPWORDS = {
    "hola", "buenas", "buenos", "dias", "días", "tardes", "noches", "como",
    "estas", "está", "esta", "que", "pasa", "paso", "quiero", "quisiera",
    "necesito", "somos", "queremos", "tengo", "gracias", "favor", "hacer",
    "puedo", "podemos", "disponible", "disponibilidad", "cuanto", "cuánto",
    "cuesta", "precio", "reservar", "reserva", "informacion", "información",
    "ayuda", "el", "la", "los", "las", "de", "en", "un", "una", "unos",
    "unas", "es", "son", "con", "por", "para", "no", "si", "sí", "mi", "tu",
    "su", "nos", "les", "mas", "más", "pero", "cuando", "donde", "dónde",
    "quien", "quién", "porque", "aqui", "aquí", "alli", "allí", "esto",
    "eso", "esa", "ese", "esos", "esas", "estos", "estas", "yo", "tú",
    "él", "ella", "nosotros", "ustedes", "ellos", "ellas", "te", "me",
    "lo", "nuestro", "vamos", "estamos", "estoy", "tenemos", "podria",
    "podría", "bien", "muy", "todo", "todos", "buceo", "bucear", "buzo",
    "snorkel", "curso", "minicurso", "certificado", "personas", "día",
    "días", "inmersión", "información", "viaje", "isla", "islas",
}

_ENGLISH_STOPWORDS = {
    "hello", "hi", "hey", "welcome", "good", "morning", "afternoon",
    "evening", "want", "wanna", "need", "we", "are", "is", "the", "to",
    "of", "and", "in", "that", "have", "it", "for", "not", "on", "with",
    "as", "you", "do", "at", "this", "but", "his", "from", "they", "say",
    "her", "she", "or", "will", "my", "would", "there", "their", "what",
    "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
    "when", "make", "can", "like", "time", "just", "him", "know", "take",
    "people", "into", "your", "some", "could", "them", "see", "other",
    "than", "then", "now", "look", "only", "come", "its", "over", "think",
    "also", "back", "after", "use", "two", "how", "our", "work", "first",
    "well", "way", "even", "new", "because", "any", "these", "give",
    "day", "most", "us", "please", "thanks", "thank", "book", "booking",
    "price", "cost", "diving", "dive", "snorkel", "course", "certified",
    "beginner", "group", "trip", "island", "islands", "people",
}


def _detect_language_heuristic(message: str) -> str | None:
    """Guess "es"/"en" from common stopwords in ANY free-text message.

    Falls back to None when there's no usable signal (digits-only, emoji-only,
    a single unrecognized word) so the caller can still ask explicitly.
    """
    normalized = " ".join(message.strip().lower().split())
    if not normalized:
        return None
    words = {word.strip(".,!?¡¿:;()[]{}\"'") for word in normalized.split()}
    es_count = len(words & _SPANISH_STOPWORDS)
    en_count = len(words & _ENGLISH_STOPWORDS)
    if es_count > en_count:
        return "es"
    if en_count > es_count:
        return "en"
    return None


def _detect_language_from_text(message: str) -> str | None:
    normalized = " ".join(message.strip().lower().split())
    words = {word.strip(".,!?¡¿:;()[]{}\"'") for word in normalized.split()}

    if normalized in {"en", "english"} or words.intersection({"english", "hello", "hi"}):
        return "en"
    if normalized in {"es", "espanol", "español", "spanish"} or words.intersection({"espanol", "español", "spanish", "hola"}):
        return "es"
    return _detect_language_heuristic(message)


def _join_items(items: list[str] | str | None) -> str:
    if isinstance(items, list):
        return ", ".join(items)
    return items or ""


def _format_duration(service: dict, lang: str) -> str:
    days = service.get("duration_days")
    if days == 1:
        return "1 dia" if lang == "es" else "1 day"
    if days:
        return f"{days} dias" if lang == "es" else f"{days} days"
    return "Multi-dia / variable" if lang == "es" else "Multi-day / variable"


# ord-3 (21-oct, decisión de Gadea, Coral #1150): la tarifa vive en UN sitio, `pricing.json` (la que vigila
# test_tarifa_cuadra y la que usa el juez). Cada servicio de `services.json` dice qué fila es la suya (`tarifa`, p. ej.
# "from_cartagena.paquetes.paquete_5_buceos") y aquí se le ponen sus cuatro precios al cargar. Antes había dos copias
# que había que tener iguales a mano (test_pricing_consistency las comparaba).
_KB_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge_base"
TARIFA = json.loads((_KB_DIR / "pricing.json").read_text(encoding="utf-8-sig"))
_PRECIOS_DE_LA_TARIFA = {"price_usd": "usd_online", "price_usd_normal": "usd_normal",
                         "price_cop": "cop_online", "price_cop_normal": "cop_normal"}


def fila_de_la_tarifa(ruta: str) -> dict:
    """La fila de `pricing.json` por su ruta ("origen.categoría.clave"). KeyError si no existe."""
    fila = TARIFA
    for clave in ruta.split("."):
        fila = fila[clave]
    return fila


def _servicios_con_precios() -> dict:
    """Las entradas de services.json con los precios de su fila de la tarifa (sin `tarifa`, sin precio)."""
    crudos = json.loads((_KB_DIR / "services.json").read_text(encoding="utf-8-sig")).get("services", {})
    servicios = {}
    for service_id, service in crudos.items():
        fila = fila_de_la_tarifa(service["tarifa"]) if service.get("tarifa") else {}
        servicios[service_id] = {**service, **{campo: fila.get(columna)
                                               for campo, columna in _PRECIOS_DE_LA_TARIFA.items()}}
    return servicios


def _load_services() -> dict:
    raw_services = _servicios_con_precios()
    services = {}
    for service_id, service in raw_services.items():
        # Edad minima: la del servicio si la declara, si no la de su actividad en
        # el registro (antes se deducia aqui con ids escritos a mano y buscando
        # "Minicurso"/"Snorkeling" dentro del nombre; F3a del plan de dominio).
        inferred_min_age = service.get("min_age")
        if inferred_min_age is None:
            activity = dom.activity_for_service(service_id)
            inferred_min_age = activity.min_age if activity else None

        services[service_id] = {
            "name_es": service.get("name_es", service_id),
            "name_en": service.get("name_en", service.get("name_es", service_id)),
            "requires_cert": service.get("requires_certification", False),
            "duration_days": service.get("duration_days"),
            # Precios crudos para poder elegir COP/USD segun el cliente
            "price_usd": service.get("price_usd"),
            "price_usd_normal": service.get("price_usd_normal"),
            "price_cop": service.get("price_cop"),
            "price_cop_normal": service.get("price_cop_normal"),
            "duration_es": _format_duration(service, "es"),
            "duration_en": _format_duration(service, "en"),
            "includes_es": _join_items(service.get("included_es")),
            "includes_en": _join_items(service.get("included_en")),
            "description_es": service.get("description_es", ""),
            "description_en": service.get("description_en", ""),
            "preparation_es": service.get("preparation_es", ""),
            "preparation_en": service.get("preparation_en", ""),
            "itinerary_es": service.get("itinerary_es", []) or [],
            "itinerary_en": service.get("itinerary_en", []) or [],
            "requirements_es": service.get("requirements_es", []) or [],
            "requirements_en": service.get("requirements_en", []) or [],
            "included_es": service.get("included_es", []) or [],
            "included_en": service.get("included_en", []) or [],
            "not_included_es": service.get("not_included_es", []) or [],
            "not_included_en": service.get("not_included_en", []) or [],
            "min_age": inferred_min_age,
            "includes_night_dive": service.get("includes_night_dive", False),
            # "optional": plan de varios dias en el que dormir en las islas es opcional (Curso Referido:
            # el dia 1 se puede volver a Cartagena). Sin el campo, lo deciden `duration_days` y el nocturno.
            "overnight": service.get("overnight"),
            "web_url": service.get("url") or "https://divingplanet.org/contacto/",
            "booking_url": service.get("booking_url") or service.get("url") or "https://divingplanet.org/contacto/",
            "booking_url_island": "",
            "category": service.get("category"),
            "contact_only": service.get("contact_only", False),
            # ord-6b: sin itinerario en la base, el catálogo no rellena lancha, ida y vuelta ni almuerzo.
            "detalles_por_asesor": service.get("detalles_por_asesor", False),
        }
    return services


SERVICES = _load_services()


def _load_raw_services() -> dict:
    """Las entradas de services.json TAL CUAL, sin la transformacion de `_load_services`.

    Hacen falta para `service_fact_sheet` (rag-3): la ficha de la base v2 se construye desde el
    JSON crudo (`included_es`, `duration_note_es`…), no desde las claves renombradas de `SERVICES`
    (`includes_es`, ya unido y saneado). Construir la ficha desde dos entradas distintas es
    exactamente lo que rag-2 vino a evitar: dos textos del mismo servicio que pueden diferir. ord-3: con los precios
    de la tarifa ya puestos, como en `_load_services`."""
    return _servicios_con_precios()


RAW_SERVICES = _load_raw_services()

# Etiquetas de la ficha de servicio. Vienen de `scripts/kb_v2.py` (rag-2), donde nacieron para
# construir la base curada; viven aqui desde rag-3 porque ahora la ficha se usa en DOS sitios
# (la base v2 y el contexto del turno) y tienen que ser el mismo texto.
_SHEET_T = {
    "es": {"ficha": "Ficha del servicio", "desde": "saliendo desde Cartagena",
           "islas": "para quien ya está en las Islas del Rosario (recogida en el hotel si tiene acceso marítimo)",
           "datos": "Datos", "incluye": "Incluye", "no_incluye": "No incluye", "itinerario": "Itinerario",
           "requisitos": "Requisitos", "preparacion": "Antes de la actividad", "reserva": "Reserva",
           "info": "Más información", "edad10": "edad mínima 10", "de": "de"},
    "en": {"ficha": "Service sheet", "desde": "departing from Cartagena",
           "islas": "for guests already on the Rosario Islands (hotel pick-up if it has boat access)",
           "datos": "Facts", "incluye": "Included", "no_incluye": "Not included",
           "itinerario": "Itinerary", "requisitos": "Requirements", "preparacion": "Before the activity",
           "reserva": "Booking", "info": "More info", "edad10": "minimum age 10", "de": "for"},
}


def _sheet_list(titulo: str, items) -> str:
    if isinstance(items, str):
        return f"{titulo}: {items}" if items.strip() else ""
    items = [i for i in (items or []) if i]
    return f"{titulo}:\n" + "\n".join(f"- {i}" for i in items) if items else ""


def regla_de_vuelo(actividad: str | None, lang: str) -> str | None:
    """lat-deuda-u (26-oct): cuánto esperar para volar tras la actividad, del registro de actividades (18 h al bucear,
    12 h tras el minicurso, 18 h tras el refresher aunque se venda con la ficha del minicurso). Era una línea copiada en
    los requisitos de 31 fichas, y el refresher heredaba las 12 h del minicurso."""
    registro = dom.by_id(actividad) if actividad else None
    horas = registro.horas_antes_de_volar if registro else None
    if not horas:
        return None
    return (f"Después de bucear, esperar mínimo {horas} horas antes de tomar un vuelo" if lang == "es"
            else f"After diving, wait at least {horas} hours before flying")


# Los planes que exigen el formulario médico de curso: cursos, minicurso y refresher (por su `cart_type`); los que
# llevan la regla del refresh: el buceo certificado y el propio refresher.
CON_FORMULARIO_MEDICO = {"course", "beginner", "refresh"}
CON_REFRESH = {"certified_diving", "refresher"}


def requisitos_de_politica(actividad: str | None, lang: str) -> list[str]:
    """lat-deuda-u (26-oct): los requisitos que son POLÍTICAS de la base, puestos por actividad en un solo sitio para la
    tabla de hechos y la ficha del RAG. Eran copias en las fichas, y desordenadas: el seguro solo en las de «ya en las
    islas», el refresh en 8 de las 14 de buceo certificado, el formulario en 4; una lista en inglés llevaba una línea
    que su lista en español no tenía."""
    registro = dom.by_id(actividad) if actividad else None
    if registro is None:
        return []
    requisitos = [politica("medical_restrictions", lang) if registro.cart_type in CON_FORMULARIO_MEDICO else None,
                  politica("refresh_requirement", lang) if registro.id in CON_REFRESH else None,
                  politica("insurance_form_requirement", lang),
                  regla_de_vuelo(registro.id, lang)]
    return [r for r in requisitos if r]


def enlace_en_su_idioma(url: str | None, lang: str) -> str | None:
    """lat-deuda-u (26-oct): las fichas guardan el enlace con `language=es`; al cliente inglés, en inglés. Lo hacían a
    mano la tarjeta y la lista de enlaces del RAG, y la ficha del RAG no (C15 del inventario)."""
    return url.replace("language=es", "language=en") if url and lang == "en" else url


def service_fact_sheet(service_id: str, lang: str, svc: dict | None = None, actividad: str | None = None) -> str:
    """La ficha autocontenida de un servicio: qué es, datos, incluye/no incluye, itinerario,
    requisitos, preparación y enlaces. `actividad`: la que se describe, si no es la dueña del servicio (el refresher
    con la ficha del minicurso), para la regla de vuelo.

    UNA sola fuente para dos usos (rag-3, 29-sep): el documento de la base curada v2
    (`scripts/kb_v2.ficha_servicio`, que solo le añade sus metadatos) y el contexto del turno
    cuando ya se sabe qué servicio mira el cliente. Antes, el contexto solo inyectaba
    incluye/no incluye, así que "¿a qué hora acaba el día 1?" con el Open Water elegido dependía
    de que la búsqueda encontrase la ficha — y no la encontraba (`rag_piezas`: fuera del top-8).

    `svc` es la entrada CRUDA de services.json; por defecto la de `RAW_SERVICES`."""
    svc = RAW_SERVICES[service_id] if svc is None else svc
    t = _SHEET_T[lang]
    island = service_id.endswith("_already_on_island")
    nombre = svc.get(f"name_{lang}") or service_id
    # rag-3 (30-sep, ronda core rag3-B): con dos fichas en el contexto (curso referido + refresher) el modelo mezclo
    # sus requisitos ("both require ... your referral paperwork"). Cada seccion lleva el nombre de SU servicio.
    de = f" {t['de']} {nombre}"
    partes = service_fact_parts(service_id, lang) if service_id in SERVICES else []
    if partes and not any("edad" in p or "age" in p for p in partes) and SERVICES[service_id].get("min_age") == 10:
        partes.append(t["edad10"])
    bloques = [
        f"{t['ficha']}: {nombre} — {t['islas'] if island else t['desde']}",
        svc.get(f"description_{lang}") or "",
        f"{t['datos']}{de}: " + "; ".join(partes) + "." if partes else "",
        svc.get(f"duration_note_{lang}") or "",
        _sheet_list(t["incluye"] + de, svc.get(f"included_{lang}")),
        _sheet_list(t["no_incluye"] + de, svc.get(f"not_included_{lang}")),
        _sheet_list(t["itinerario"] + de, svc.get(f"itinerary_{lang}")),
        _sheet_list(t["requisitos"] + de, [*(svc.get(f"requirements_{lang}") or []), *requisitos_de_politica(
            actividad or getattr(dom.activity_for_service(service_id), "id", None), lang)]),
        _sheet_list(t["preparacion"] + de, svc.get(f"preparation_{lang}")),
        " · ".join(x for x in (
            f"{t['reserva']}: {enlace_en_su_idioma(svc['booking_url'], lang)}"
            if svc.get("booking_url") and not svc.get("contact_only") else "",
            f"{t['info']}: {svc['url']}" if svc.get("url") else "") if x),
    ]
    return "\n\n".join(b for b in bloques if b.strip())


# Servicio desde Cartagena -> su variante "ya en las islas". Se deriva de la
# convencion de ids de services.json (`<id>_already_on_island`, que valida
# `src.domain.activities.validate`) en vez de mantenerse a mano: la lista escrita
# a mano no tenia las variantes de 3 y 4 inmersiones (discrepancia D5).
ISLAND_SERVICE_MAP = {
    service_id: f"{service_id}_already_on_island"
    for service_id in SERVICES
    if f"{service_id}_already_on_island" in SERVICES
}

# Servicios de varios dias (paquetes de inmersiones y cursos que obligan a dormir
# en las islas). Se deriva de `duration_days` de services.json en vez de una lista
# a mano, que solo tenia los paquetes: el contexto del LLM describia el Open Water
# como "de un solo dia", contra la politica `courses_overnight_requirement`
# (F3a del plan de dominio). `SERVICE_TO_CART_TYPE` se borro: no tenia ningun uso.
MULTI_DAY_SERVICES = {
    service_id for service_id, service in SERVICES.items()
    if (service.get("duration_days") or 0) > 1
}

# Servicios que obligan a dormir en las islas: los de varios dias y los que llevan buceo
# nocturno (el paquete de 3 inmersiones "de 1 dia" termina de noche: services.json lo dice en
# `requirements_es`, "debes alojarte 1 noche", y la ronda A del paso 3 lo contradecia).
OVERNIGHT_SERVICES = {
    service_id for service_id in MULTI_DAY_SERVICES | {
        sid for sid, service in SERVICES.items() if service.get("includes_night_dive")
    }
    if SERVICES[service_id].get("overnight") != "optional"
}


def _load_companion_price() -> dict:
    """El precio del acompañante, de su fila de la tarifa. ord-3: sin cifras de respaldo escritas aquí; si la fila
    falta, falla al cargar (y los tests), en vez de cotizar en silencio un precio viejo."""
    comp = fila_de_la_tarifa("from_cartagena.servicios_buceo_snorkel.acompanante")
    return {"usd_online": float(comp["usd_online"]), "usd_normal": float(comp["usd_normal"]),
            "cop_online": int(comp["cop_online"]), "cop_normal": int(comp["cop_normal"])}


COMPANION_PRICE = _load_companion_price()
# Lo que incluye el plan de acompañante según el origen (una sola fuente: el catálogo del RAG y los hechos de arq-1j). No
# incluye equipo: no se mete al agua (G10 nº 2: «todos los planes incluyen equipo», también el acompañante).
# lat-deuda-u (26-oct): lo que incluye el acompañante, del registro de actividades (estaba escrito aquí).
COMPANION_NO_INCLUYE = dom.by_id("companion").no_incluye
COMPANION_INCLUDES = dom.by_id("companion").incluye


def _lista_en_frase(elementos: list[str], lang: str) -> str:
    """«lancha, almuerzo, seguro y entrada…» (en minúscula salvo nombres propios, como lo escribía el catálogo)."""
    bajos = [e if e.startswith(("Parque", "National")) else e[:1].lower() + e[1:] for e in elementos]
    y = " y " if lang == "es" else " and "
    return bajos[0] if len(bajos) == 1 else ", ".join(bajos[:-1]) + y + bajos[-1]


_FACTS_CACHE: dict[str, str] = {}


def service_fact_parts(service_id: str, lang: str) -> list[str]:
    """Los datos de un servicio tal como los dice el catálogo (precio, días, noches, lancha, almuerzo,
    certificación, edad). rag-2: la ficha del servicio en la base v2 usa esta misma línea, así el
    catálogo y la ficha no pueden decir cosas distintas."""
    svc = SERVICES[service_id]
    es = lang == "es"
    parts = []
    if svc.get("price_usd") is not None:
        online = money.usd_cop(svc.get("price_usd"), svc.get("price_cop"))
        normal = money.usd_cop(svc.get("price_usd_normal"), svc.get("price_cop_normal"))
        parts.append(f"{online} online, {normal} normal" if es else f"{online} online, {normal} regular")
    else:
        parts.append("precio: lo cotiza un asesor" if es else "price: quoted by an advisor")
    days = svc.get("duration_days")
    if days:
        parts.append((f"{days} día" + ("s" if days > 1 else "")) if es else (f"{days} day" + ("s" if days > 1 else "")))
    if svc.get("includes_night_dive"):
        parts.append("incluye un buceo nocturno" if es else "includes a night dive")
    island = service_id.endswith("_already_on_island")
    if svc.get("detalles_por_asesor"):
        # ord-6b (21-oct): un servicio sin itinerario en la base (Bubble Makers desde
        # Cartagena). Lo de abajo rellenaría «ida y vuelta el mismo día» y «almuerzo NO incluido» sin saberlo.
        parts.append("traslado, horario y almuerzo: los confirma un asesor" if es
                     else "transfer, schedule and lunch: confirmed by an advisor")
        parts.append("sin certificación previa" if es else "no prior certification")
        if svc.get("min_age") and svc["min_age"] != 10:
            parts.append(f"edad mínima {svc['min_age']}" if es else f"minimum age {svc['min_age']}")
        return parts
    if service_id in OVERNIGHT_SERVICES and not island:
        parts.append("hay que dormir en las islas (alojamiento no incluido), no es ida y vuelta el mismo día"
                     if es else "you must stay overnight on the islands (lodging not included), not a same-day round trip")
    elif svc.get("overnight") == "optional" and not island:
        parts.append("el día 1 puedes volver a Cartagena o dormir en las islas (alojamiento no incluido)"
                     if es else "on day 1 you can return to Cartagena or stay on the islands (lodging not included)")
    elif not island and days == 1:
        parts.append("ida y vuelta desde Cartagena el mismo día" if es else "same-day round trip from Cartagena")
    includes = (svc.get("includes_es") or "").lower()
    if "transporte" in includes and not island:
        # 28-sep (ronda cache-B2): "no es ida y vuelta el mismo dia" se leia como "no hay lancha".
        parts.append("lancha Cartagena-Islas-Cartagena incluida" if es else
                     "boat Cartagena-Islands-Cartagena included")
    # rag-2 (D5, Gadea 29-sep): desde Cartagena el almuerzo va solo el día 1; desde las islas, nunca.
    if "almuerzo" not in includes:
        parts.append("almuerzo NO incluido" if es else "lunch NOT included")
    elif days and days > 1:
        parts.append("almuerzo solo el día 1" if es else "lunch on day 1 only")
    else:
        parts.append("almuerzo incluido" if es else "lunch included")
    parts.append(("requiere certificación" if svc.get("requires_cert") else "sin certificación previa")
                 if es else ("certification required" if svc.get("requires_cert") else "no prior certification"))
    if svc.get("min_age") and svc["min_age"] != 10:
        parts.append(f"edad mínima {svc['min_age']}" if es else f"minimum age {svc['min_age']}")
    return parts


def _parte_equipo(service_id: str, lang: str) -> list[str]:
    """9-oct: si el plan incluye el equipo, para la línea del CATÁLOGO (no para la
    ficha del servicio, que ya lo dice en "Incluye" y cuyo cambio obligaría a regenerar la base v2). El catálogo no lo
    decía (solo una FAQ) y el revisor tumbó "el equipo está incluido en el precio del plan", que es cierto
    (decisiones-B, turno de 15 s). Sale de los datos de cada plan: el Dive Master NO lo incluye (equipo propio)."""
    incluye = (SERVICES[service_id].get("includes_es") or "").lower()
    no_incluye = " ".join(RAW_SERVICES.get(service_id, {}).get("not_included_es") or []).lower()
    if "equipo" in incluye:
        return ["equipo incluido" if lang == "es" else "gear included"]
    if "equipo" in no_incluye:
        return ["equipo NO incluido (hay que tener equipo propio)" if lang == "es" else "gear NOT included (own gear needed)"]
    return []


def _parte_ficha(service_id: str, lang: str) -> list[str]:
    """CAL (17-oct): lo que la FICHA del producto ya dice y el catálogo no pintaba, cada cosa con su flag.

    - `catalogo_profundidad`: hasta qué profundidad certifica (`max_depth_m`: Open Water 18 m, Advanced 30 m, lo que
      la base dice en el registro de actividades). Sin esto, a "¿cuántos metros bajan?" el RAG solo podía decir
      "depende de la certificación": el dato no estaba en nada que viera (cal-18).
    - La preparación de cada producto (`preparation_*`) NO va: medido el 17-oct (banco CAL-A 16x3), arreglaba cal-49
      pero rompía cal-26 y cal-64; dieciocho párrafos en TODOS los turnos compiten con lo que hace falta en cada uno.

    Va en el catálogo y no en una regla del prompt: es un dato de cada producto y sale de su ficha. Como el juez lee
    el mismo catálogo, también puede comprobar lo que el bot diga de ello."""
    svc = RAW_SERVICES.get(service_id, {})
    es = lang == "es"
    partes: list[str] = []
    metros = svc.get("max_depth_m")
    if metros:
        partes.append(f"certifica para bucear hasta {metros} m" if es else f"certifies you to dive down to {metros} m")
    return partes


def _profundidad_por_certificacion(lang: str) -> str | None:
    """CAL (17-oct, flag `catalogo_profundidad`): la profundidad máxima de cada buzo la marca su certificación,
    como una línea general del catálogo (junto a la edad mínima o los días que operamos). Los números salen de las
    fichas de los cursos que certifican (`max_depth_m`), no se escriben aquí: un solo origen."""
    es = lang == "es"
    por_curso: dict[str, int] = {}
    for sid, svc in RAW_SERVICES.items():
        metros = svc.get("max_depth_m")
        if not metros or sid.endswith("_already_on_island"):
            continue
        por_curso[svc.get("name_es" if es else "name_en") or sid] = metros
    if not por_curso:
        return None
    orden = sorted(por_curso.items(), key=lambda par: par[1])
    if es:
        cursos = "; ".join(f"{nombre}: hasta {metros} m" for nombre, metros in orden)
        return f"Profundidad máxima de cada buzo según su certificación (también en las salidas de buceo): {cursos}."
    cursos = "; ".join(f"{nombre}: down to {metros} m" for nombre, metros in orden)
    return f"Maximum depth for each diver according to their certification (also on dive trips): {cursos}."


def policies_facts(lang: str) -> str:
    """EX-RAG-1 (flag `rag_politicas_en_contexto`, aprobado por Gadea el 14-oct para medir): las políticas del negocio
    enteras (data/knowledge_base/policies.json, ~2.000 tokens), para que vayan SIEMPRE en el contexto del RAG como el
    catálogo. Ronda atencion-B2: un mensaje que mezclaba el paquete de 5 buceos, el check-out y el equipaje solo
    recuperaba FAQs y servicios, y el RAG contestaba que no tenía la política de equipaje. CALN-8 (3) (28-oct): ya solo
    las ve el juez del RAG; al escritor le llegan en los hechos las que el caso exige (CALN-7)."""
    policies = politicas()
    head = "Políticas de Diving Planet:" if lang == "es" else "Diving Planet policies:"
    lines = [f"- {text.get(lang) or text.get('es', '')}" for text in policies.values() if isinstance(text, dict)]
    return "\n".join([head, *[ln for ln in lines if ln.strip() != "-"]])


_DESCUENTOS = ("online_direct_booking", "group_discount", "own_equipment_discount", "colombian_cop_pricing")


def descuentos_de_la_base(lang: str) -> dict[str, str]:
    """arq-8h: cada descuento con sus condiciones, tal cual de discounts.json (el único sitio). El de grupo lleva la
    nota del acompañante. lat-deuda-u (26-oct, confirmado por Gadea): también la regla de que no se acumulan (grupo y
    equipo propio no se suman entre sí, cada uno sí con el online), que estaba en la base y no la leía ningún camino."""
    base = json.loads((_KB_DIR / "discounts.json").read_text(encoding="utf-8-sig"))
    datos = base.get("discounts", {})
    lang = "es" if lang == "es" else "en"
    textos = {}
    for clave in _DESCUENTOS:
        d = datos.get(clave) or {}
        texto = d.get(f"description_{lang}") or d.get("description_es")
        if not texto:
            continue
        nota = d.get(f"companion_note_{lang}")
        textos[clave] = f"{texto} {nota}" if nota else texto
    acumulacion = (base.get("discount_policies") or {}).get("non_cumulative") or {}
    if texto := acumulacion.get(lang) or acumulacion.get("es"):
        textos["non_cumulative"] = texto
    return textos


def catalog_facts(lang: str) -> str:
    """Paso 5 (RAG, 27-sep): el catalogo entero como hechos compactos para el contexto
    del RAG — precio online y normal, duracion, si obliga a dormir en las islas y si pide
    certificacion, de cada servicio y desde cada origen. Sale de services.json/pricing.json, no
    se escribe a mano.

    Ronda A (27-sep): los atajos de precio por regex contestaban preguntas que no eran de precio
    ("¿cuánto tiempo dura?" -> lista de precios) o con el servicio equivocado ("curso básico" ->
    buceo certificado), y el LLM contradecia reglas del catalogo que la busqueda no traia (cursos
    de 2 dias "ida y vuelta el mismo dia", el paquete de 3 inmersiones "en 1 dia"). Con estos
    hechos siempre en el contexto el LLM contesta la pregunta real y el precio sale del catalogo
    (el guard de importes sigue exigiendo que cada cifra este en el contexto)."""
    clave = lang
    if clave in _FACTS_CACHE:
        return _FACTS_CACHE[clave]

    es = lang == "es"
    groups: dict[bool, list[str]] = {False: [], True: []}
    for service_id, svc in SERVICES.items():
        if svc.get("category") == "private":
            continue
        name = svc.get("name_es" if es else "name_en") or service_id
        island = service_id.endswith("_already_on_island")
        parts = service_fact_parts(service_id, lang)
        # 9-oct: cada plan dice si el equipo va incluido (el Dive Master no).
        parts += _parte_equipo(service_id, lang)
        parts += _parte_ficha(service_id, lang)
        groups[island].append(f"- {name}: " + "; ".join(parts) + ".")
    # El refresher se vende con el servicio que le da el registro de actividades (hoy el minicurso). Paso 8
    # (28-sep): sin el atajo fijo del refresher, el RAG decia "el refresh no esta listado con precio".
    for location, target in (("cartagena", False), ("island", True)):
        ids = dom.service_ids("refresher", location)
        svc = SERVICES.get(ids[0], {}) if ids else {}
        if svc.get("price_usd") is not None:
            price = money.usd_cop(svc.get("price_usd"), svc.get("price_cop"))
            groups[target].append(
                f"- Refresher (repaso para certificados con más de 2 años sin bucear; se reserva como "
                f"'{svc.get('name_es')}'): {price} online."
                if es else
                f"- Refresher (review for certified divers with more than 2 years without diving; booked as "
                f"'{svc.get('name_en')}'): {price} online."
            )
    comp = COMPANION_PRICE
    companion = money.usd_cop(comp["usd_online"], comp["cop_online"])
    # 9-oct (Gadea): en los hoteles base la recogida no depende del acceso maritimo. Con solo "si tiene acceso
    # maritimo" en el catalogo, el RAG (y RAG_CONDICIONES) dudaba tambien de Cocoliso: "el equipo confirma si Cocoliso
    # tiene acceso maritimo" (paquete-5-buceos-islas-residente-sin-recogida).
    base = list(lugares.hoteles_base())  # lat-deuda-u: de data/knowledge_base/lugares.json (nombres propios, tal cual)
    base_es = base[0] if len(base) == 1 else ", ".join(base[:-1]) + " y " + base[-1]
    base_en = base[0] if len(base) == 1 else ", ".join(base[:-1]) + " and " + base[-1]
    islas_es = ("Si ya estás en las Islas del Rosario (recogida en tu hotel si tiene acceso marítimo; en nuestros "
                f"hoteles base, {base_es}, en Isla Grande, la recogida está confirmada e incluida):")
    islas_en = ("If already on the Rosario Islands (pickup at your hotel if it has boat access; at our base hotels, "
                f"{base_en} on Isla Grande, pickup is confirmed and included):")
    companion_normal = money.usd_cop(comp["usd_normal"], comp["cop_normal"])
    if es:
        head = ("CATÁLOGO OFICIAL (fuente de verdad; precios por persona, 'online' = con el 10% de "
                "descuento por reservar en la web):")
        out = [head, "Saliendo desde Cartagena:", *groups[False],
               f"- Acompañante (no bucea, va en la lancha con el grupo): {companion} online, {companion_normal} normal; "
               f"incluye {_lista_en_frase(COMPANION_INCLUDES['es']['cartagena'], 'es')}; no incluye "
               f"{COMPANION_NO_INCLUYE['es']}.",
               islas_es,
               *groups[True],
               f"- Acompañante - ya en las islas (no bucea, va en la lancha con el grupo): {companion} online, "
               f"{companion_normal} normal (el mismo precio); incluye "
               f"{_lista_en_frase(COMPANION_INCLUDES['es']['island'], 'es')}; almuerzo NO incluido; no incluye "
               f"{COMPANION_NO_INCLUYE['es']}.",
               f"Edad mínima {dom.by_id('minicourse').min_age} años salvo que se indique otra.",
               f"Operamos todos los días del año salvo {dias_cerrados('es')}. Tú no ves los cupos: "
               "el cliente elige la fecha y el número de personas en el calendario del link de reserva.",
               "Descuentos: " + " ".join(descuentos_de_la_base("es").values()),
               "Moneda: los colombianos (vivan donde vivan) y los residentes en Colombia pagan en COP; el resto, en "
               "USD (en un grupo mixto de colombianos o residentes y extranjeros, toda la reserva en USD); es el "
               "mismo precio en las dos monedas: el precio en COP de cada plan es el que pagan los "
               "colombianos. NO existe descuento ni tarifa rebajada para colombianos: si el cliente cree que la hay, "
               "díselo claramente (solo cambia la moneda). " + MONEDA_SIN_NACIONALIDAD["es"] + " No sumes ni calcules "
               "totales. "
               "Si el cliente "
               "cita un precio que no coincide con el catálogo, dale el del catálogo sin repetir su cifra."]
    else:
        head = ("OFFICIAL CATALOG (source of truth; prices per person, 'online' = with the 10% discount "
                "for booking on the website):")
        out = [head, "Departing from Cartagena:", *groups[False],
               f"- Companion (doesn't dive, rides the boat with the group): {companion} online, {companion_normal} "
               f"regular; includes {_lista_en_frase(COMPANION_INCLUDES['en']['cartagena'], 'en')}; does not include "
               f"{COMPANION_NO_INCLUYE['en']}.",
               islas_en,
               *groups[True],
               f"- Companion - already on the islands (doesn't dive, rides the boat with the group): {companion} online, "
               f"{companion_normal} regular (the same price); includes "
               f"{_lista_en_frase(COMPANION_INCLUDES['en']['island'], 'en')}; lunch NOT included; does not include "
               f"{COMPANION_NO_INCLUYE['en']}.",
               f"Minimum age {dom.by_id('minicourse').min_age} unless stated otherwise.",
               f"We operate every day of the year except {dias_cerrados('en')}. You can't see open slots: "
               "the customer picks the date and number of people in the booking link's calendar.",
               "Discounts: " + " ".join(descuentos_de_la_base("en").values()),
               "Currency: Colombians (wherever they live) and residents of Colombia pay in COP; everyone else in USD "
               "(in a mixed group of Colombians or residents and foreigners, the whole booking in USD); it is the same price in both currencies: each plan's COP price is what Colombians pay. There is NO "
               "discount or reduced rate for Colombians: if the customer thinks there is one, say so clearly (only "
               "the currency changes). " + MONEDA_SIN_NACIONALIDAD["en"] + " Do not add up or compute totals. If the "
               "customer quotes a price that doesn't match the catalog, give the catalog price without repeating theirs."]
    # arq-8h / lat-deuda-u: los descuentos salen de discounts.json (arriba, sin texto fijo que sustituir).
    text = chr(10).join(out)
    # La profundidad también como regla general: "certifica hasta 18 m" en la línea del CURSO no le llegaba a quien
    # pregunta por una SALIDA siendo ya buzo certificado (cal-18 siguió 3/3 con solo la parte de la ficha).
    profundidad = _profundidad_por_certificacion(lang)
    if profundidad:
        text += chr(10) + profundidad
    _FACTS_CACHE[clave] = text
    return text


# lat-deuda-u (26-oct, decisión de Gadea): sin saber la nacionalidad, el precio en USD y en COP, como la tabla de hechos
# (arq-5c); sustituye a la regla de solo USD de CAL-B (15-oct). La regla del código está en `src/flows/moneda.py`.
MONEDA_SIN_NACIONALIDAD = {
    "es": "Si no sabes la nacionalidad del cliente, da el precio en USD y en COP: es el mismo precio, solo cambia la "
          "moneda (si te dice que es colombiano o residente en Colombia, solo en COP).",
    "en": "If you don't know the customer's nationality, give the price in USD and in COP: it is the same price, only "
          "the currency changes (if they tell you they are Colombian or a resident of Colombia, only in COP).",
}


# 1-oct (análisis del juez, `docs/robustness/juez/README.md`): el juez y el que redacta leen el mismo catálogo pero
# necesitan cosas distintas de la regla de moneda. Al que redacta le hace falta la INSTRUCCIÓN (si el cliente cree
# que hay tarifa especial para colombianos, decirle que no); al juez, el HECHO. Con la instrucción, el juez rechazaba
# el precio COP correcto en cuanto la respuesta decía "para colombianos" (14 de 54 rechazos); con el hecho en el
# texto del que redacta, el bot dejaba de corregir el mito (1/4). Cada uno recibe la suya.
_MONEDA_PARA_EL_JUEZ = {
    "es": ("Moneda: los colombianos (vivan donde vivan) y los residentes en Colombia pagan en COP y el resto en USD; "
           "es el mismo precio en las dos monedas. El precio en COP de cada plan es el precio para colombianos: una "
           "respuesta que da ese precio 'para colombianos' es correcta. Lo que no existe es un descuento ni una "
           "tarifa rebajada para colombianos."),
    "en": ("Currency: Colombians (wherever they live) and residents of Colombia pay in COP and everyone else in USD; "
           "it is the same price in both currencies. Each plan's COP price is the price for Colombians: a response "
           "that gives that price 'for Colombians' is correct. What does not exist is a discount or a reduced rate "
           "for Colombians."),
}


def para_el_juez(hechos: str, lang: str) -> str:
    """El catálogo que ve el juez de grounding: el mismo, con la regla de moneda como hecho (ver arriba)."""
    linea = _MONEDA_PARA_EL_JUEZ["es" if lang == "es" else "en"]
    return chr(10).join(linea if ln.startswith(("Moneda:", "Currency:")) else ln for ln in hechos.split(chr(10)))


def catalog_booking_links(lang: str) -> str:
    """Paso 6 (27-sep): el link de reserva de cada servicio para el contexto del RAG. Con la
    regla nueva de "¿cómo pago?" (el link de reserva) el LLM escribía un link que no estaba en el
    contexto, el guard de URLs lo rechazaba y la respuesta acababa en "no lo tengo a la mano" (ronda B
    del paso 6, "no sé cómo se haga la reserva"). Los de servicios que cierra un asesor no van."""
    es = lang == "es"
    lines = []
    for service_id, svc in SERVICES.items():
        url = svc.get("booking_url")
        if not url or svc.get("contact_only") or svc.get("category") == "private":
            continue
        url = enlace_en_su_idioma(url, lang)
        lines.append(f"- {svc.get('name_es' if es else 'name_en') or service_id}: {url}")
    head = ("LINKS DE RESERVA ONLINE (el cliente elige fecha y personas y paga ahí; comparte solo el del "
            "servicio que corresponde):" if es else
            "ONLINE BOOKING LINKS (the customer picks date and people and pays there; share only the one "
            "for the matching service):")
    return chr(10).join([head, *lines])
