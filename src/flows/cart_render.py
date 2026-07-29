"""Render y parseo del carrito para el núcleo conversacional (Fase 4, P1b).

El núcleo importa las funciones públicas de aquí (`service_for_location`,
`parse_quantity`, `cart_label_for`, `goto_final_summary`, `cart_booking_blocks`).
La lógica real —movida FÍSICAMENTE desde `DecisionTree` en Fase 4 P1b— vive ahora
en este módulo como funciones puras (stateless), no como métodos de la máquina de
estados legacy (ya retirada). Solo importa el catálogo/estado compartido de
`catalog.py`/`state.py` (SERVICES/MESSAGE_SPLIT/COMPANION_PRICE/
ISLAND_SERVICE_MAP/ConversationState/Step).
"""

from __future__ import annotations

import unicodedata

from src.flows.catalog import COMPANION_PRICE, ISLAND_SERVICE_MAP, SERVICES
from src.flows.state import MESSAGE_SPLIT, ConversationState, Step
from src.utils.fuzzy import fuzzy_word_number

# ─────────────────────── API pública (la usa el núcleo) ───────────────────────

def service_for_location(service_id, state):
    """Resuelve el `service_id` a su variante según la ubicación (isla vs Cartagena)."""
    return _service_for_location(service_id, state)


def parse_quantity(message):
    """Parsea una cantidad ('2', 'dos', 'un par' via fuzzy) o None."""
    return _parse_mixed_quantity(message)


def cart_label_for(item_type, plan, lang):
    """Etiqueta legible de un ítem del carrito (cert/beginner/snorkel/course)."""
    return _cart_label_for(item_type, plan, lang)


def goto_final_summary(state):
    """Resumen final determinista del carrito (precios + links del catálogo)."""
    return _goto_mixed_final_summary(state)


def cart_booking_blocks(state):
    """Bloques de reserva (servicio + link) por ítem del carrito."""
    return _cart_booking_blocks(state)


def cart_service_id(item_type, plan, state):
    """ID de catálogo (para precios/links) de un ítem del carrito, o None."""
    return _cart_service_id(item_type, plan, state)


# ─────────────── Implementación (funciones puras, movidas de DecisionTree) ───────────────


def _service_for_location(service_id: str, state: ConversationState) -> str:
    if state.location == "island":
        return ISLAND_SERVICE_MAP.get(service_id, service_id)
    return service_id


def _cart_label_for(item_type: str, plan: str | None, lang: str) -> str:
    """Human-readable label for a cart item."""
    if item_type == "cert":
        service = SERVICES.get(plan) or {}
        label = service.get(f"name_{lang}") or service.get("name_es")
        if label:
            return label
        if lang == "es":
            return "Salidas de Buceo - 2 inmersiones (1 día)" if plan == "2_dives_1_day" else "Buceo certificado"
        return "Fun Dives - 2 dives (1 day)" if plan == "2_dives_1_day" else "Certified diving"
    if item_type == "beginner":
        return "Buceo principiantes (Minicurso)" if lang == "es" else "Beginner diving (Mini-course)"
    if item_type == "refresh":
        return "Refresher para certificados" if lang == "es" else "Certified diver refresher"
    if item_type == "snorkel":
        return "Snorkel" if lang == "es" else "Snorkeling"
    if item_type == "course":
        service = SERVICES.get(plan) or {}
        return service.get(f"name_{lang}") or service.get("name_es") or ("Curso PADI" if lang == "es" else "PADI course")
    if item_type == "companion":
        return "Acompañante (sin actividad)" if lang == "es" else "Companion (no activity)"
    return item_type


def _cart_service_id(item_type: str, plan: str | None, state: ConversationState) -> str | None:
    """Map a cart item to the catalog service ID (for prices and booking URLs)."""
    if item_type == "cert":
        return plan or _service_for_location("2_dives_1_day", state)
    if item_type == "beginner":
        return _service_for_location("minicourse", state)
    if item_type == "refresh":
        return _service_for_location("minicourse", state)
    if item_type == "snorkel":
        return _service_for_location("snorkeling", state)
    if item_type == "course":
        return plan
    return None


