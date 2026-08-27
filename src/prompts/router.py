"""Prompts del nodo **router** (`src/orchestration/router.py`).

Una sola red: `escalation.detect_routing_signals` — UNA llamada por turno que
detecta las 9 señales de enrutado (quiere humano · menú/reiniciar · tema
sensible · discapacidad/DIVE TO HEAL · cancelar/reprogramar · pide contacto ·
link roto · disponibilidad · deliberación entre opciones). Es la única red
compartida por varios nodos **a propósito** (`docs/agent-arch-design.md` §7):
el router la computa una vez y cada nodo consume la señal que le toca, en vez
de que cada uno pregunte por su cuenta.

El *tool schema* es parte del prompt: la descripción de cada campo es lo que
instruye al modelo — sesgo "ante la duda, márcalo" en las señales sensibles
(escalar de más es más seguro), estricto en las explícitas (`wants_human`,
`booking_change_topic`). Se leen y se revisan juntos.
"""

from __future__ import annotations

# ── Señales de enrutado del turno · `escalation.detect_routing_signals` ─────

# ---------------------------------------------------------------------------
# Red de precisión LLM (auditoría 2026-07-22): los gates de arriba
# (SENSITIVE_RULES, ESCALATION_KEYWORDS en supervisor.py, MENU_KEYWORDS/
# BACK_KEYWORDS en supervisor.py, _ADAPTIVE_DIVING_PATTERN en supervisor.py)
# son listas cerradas de palabras exactas. Probado en vivo: "estoy
# embarazadita", "soy epiléptica", "tengo una condición cardiaca" (femenino),
# "ataque de pánico" (médico) y "perdí una pierna", "uso prótesis", "tengo
# párkinson", "lesión medular", "soy sordomuda", "no vidente" (discapacidad/
# DIVE TO HEAL, auditoría 2026-07-23) — NINGUNA se detectaba, pese a ser
# justo el tipo de caso que estos gates existen para atrapar.
# A diferencia del extractor de reserva (donde abstenerse es más seguro que
# inventar), aquí el sesgo correcto es el CONTRARIO para sensitive_topic y
# adaptive_diving_topic: mejor escalar/enrutar de más que de menos — no
# detectar una emergencia real o una necesidad de accesibilidad cuesta mucho
# más que un falso positivo. Nunca REEMPLAZA las listas (que siguen siendo el
# camino gratis para los casos claros); es una red que solo se llama cuando
# esas listas no encontraron nada.
ROUTING_TOOL = {
    "type": "function",
    "function": {
        "name": "detect_routing_signals",
        "description": (
            "Classify a customer message for a scuba booking bot for 9 "
            "safety/routing signals, in ANY regional Spanish or English "
            "phrasing, slang, or diminutive form — not just the exact "
            "clinical/formal wording. Bias applies to sensitive_topic, "
            "adaptive_diving_topic, broken_link_complaint AND "
            "availability_question: when genuinely unsure whether a MEDICAL/"
            "weather/real-time/complaint issue, a DISABILITY/accessibility "
            "topic, a BROKEN link/page/payment, or an AVAILABILITY/spots "
            "question applies, still set it — missing a real one is worse "
            "than a false positive. wants_human, wants_menu_or_restart, "
            "booking_change_topic and asks_for_contact_number are the "
            "OPPOSITE: be STRICT, only set them on an explicit request (see "
            "their descriptions) — a normal booking message must never be "
            "misread as one."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "wants_human": {
                    "type": "boolean",
                    "description": (
                        "True ONLY if the customer EXPLICITLY asks to talk to "
                        "a human / real person / agent / advisor instead of the "
                        "bot ('quiero hablar con alguien', 'pásame con un "
                        "asesor', 'can I talk to a real person'). A message that "
                        "merely describes their booking — companions, group, "
                        "activities, plan, or a normal question ('tengo un amigo "
                        "que quiere bucear', 'somos 3', 'y uno hace snorkel') — "
                        "is NOT a request for a human. When unsure, leave it "
                        "false; another layer handles the booking."
                    ),
                },
                "wants_menu_or_restart": {
                    "type": "boolean",
                    "description": (
                        "True if the customer wants to go back to a "
                        "previous step, see the menu of options, or start "
                        "over."
                    ),
                },
                "sensitive_topic": {
                    "type": "string",
                    "enum": [
                        "medical_questions", "weather_conditions",
                        "real_time_issues", "complaints_or_emergencies",
                    ],
                    "description": (
                        "Set if the message raises a MEDICAL condition or "
                        "concern (pregnancy, heart/cardiac/respiratory/"
                        "psychiatric conditions, panic attacks, epilepsy, "
                        "surgery, medication...), a WEATHER-dependent "
                        "question, a REAL-TIME availability/payment "
                        "PROBLEM (something actively failing right now: "
                        "'no me deja pagar', 'the payment page crashes', "
                        "'error al reservar'), or a COMPLAINT/emergency/"
                        "fraud accusation. Do NOT use 'real_time_issues' for "
                        "a general, nothing-is-broken question about "
                        "payment METHODS ('qué métodos de pago aceptan', "
                        "'puedo pagar con tarjeta', 'what payment methods do "
                        "you take') — that is normal catalog information, "
                        "not a real-time problem, and must be left false "
                        "here. Do NOT use 'medical_questions' for a "
                        "DISABILITY or accessibility topic (amputation, "
                        "prosthetic limb, wheelchair, blindness/deafness, "
                        "paralysis, reduced mobility, Down syndrome, "
                        "autism...) — those go in `adaptive_diving_topic` "
                        "instead, never both."
                    ),
                },
                "adaptive_diving_topic": {
                    "type": "boolean",
                    "description": (
                        "True if the message raises a DISABILITY or "
                        "accessibility topic in the context of diving — "
                        "amputation, missing limb, prosthetic/prótesis, "
                        "wheelchair, paralysis (parálisis, lesión medular), "
                        "blindness/low vision ('no vidente', invidente, "
                        "ciego), deafness ('sordomuda', sordo), Down "
                        "syndrome, autism, Parkinson's, cerebral palsy, "
                        "reduced mobility, or asking whether someone with a "
                        "disability can dive — in ANY regional phrasing, "
                        "even if it doesn't use the word 'discapacidad' "
                        "itself. This routes to the DIVE TO HEAL adaptive-"
                        "diving program, NOT a medical escalation — never "
                        "also set `sensitive_topic` for the same message."
                    ),
                },
                "availability_question": {
                    "type": "boolean",
                    "description": (
                        "True if the customer asks whether there is SPACE / "
                        "SPOTS / AVAILABILITY / cupo / lugar for a specific "
                        "day or date, in any phrasing ('¿hay cupo para "
                        "mañana?', '¿tienen disponibilidad el sábado?', "
                        "'¿queda espacio el domingo?', '¿puedo ir el 20?', "
                        "'do you have availability this weekend?', 'any spots "
                        "left for Saturday?'). The bot CANNOT see the live "
                        "calendar, so these must be routed — bias toward "
                        "catching (better to route than to invent a 'yes, we "
                        "have space'). Do NOT set it for a general question "
                        "about the schedule/what days you operate that "
                        "doesn't ask to confirm a specific slot. CRITICAL — "
                        "do NOT confuse this with a PRICE question: 'cuánto "
                        "es el snorkel en pesos colombianos?' / 'cuánto "
                        "cuesta el buceo?' / 'how much is snorkeling?' ask "
                        "for a COST, not a date/slot — 'cuánto' ('how much') "
                        "is not 'cuándo' ('when'); leave this field unset "
                        "for those, even though both start with 'cuánto'/"
                        "'how much'. Only set it when a DATE or TIME slot is "
                        "actually being asked about."
                    ),
                },
                "broken_link_complaint": {
                    "type": "boolean",
                    "description": (
                        "True if the customer reports that a LINK, booking "
                        "page, payment page, button or form the bot/team sent "
                        "is BROKEN or not working — won't open, won't load, "
                        "blank page, crashes, throws an error, dead link, "
                        "button does nothing, goes nowhere, in any phrasing "
                        "('el link no me deja pagar', 'me sale página en "
                        "blanco', 'le doy al botón y no pasa nada', 'the "
                        "payment page crashes', 'your booking link is dead'). "
                        "This is a technical failure to FIX, not a general "
                        "question — do NOT set it for 'no me funciona el buceo "
                        "nocturno?' (that's a normal question about an "
                        "activity, not a broken link). Do NOT set it for a "
                        "TRUST/security question about the link ('¿el link de "
                        "pago es seguro?', 'is the payment link safe?', 'is "
                        "this legit?') — nothing is reported as failing there, "
                        "the customer is only asking whether it's safe to "
                        "click, which is a normal reassurance question, not a "
                        "complaint."
                    ),
                },
                "asks_for_contact_number": {
                    "type": "boolean",
                    "description": (
                        "True ONLY if the customer is asking for a direct "
                        "contact channel to reach the business OUTSIDE this "
                        "chat — a phone number, WhatsApp number, a line to "
                        "call, or an email — in any phrasing ('¿me pasas un "
                        "número?', 'tienen WhatsApp?', '¿cómo los contacto?', "
                        "'a number to call you', 'how can I reach you'). Do "
                        "NOT set it for a normal booking message, for asking "
                        "to talk to a human IN this chat (that is "
                        "wants_human), or for giving THEIR own number. When "
                        "unsure, leave it false."
                    ),
                },
                "comparing_options": {
                    "type": "object",
                    "properties": {
                        "comparing": {
                            "type": "boolean",
                            "description": (
                                "True ONLY if the customer is WEIGHING two or "
                                "more of our activities WITHOUT having decided "
                                "— undecided, comparing, or asking which to "
                                "pick ('no sé si buceo o minicurso', 'mi pareja "
                                "duda entre snorkel y buceo', 'cuál me "
                                "conviene', 'torn between diving and "
                                "snorkeling'). It is NOT comparing when they "
                                "clearly SELECT one ('quiero el minicurso') or "
                                "clearly want BOTH as a real booking ('quiero "
                                "buceo y snorkel para los dos'). Needs 2+ "
                                "distinct activities in play; a single activity "
                                "is never 'comparing'."
                            ),
                        },
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    "certified_diving", "minicourse",
                                    "snorkel", "padi_course",
                                ],
                            },
                            "description": (
                                "The activities being weighed, only if "
                                "comparing is true. Use certified_diving for "
                                "scuba diving as a certified diver, minicourse "
                                "for the first-time discover-scuba, snorkel, or "
                                "padi_course for a full PADI certification "
                                "course."
                            ),
                        },
                        "who": {
                            "type": "string",
                            "enum": ["self", "companion", "unspecified"],
                            "description": (
                                "Who is undecided: 'self' (the person "
                                "writing), 'companion' (a partner/friend/"
                                "relative they mention), or 'unspecified'."
                            ),
                        },
                    },
                    "description": (
                        "Set when the customer is DELIBERATING between two or "
                        "more of our activities instead of selecting or "
                        "booking — they want help deciding / an explanation of "
                        "the difference, not a booking. Leave unset for a plain "
                        "selection, a real multi-activity booking, or a "
                        "single-activity message."
                    ),
                },
                "booking_change_topic": {
                    "type": "string",
                    "enum": ["cancellation", "reschedule", "modify_headcount"],
                    "description": (
                        "Set ONLY when the customer clearly wants to CANCEL, "
                        "CHANGE THE DATE, or CHANGE THE NUMBER OF PEOPLE of "
                        "an EXISTING booking of theirs, in any regional "
                        "phrasing, slang, typo, or indirect wording — "
                        "'cancellation' for cancelling/backing out/not being "
                        "able to come ('ya no puedo ir', 'me surgió un "
                        "imprevisto y no puedo asistir', 'quiero echar para "
                        "atrás la reserva', 'dar de baja', 'bórrame del buceo', "
                        "\"i can't make it anymore\", 'take me off the "
                        "booking'); 'reschedule' for moving it to another day "
                        "('mover mi reserva', 'pasar el buceo para otro día', "
                        "'correr la fecha', 'posponerlo', 'push it to "
                        "another day'); 'modify_headcount' for adding or "
                        "removing people from a booking that ALREADY EXISTS "
                        "('ya tengo una reserva hecha, quiero agregar una "
                        "persona más', 'somos uno más de los que reservé', "
                        "'quiero quitar a alguien de mi reserva', 'add "
                        "someone to my existing booking', 'we're one more "
                        "than what I booked'). STRICT: do NOT set it for a "
                        "general question ABOUT the cancellation/refund "
                        "policy ('¿cuál es la política de cancelación?', 'si "
                        "cancelo me devuelven?'), nor for the bare word "
                        "'cancelar'/'cancel'/'atrás'/'volver' used to "
                        "navigate the menu (that is menu/back, not a booking "
                        "change), nor for stating a group size while a "
                        "booking is still being CREATED right now (that is "
                        "normal booking info, not 'modify_headcount' — this "
                        "signal is ONLY about a booking that already exists). "
                        "When unsure, leave it unset."
                    ),
                },
            },
        },
    },
}


