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


def _sanitize_includes(items: list[str] | None) -> list[str] | None:
    """Remove DIVE TO HEAL eco-social contribution from includes lists."""
    if not isinstance(items, list):
        return items
    # Filter any language variant containing 'DIVE TO HEAL'
    return [it for it in items if "DIVE TO HEAL" not in it.upper()]


def _format_price(service: dict) -> str:
    price = service.get("price_usd")
    normal = service.get("price_usd_normal")
    note = service.get("price_note")
    if price and normal:
        return f"{money.usd(price)} online / {money.usd(normal)} normal"
    if price:
        return money.usd(price)
    if note:
        return note
    return "Consultar precio actualizado en la web"


def _format_duration(service: dict, lang: str) -> str:
    days = service.get("duration_days")
    if days == 1:
        return "1 dia" if lang == "es" else "1 day"
    if days:
        return f"{days} dias" if lang == "es" else f"{days} days"
    return "Multi-dia / variable" if lang == "es" else "Multi-day / variable"


def _flight_rule(service: dict, lang: str) -> str:
    requirements = service.get(f"requirements_{lang}", [])
    for requirement in requirements:
        lowered = requirement.lower()
        if "vuelo" in lowered or "flying" in lowered or "fly" in lowered:
            return requirement
    return ""


def _extra_notes(service: dict, lang: str) -> str:
    parts = []
    description = service.get(f"description_{lang}")
    preparation = service.get(f"preparation_{lang}")
    not_included = service.get(f"not_included_{lang}", [])
    if description:
        parts.append(description)
    if preparation:
        title = "Preparacion: " if lang == "es" else "Preparation: "
        parts.append(title + preparation)
    if lang == "es":
        if "Minicurso" in service.get("name_es", "") and "No necesitas experiencia previa" not in " ".join(parts):
            parts.append("No necesitas experiencia previa.")
        if "Snorkeling" in service.get("name_es", "") and "Actividad de superficie" not in " ".join(parts):
            parts.append("Actividad de superficie ideal para acompañantes o personas que no quieren bucear.")
        if service.get("includes_night_dive") and "quitar la nocturna" not in " ".join(parts):
            parts.append("Si quieres quitar la nocturna, cambiar noches o personalizar el paquete, lo revisamos con un asesor.")
        if any("Hotel/alojamiento" in item for item in not_included) and "alojamiento no esta incluido" not in " ".join(parts):
            parts.append("El alojamiento no esta incluido y se reserva aparte con el hotel.")
    return " ".join(parts)


def _extra_notes_multiline(service: dict, lang: str) -> str:
    lines: list[str] = []
    description = service.get(f"description_{lang}")
    preparation = service.get(f"preparation_{lang}")
    itinerary = service.get(f"itinerary_{lang}", [])
    not_included = service.get(f"not_included_{lang}", [])
    requirements = service.get(f"requirements_{lang}", [])

    if description:
        lines.append(description)

    if preparation:
        title = "Preparacion:" if lang == "es" else "Preparation:"
        lines.append(title)
        lines.append(f"- {preparation}")

    if itinerary:
        title = "Itinerario:" if lang == "es" else "Itinerary:"
        lines.append(title)
        for item in itinerary:
            lines.append(f"- {item}")

    if requirements:
        title = "Requisitos:" if lang == "es" else "Requirements:"
        lines.append(title)
        for item in requirements:
            lines.append(f"- {item}")

    if not_included:
        title = "No incluye:" if lang == "es" else "Not included:"
        lines.append(title)
        for item in not_included:
            lines.append(f"- {item}")

    if lang == "es":
        name_es = service.get("name_es", "")
        if "Minicurso" in name_es and not any("No necesitas experiencia previa" in ln for ln in lines):
            lines.append("No necesitas experiencia previa.")
        if "Snorkeling" in name_es and not any("Actividad de superficie" in ln for ln in lines):
            lines.append("Actividad de superficie ideal para acompañantes o personas que no quieren bucear.")
        if service.get("includes_night_dive") and not any("nocturna" in ln for ln in lines):
            lines.append("Si quieres quitar la nocturna, cambiar noches o personalizar el paquete, lo revisamos con un asesor.")
        if any("Hotel/alojamiento" in item for item in not_included) and not any("alojamiento no esta incluido" in ln for ln in lines):
            lines.append("El alojamiento no esta incluido y se reserva aparte con el hotel.")

    return "\n".join(lines)






