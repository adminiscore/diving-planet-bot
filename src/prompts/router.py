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

lat-11 (26-oct): la llamada LLM del enrutador se quitó (T2: con la duda decide Jev) y con ella su prompt de sistema
(`routing_system_prompt`, T6e). `ROUTING_TOOL` sigue siendo la definición de las señales: de ella salen las preguntas de
Jev (`jev_router`).
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
                        # ex-9b (19-oct): sin "none", el LLM que rellena todos los campos elegia uno a la fuerza
                        # ("the discount of 10% is not showing up" -> real_time_issues y cancellation). Jev ya
                        # tenia su "none" (routing_questions lo sobrescribe): sus preguntas no cambian.
                        "none",
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
                        "here. The same for a PRICE or DISCOUNT that looks "
                        "different from what the customer expected (the "
                        "online discount is already included in the web "
                        "price, there is no code): a pricing question, not "
                        "a failure. Do NOT use 'weather_conditions' for a "
                        "hypothetical or POLICY question about what happens "
                        "if the weather turns bad ('¿qué pasa si llueve ese "
                        "día?', '¿cuál es la política de cancelación por mal "
                        "clima?', 'what happens if it rains that day?') — "
                        "that is normal cancellation/rescheduling policy "
                        "information already known in the catalog, not a "
                        "request for today's/tomorrow's real forecast, and "
                        "must be left false here. Only set "
                        "'weather_conditions' for a LIVE forecast request "
                        "about a specific near-term day ('¿qué clima hace "
                        "mañana?', '¿va a llover hoy?', 'is it windy right "
                        "now?') that the bot genuinely cannot answer. Do NOT "
                        "use 'medical_questions' for a "
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
                        "actually being asked about. Merely MENTIONING a "
                        "near-term day ('mañana', 'amanhã', 'demain', "
                        "'tomorrow', 'tonight') is NOT enough by itself — a "
                        "message that mentions tomorrow while really asking "
                        "something else (a price in any language: 'quero "
                        "mergulhar amanhã, quanto custa?'; a flight/safety "
                        "question: 'tengo un vuelo mañana, puedo bucear "
                        "hoy?') must leave this field unset and let that "
                        "other topic be answered — do not let the day-word "
                        "alone flip it to true."
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
                        "wants_human), for giving THEIR own number, for "
                        "asking HOW or WHERE to book or pay ('do we book on "
                        "WhatsApp or on the website?'), or for the contact of "
                        "ANOTHER business such as a hotel ('¿me pasas el "
                        "contacto del hotel?') — those are information "
                        "questions. Asking us to SEND them something (the "
                        "link, the price, information) by WhatsApp or email "
                        "('¿me mandas el link por whatsapp?') is not asking "
                        "for a contact channel either. When unsure, leave it "
                        "false."
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
                    "enum": ["cancellation", "reschedule", "modify_headcount", "none"],
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

# gen-3 (20-oct, flag `dieta_no_es_medica`): "una de nosotras es celíaca, ¿qué puede comer?" salía como
# 'medical_questions' y pasaba a un asesor, aunque la base lo contesta (arroz con vegetales, puede traer su comida, avisar
# antes). La misma clase de exclusión que la discapacidad o los métodos de pago de arriba. El enrutador de respaldo y Jev
# (`jev_router.routing_questions`) leen esta descripción al importar: los dos llaman a `con_dieta_no_es_medica` con el
# flag (este módulo no lee la configuración).
_DIETA_NO_ES_MEDICA = (
    " Do NOT use 'medical_questions' for a DIET or FOOD question (celiac/gluten-free, vegetarian, vegan, lactose "
    "intolerance, a food allergy and what they can eat at lunch): that is the lunch/food policy, normal catalog "
    "information, and must be left 'none' here."
)


def con_dieta_no_es_medica(tool: dict) -> None:
    """Añade la exclusión de la dieta a la definición de `sensitive_topic` (una sola vez)."""
    prop = tool["function"]["parameters"]["properties"]["sensitive_topic"]
    if _DIETA_NO_ES_MEDICA not in prop["description"]:
        prop["description"] += _DIETA_NO_ES_MEDICA