def _parse_mixed_quantity(message: str) -> int | None:
    import re as _re
    msg = " ".join(message.strip().lower().split())
    if msg in {"6+", "6 o mas", "6 o más", "6 or more", "more"}:
        return 6
    try:
        n = int(msg)
        if 1 <= n <= 99:
            return n
    except ValueError:
        pass
    # Accept word numbers (with typo tolerance via fuzzy helper)
    _word_num = {
        'uno': 1, 'una': 1, 'one': 1,
        'dos': 2, 'two': 2,
        'tres': 3, 'three': 3,
        'cuatro': 4, 'four': 4,
        'cinco': 5, 'five': 5,
        'seis': 6, 'six': 6,
        'siete': 7, 'seven': 7,
        'ocho': 8, 'eight': 8,
        'nueve': 9, 'nine': 9,
        'diez': 10, 'ten': 10,
    }
    _fuzzy_n = fuzzy_word_number(msg)
    if _fuzzy_n is not None:
        return _fuzzy_n
    # Extract number from phrases like "somos 3", "vamos 2", "3 personas", "we are 4"
    m = _re.search(r'\b(\d+)\b', msg)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 99:
            return n
    # Extract word number from phrase — exact match first, then fuzzy per token
    for word, val in _word_num.items():
        if _re.search(rf'\b{word}\b', msg):
            return val
    for token in msg.split():
        _n = fuzzy_word_number(token)
        if _n is not None:
            return _n
    # "Self + companion" phrasings with no explicit number → 2 people.
    # e.g. "yo y mi pareja", "voy yo y mi novia", "vengo con mi amiga",
    # "mi hijo y yo", "me acompaña mi esposo". Fixes the qty step answering
    # "no te entendí" to a perfectly clear two-person answer. "familia" is
    # excluded on purpose (its size is unknown — don't guess 2).
    _norm = "".join(
        c for c in unicodedata.normalize("NFD", msg) if unicodedata.category(c) != "Mn"
    )
    _comp = r"(?:pareja|novi[oa]|espos[oa]|amig[oa]|herman[oa]|hij[oa]|mama|papa|acompanante)"
    _self_companion = [
        rf"\byo\s+y\s+mi\s+{_comp}",
        rf"\bmi\s+{_comp}\s+y\s+yo\b",
        rf"\b(?:vengo|voy|vamos|venimos)\s+con\s+mi\s+{_comp}",
        rf"\bcon\s+mi\s+{_comp}\b",
        rf"\bme\s+acompana\s+mi\s+{_comp}",
        rf"\bmi\s+{_comp}\s+me\s+acompana",
    ]
    if any(_re.search(p, _norm) for p in _self_companion):
        return 2
    return None