def _load_services() -> dict:
    path = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "services.json"
    raw_services = json.loads(path.read_text(encoding="utf-8-sig")).get("services", {})
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
            "price": _format_price(service),
            # Precios crudos para poder elegir COP/USD segun el cliente
            "price_usd": service.get("price_usd"),
            "price_usd_normal": service.get("price_usd_normal"),
            "price_cop": service.get("price_cop"),
            "price_cop_normal": service.get("price_cop_normal"),
            "price_note": service.get("price_note"),
            "price_note_es": service.get("price_note_es"),
            "price_note_en": service.get("price_note_en"),
            "duration_es": _format_duration(service, "es"),
            "duration_en": _format_duration(service, "en"),
            "includes_es": _join_items(_sanitize_includes(service.get("included_es"))),
            "includes_en": _join_items(_sanitize_includes(service.get("included_en"))),
            "description_es": service.get("description_es", ""),
            "description_en": service.get("description_en", ""),
            "preparation_es": service.get("preparation_es", ""),
            "preparation_en": service.get("preparation_en", ""),
            "itinerary_es": service.get("itinerary_es", []) or [],
            "itinerary_en": service.get("itinerary_en", []) or [],
            "summary_intro_es": service.get("summary_intro_es", []) or [],
            "summary_intro_en": service.get("summary_intro_en", []) or [],
            "itinerary_overview_es": service.get("itinerary_overview_es", []) or [],
            "itinerary_overview_en": service.get("itinerary_overview_en", []) or [],
            "requirements_es": service.get("requirements_es", []) or [],
            "requirements_en": service.get("requirements_en", []) or [],
            "not_included_es": service.get("not_included_es", []) or [],
            "not_included_en": service.get("not_included_en", []) or [],
            "min_age": inferred_min_age,
            "extra_notes_es": _extra_notes(service, "es"),
            "extra_notes_en": _extra_notes(service, "en"),
            "extra_block_es": _extra_notes_multiline(service, "es"),
            "extra_block_en": _extra_notes_multiline(service, "en"),
            "flight_rule_es": _flight_rule(service, "es"),
            "flight_rule_en": _flight_rule(service, "en"),
            "includes_night_dive": service.get("includes_night_dive", False),
            "web_url": service.get("url") or "https://divingplanet.org/contacto/",
            "booking_url": service.get("booking_url") or service.get("url") or "https://divingplanet.org/contacto/",
            "booking_url_island": "",
            "category": service.get("category"),
            "contact_only": service.get("contact_only", False),
        }
    return services


SERVICES = _load_services()

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
OVERNIGHT_SERVICES = MULTI_DAY_SERVICES | {
    service_id for service_id, service in SERVICES.items() if service.get("includes_night_dive")
}

# Above this many people in one line item, nudge toward a human-coordinated
# private/group service instead of silently treating it like a normal small
# group (T123 in docs/archive/test-battery-edge-cases.md). Deliberately does NOT state
# a maximum boat/group capacity (the KB has none — inventing one is forbidden,
# see rag_agent.py's "never invent capacity numbers" rule); it only suggests
# advisor coordination while continuing the flow normally.
LARGE_GROUP_ADVISOR_THRESHOLD = 15

REFRESHER_PRESERVE_SERVICES = {
    "2_dives_1_day",
    "2_dives_1_day_already_on_island",
    "3_dives_1_day",
    "4_dives_2_days",
    "5_dives_2_days",
    "7_dives_3_days",
    "9_dives_4_days",
    "3_dives_1_day_already_on_island",
    "4_dives_2_days_already_on_island",
    "4_dives_2_days_mixed_already_on_island",
    "5_dives_2_days_already_on_island",
    "7_dives_3_days_already_on_island",
    "9_dives_4_days_already_on_island",
}

SPECIALTY_SERVICE_IDS = {
    "mindful_diving",
    "naturalist_specialty",
    "fish_identification_specialty",
    "buoyancy_specialty",
    "nitrox_specialty",
    "fish_identification_specialty_already_on_island",
    "nitrox_specialty_already_on_island",
    "naturalist_specialty_already_on_island",
    "buoyancy_specialty_already_on_island",
}


def _load_companion_price() -> dict:
    path = Path(__file__).resolve().parents[2] / "data" / "knowledge_base" / "pricing.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"usd_online": 80.44, "usd_normal": 89.38, "cop_online": 288000, "cop_normal": 320000}
    for origin in ("from_cartagena", "from_islands"):
        section = data.get(origin, {}).get("servicios_buceo_snorkel", {})
        comp = section.get("acompanante") if isinstance(section, dict) else None
        if comp:
            return {
                "usd_online": float(comp.get("usd_online", 80.44)),
                "usd_normal": float(comp.get("usd_normal", 89.38)),
                "cop_online": int(comp.get("cop_online", 288000)),
                "cop_normal": int(comp.get("cop_normal", 320000)),
            }
    return {"usd_online": 80.44, "usd_normal": 89.38, "cop_online": 288000, "cop_normal": 320000}