def routing_system_prompt(lang: str) -> str:
    if lang == "es":
        return (
            "Eres una capa de seguridad para un bot de buceo. Las listas de "
            "palabras clave del bot no encontraron nada en este mensaje — tu "
            "única tarea es revisar si, en CUALQUIER forma regional de "
            "decirlo (México, Colombia, Chile, Argentina, España...), el "
            "mensaje (1) pide hablar con una persona humana, (2) pide volver "
            "al menú o reiniciar, (3) menciona un tema médico, del clima, "
            "de disponibilidad/pago en tiempo real, o una queja/emergencia/"
            "estafa, o (4) menciona una discapacidad o tema de accesibilidad "
            "(amputación, prótesis, silla de ruedas, ceguera/sordera, "
            "párkinson, parálisis, síndrome de Down, autismo...) en relación "
            "al buceo — esto va a `adaptive_diving_topic`, NUNCA junto con "
            "sensitive_topic, o (5) quiere CANCELAR, CAMBIAR LA FECHA o "
            "CAMBIAR EL NÚMERO DE PERSONAS de una reserva que YA tiene "
            "(booking_change_topic) — 'cancellation', 'reschedule' o "
            "'modify_headcount'. IMPORTANTE: el sesgo de 'ante la duda, márcalo' "
            "vale para sensitive_topic Y adaptive_diving_topic (mejor "
            "escalar/enrutar de más). wants_human, wants_menu_or_restart y "
            "booking_change_topic son lo contrario: márcalos SOLO si el "
            "cliente lo pide explícitamente; un mensaje normal de reserva "
            "(acompañantes, grupo, actividades) NUNCA es wants_human, y una "
            "PREGUNTA por la política de cancelación NO es booking_change_topic. "
            "(6) si pide un número de teléfono/WhatsApp/correo o una vía de "
            "contacto FUERA de este chat → asks_for_contact_number (también "
            "estricto), (7) reporta que un LINK/página/pago/botón NO "
            "funciona (roto, en blanco, da error) → broken_link_complaint, "
            "(8) pregunta si hay cupo/espacio/disponibilidad para un día "
            "concreto → availability_question (ambos con el sesgo de 'ante la "
            "duda, márcalo'), o (9) está DUDANDO entre 2+ de nuestras "
            "actividades sin decidirse (comparando, indeciso, pidiendo cuál "
            "elegir) → comparing_options; NO lo marques si elige una sola o "
            "quiere varias como reserva real. Llama a `detect_routing_signals`."
        )
    return (
        "You are a safety layer for a scuba diving bot. The bot's keyword "
        "lists found nothing in this message — your only job is to check "
        "whether, in ANY regional way of phrasing it, the message (1) asks "
        "to talk to a human, (2) asks to go back to the menu or restart, "
        "(3) raises a medical, weather, real-time availability/payment, or "
        "complaint/emergency/fraud topic, or (4) raises a disability or "
        "accessibility topic (amputation, prosthetic, wheelchair, blindness/"
        "deafness, Parkinson's, paralysis, Down syndrome, autism...) in "
        "relation to diving — that goes in `adaptive_diving_topic`, NEVER "
        "together with sensitive_topic, or (5) wants to CANCEL, CHANGE THE "
        "DATE, or CHANGE THE HEADCOUNT of a booking they ALREADY have "
        "(booking_change_topic — 'cancellation', 'reschedule' or "
        "'modify_headcount'). IMPORTANT: the 'when unsure, flag "
        "it' bias applies to BOTH sensitive_topic and adaptive_diving_topic "
        "(better to over-escalate/over-route). wants_human, "
        "wants_menu_or_restart and booking_change_topic are the opposite: "
        "flag them ONLY on an explicit request; a normal booking message "
        "(companions, group, activities) is NEVER wants_human, and a "
        "QUESTION about the cancellation policy is NOT booking_change_topic. "
        "(6) if they ask for a phone/WhatsApp/email or a contact channel "
        "OUTSIDE this chat → asks_for_contact_number (also strict), (7) "
        "report that a LINK/page/payment/button is NOT working (broken, "
        "blank, error) → broken_link_complaint, (8) ask whether there is "
        "space/spots/availability for a specific day → availability_question "
        "(both with the 'when unsure, flag it' bias), or (9) are DELIBERATING "
        "between 2+ of our activities without deciding (comparing, undecided, "
        "asking which to pick) → comparing_options; do NOT flag it for a "
        "single selection or a real multi-activity booking. Call "
        "`detect_routing_signals`."
    )