def _format_activity_booking_messages(state: ConversationState) -> list[str]:
    """One message per cart activity: summary + price + '👉 click here' + link.
    Sent as separate WhatsApp messages (joined with MESSAGE_SPLIT upstream)."""
    lang = state.language
    primary = state.mixed_display_currency

    def money(usd, cop, qty=1):
        # Round the per-person price first, then multiply, so the arithmetic
        # shown to the client always adds up (e.g. "2 × $126 = $252", never $251).
        if primary == "COP":
            return f"COP {int(round(cop or 0)) * qty:,}".replace(",", ".") if cop else None
        return f"${int(round(float(usd))) * qty} USD" if usd else None

    includes = (
        "✅ Incluye: transporte Cartagena-Islas-Cartagena, almuerzo, equipo y seguro."
        if lang == "es"
        else "✅ Includes: Cartagena-Islands transport, lunch, gear and insurance."
    )
    if state.location == "island":
        includes = (
            "✅ Incluye: equipo, seguro y acompañamiento de un profesional PADI (sin transporte desde Cartagena ni almuerzo)."
            if lang == "es"
            else "✅ Includes: gear, insurance and a PADI professional (no Cartagena transport or lunch)."
        )
    depart = (
        ("📍 Salida desde Cartagena (Muelle de la Bodeguita, 8:00 a.m.)." if lang == "es"
         else "📍 Departure from Cartagena (Muelle de la Bodeguita, 8:00 a.m.).")
        if state.location != "island"
        else ("📍 Recogida en tu hotel de las islas." if lang == "es" else "📍 Pickup at your island hotel.")
    )
    cta = ("👉 *Para más información y hacer tu reserva, haz clic aquí:*"
           if lang == "es" else "👉 *For more information and to book, click here:*")
    info_cta = ("ℹ️ Más información aquí:" if lang == "es" else "ℹ️ More information here:")
    wa = ("👉 Para reservar esto, dime y te paso con un asesor que coordina los detalles contigo."
          if lang == "es" else "👉 To book this, let me know and I'll connect you with an advisor who arranges the details with you.")

    msgs: list[str] = []
    for b in _cart_booking_blocks(state):
        qty = b["qty"]
        url = b["url"]
        # A direct booking checkout ("book.divingplanet.org") lets the client
        # pay online; a plain divingplanet.org page is info-only → book via WhatsApp.
        direct = bool(url) and "book.divingplanet.org" in url
        online = (" (reservando online)" if lang == "es" else " (online rate)") if direct else ""
        lines = [f"🤿 *{b['label']}*"]
        pp = money(b["usd"], b["cop"])
        if pp:
            if qty > 1:
                sub = money(b["usd"], b["cop"], qty)
                lines.append(f"💰 {qty} × {pp} p.p. = *{sub}*{online}")
            else:
                lines.append(
                    f"💰 *{pp}* por persona{online}" if lang == "es"
                    else f"💰 *{pp}* per person{online}"
                )
        if b.get("kind") == "course":
            # Multi-day PADI courses aren't the standard 8 a.m. day-tour: dates,
            # sessions and logistics are arranged with you, so skip the day-tour
            # "includes / 8 a.m. departure" boilerplate.
            lines.append(
                "📚 Curso PADI: las fechas, sesiones y detalles se coordinan contigo."
                if lang == "es"
                else "📚 PADI course: dates, sessions and details are arranged with you."
            )
        else:
            lines.append(includes)
            lines.append(depart)
        if b.get("note"):
            lines.append(b["note"])
        lines.append("")
        if direct:
            lines.extend([cta, url])
        elif url:
            lines.extend([info_cta, url, "", wa])
        else:
            lines.append(wa)
        msgs.append("\n".join(lines))
    return msgs