COMPANION_PRICE = _load_companion_price()


_FACTS_CACHE: dict[str, str] = {}


def catalog_facts(lang: str) -> str:
    """Paso 5 (RAG, flag `rag_v2`): el catalogo entero como hechos compactos para el contexto
    del RAG — precio online y normal, duracion, si obliga a dormir en las islas y si pide
    certificacion, de cada servicio y desde cada origen. Sale de services.json/pricing.json, no
    se escribe a mano.

    Ronda A (27-sep): los atajos de precio por regex contestaban preguntas que no eran de precio
    ("¿cuánto tiempo dura?" -> lista de precios) o con el servicio equivocado ("curso básico" ->
    buceo certificado), y el LLM contradecia reglas del catalogo que la busqueda no traia (cursos
    de 2 dias "ida y vuelta el mismo dia", el paquete de 3 inmersiones "en 1 dia"). Con estos
    hechos siempre en el contexto el LLM contesta la pregunta real y el precio sale del catalogo
    (el guard de importes sigue exigiendo que cada cifra este en el contexto)."""
    if lang in _FACTS_CACHE:
        return _FACTS_CACHE[lang]
    es = lang == "es"
    groups: dict[bool, list[str]] = {False: [], True: []}
    for service_id, svc in SERVICES.items():
        if svc.get("category") == "private":
            continue
        name = svc.get("name_es" if es else "name_en") or service_id
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
        island = service_id.endswith("_already_on_island")
        if service_id in OVERNIGHT_SERVICES and not island:
            parts.append("hay que dormir en las islas (alojamiento no incluido), no es ida y vuelta el mismo día"
                         if es else "you must stay overnight on the islands (lodging not included), not a same-day round trip")
        elif not island and days == 1:
            parts.append("ida y vuelta desde Cartagena el mismo día" if es else "same-day round trip from Cartagena")
        parts.append(("requiere certificación" if svc.get("requires_cert") else "sin certificación previa")
                     if es else ("certification required" if svc.get("requires_cert") else "no prior certification"))
        if svc.get("min_age") and svc["min_age"] != 10:
            parts.append(f"edad mínima {svc['min_age']}" if es else f"minimum age {svc['min_age']}")
        groups[island].append(f"- {name}: " + "; ".join(parts) + ".")
    comp = COMPANION_PRICE
    companion = money.usd_cop(comp["usd_online"], comp["cop_online"])
    companion_normal = money.usd_cop(comp["usd_normal"], comp["cop_normal"])
    if es:
        head = ("CATÁLOGO OFICIAL (fuente de verdad; precios por persona, 'online' = con el 10% de "
                "descuento por reservar en la web):")
        out = [head, "Saliendo desde Cartagena:", *groups[False],
               f"- Acompañante (no bucea, va en la lancha): {companion} online, {companion_normal} normal.",
               "Si ya estás en las Islas del Rosario (recogida en tu hotel si tiene acceso marítimo):",
               *groups[True],
               "Edad mínima 10 años salvo que se indique otra.",
               "Operamos todos los días del año salvo el 25 de diciembre y el 1 de enero. Tú no ves los cupos: "
               "el cliente elige la fecha y el número de personas en el calendario del link de reserva.",
               "Moneda: colombianos/residentes pagan en COP y extranjeros en USD, mismo precio; si no sabes "
               "la nacionalidad del cliente, da las dos monedas. No sumes ni calcules totales. Si el cliente "
               "cita un precio que no coincide con el catálogo, dale el del catálogo sin repetir su cifra."]
    else:
        head = ("OFFICIAL CATALOG (source of truth; prices per person, 'online' = with the 10% discount "
                "for booking on the website):")
        out = [head, "Departing from Cartagena:", *groups[False],
               f"- Companion (doesn't dive, rides the boat): {companion} online, {companion_normal} regular.",
               "If already on the Rosario Islands (pickup at your hotel if it has boat access):",
               *groups[True],
               "Minimum age 10 unless stated otherwise.",
               "We operate every day of the year except December 25 and January 1. You can't see open slots: "
               "the customer picks the date and number of people in the booking link's calendar.",
               "Currency: Colombians/residents pay in COP and foreigners in USD, same price; if you don't "
               "know the customer's nationality, give both currencies. Do not add up or compute totals. If the "
               "customer quotes a price that doesn't match the catalog, give the catalog price without repeating theirs."]
    text = chr(10).join(out)
    _FACTS_CACHE[lang] = text
    return text