def _cart_booking_blocks(state: ConversationState) -> list[dict]:
    """One block per bookable activity in the cart (kids split into their real
    activity by age), each with price + booking URL — for the per-activity
    summary + link that closes the flow."""
    lang = state.language
    blocks: list[dict] = []

    def add(svc: dict, qty: int, label: str, url: str | None, note: str | None = None, kind: str = "day"):
        blocks.append({
            "label": label, "qty": qty,
            "usd": svc.get("price_usd"), "cop": svc.get("price_cop"), "url": url,
            "note": note, "kind": kind,
        })

    for item in state.mixed_cart:
        qty = item.get("qty", 0)
        it = item.get("type")
        if it == "refresh" or qty <= 0:
            continue
        if it == "beginner":
            beg = SERVICES.get(_cart_service_id("beginner", None, state)) or {}
            beg_name = beg.get(f"name_{lang}") or ("Minicurso de Buceo" if lang == "es" else "Dive Mini-Course")
            beg_url = _resolve_service_booking_url(beg, state)
            u8 = min(state.kids_under_8_count or 0, qty)
            e10 = min(state.kids_eight_to_ten_count or 0, max(0, qty - u8))
            if u8 > 0 or e10 > 0:
                adult = max(0, qty - u8 - e10)
                if adult > 0:
                    add(beg, adult, beg_name, beg_url)
                if u8 > 0:
                    snk = SERVICES.get(_service_for_location("snorkeling", state)) or {}
                    nm = (snk.get(f"name_{lang}") or "Snorkel") + (" [menores de 8]" if lang == "es" else " [under 8]")
                    u8_note = (
                        "_Los menores de 8 no pueden bucear; hacen snorkel (desde 6 años)._"
                        if lang == "es"
                        else "_Under 8 cannot dive; they snorkel instead (from age 6)._"
                    )
                    add(snk, u8, nm, _resolve_service_booking_url(snk, state), u8_note)
                if e10 > 0:
                    e10_note = (
                        "_Programa Bubble Makers (8-10 años), con supervisor especializado._"
                        if lang == "es"
                        else "_Bubble Makers program (ages 8-10), with a specialized supervisor._"
                    )
                    add(beg, e10, beg_name + " [Bubble Makers]", beg_url, e10_note)
                continue
            add(beg, qty, beg_name, beg_url)
            continue
        if it == "companion":
            blocks.append({
                "label": _cart_label_for(it, None, lang), "qty": qty,
                "usd": COMPANION_PRICE.get("usd_online"), "cop": COMPANION_PRICE.get("cop_online"), "url": None,
                "note": None, "kind": "day",
            })
            continue
        svc_id = _cart_service_id(it, item.get("plan"), state)
        svc = SERVICES.get(svc_id) or {}
        label = svc.get(f"name_{lang}") or item.get("label") or _cart_label_for(it, item.get("plan"), lang)
        url = None if _is_contact_only_service(svc_id) else _resolve_service_booking_url(svc, state)
        add(svc, qty, label, url, kind=("course" if it == "course" else "day"))
    return blocks


def _goto_mixed_final_summary(state: ConversationState) -> str:
    """Close the flow with ONE message per activity: summary + price + the
    booking link for that activity's web page (no cart/itinerary/payment
    buttons). Multiple activities → multiple separate messages."""
    lang = state.language
    msgs = _format_activity_booking_messages(state)
    state.quick_replies = []
    state.pending_lead_note_reason = "grupo mixto - resumen por actividad + links de reserva enviados"
    if not msgs:
        state.step = Step.ESCALATE
        state.pending_escalation_reason = "grupo mixto - cierre de reserva sin link directo"
        return (
            "¡Perfecto! Te paso con un asesor para cerrar los detalles de tu reserva. 🌊"
            if lang == "es"
            else "Perfect! I'll connect you with an advisor to finalize your booking. 🌊"
        )
    state.step = Step.FREE_TEXT
    # Keep a plain-text copy for the lead note / extra_context.
    state.mixed_last_summary = "\n\n———\n\n".join(msgs)
    # Cierre profesional tras los links (pedido del owner 2026-07-23): en vez
    # de una despedida pasiva, una PREGUNTA cálida que invita a seguir —
    # añadir otra actividad, resolver dudas o ajustar la reserva. Con varias
    # actividades es un único cierre al final de todos los mensajes (no uno
    # por actividad). Sin precios/links aquí: van en los `msgs` de arriba.
    closing = (
        "\n\n_El precio es el mismo en pesos (COP) o dólares (USD), sin cobro extra por la divisa._"
        "\n\n¿Te ayudo con algo más? Puedo *añadir otra actividad*, resolver dudas o "
        "ajustar la reserva. 🤿"
        if lang == "es"
        else "\n\n_The price is the same in COP or USD, with no extra charge for the currency._"
        "\n\nIs there anything else I can help you with? I can *add another activity*, "
        "answer questions, or adjust your booking. 🤿"
    )
    return MESSAGE_SPLIT.join(msgs) + closing


def _is_contact_only_service(service_id: str | None) -> bool:
    return service_id == "divemaster"


def _resolve_service_booking_url(service: dict, state: ConversationState) -> str | None:
    """Pick the right booking link for the service's catalog entry given location,
    localized to the conversation language (the catalog stores ?language=es)."""
    if state.location == "island" and service.get("booking_url_island"):
        url = service["booking_url_island"]
    else:
        url = service.get("booking_url")
    if url and state.language == "en":
        url = url.replace("language=es", "language=en")
    return url
