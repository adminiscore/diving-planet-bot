"""El contexto del estado que se le pasa al RAG (`_build_extra_context`): lo que ya sabemos del cliente, para que
no repregunte ni contradiga. Lo usan el nodo `info` y el núcleo (`conversational_core._entradas_rag`), siempre a
través de `supervisor._build_extra_context`.

s4-2 (19-oct): movido tal cual desde `supervisor.py`, que lo re-exporta. Ver `src/agents/rutas/__init__.py`.
"""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.config import settings
from src.flows import cart_render, eligibility
from src.flows.state import ConversationState, Step

# Cliente aclarando explicitamente que, dentro de una conversacion DIVE TO
# HEAL, la pregunta actual es sobre el programa NORMAL/no adaptado -- ver
# _build_extra_context, hallazgo en vivo 2026-09-02 (lote 9).
_DIVE_TO_HEAL_OVERRIDE_RE = re.compile(
    r"programa\s+(?:normal|regular|est[aá]ndar)|"
    r"sin\s+adaptar|no\s+adaptad[oa]|buceo\s+normal|"
    r"regular\s+program|standard\s+program|non[- ]adaptive|without\s+adapt",
    re.IGNORECASE,
)

# Nota de Fase C ("X no es buzo certificado"/"no está certificado"/"nunca ha
# buceado") sobre un acompañante -- dispara el recordatorio de que un
# minicurso no certifica a nadie, ver _build_extra_context, hallazgo en vivo
# 2026-09-02 (conv. real 831). "Nunca ha buceado" añadido tras el lote 12
# (bateria "natural/deictica", conv. 852): la nota real capturada para un
# tercer perfil del grupo ("mi primo nunca ha buceado") no matcheaba el
# regex original (solo cubria "no es/está certificado"), y el LLM conflado
# a esa persona con el buzo certificado del grupo ("tú y tu primo se unen a
# ella en las inmersiones").
# Decisión deliberada (inventario regex, 2026-09-03): NO se unifica con
# `intent_detector.certification_claim()` aunque ambas respondan "¿el texto
# dice que alguien esta/no esta certificado?" — este regex opera sobre NOTAS
# parafraseadas por LLM (`capture_notes`), no sobre el mensaje crudo del
# cliente. Ese dominio es genuinamente distinto (frases no controladas por
# nosotros, variables de corrida en corrida) y ya se endureció HOY mismo con
# 2 iteraciones de depuración en vivo real (caso "certificado-pero-inactivo",
# ver docs/robustness/progress-log.md Fase 9). Fusionarlo con el vocabulario
# de mensajes crudos arriesgaría romper ese ajuste fino sin necesidad real.
_UNCERTIFIED_COMPANION_NOTE_RE = re.compile(
    r"no\s+(?:es|est[aá])\s+(?:buzo\s+)?certificad[oa]|"
    r"sin\s+certificar|no\s+tiene\s+certificaci[oó]n|"
    r"nunca\s+ha\s+bucead|nunca\s+bucead|never\s+(?:been\s+)?div(?:ed|ing)|"
    r"not\s+certified|isn'?t\s+certified|no\s+certification",
    re.IGNORECASE,
)

# Nota de Fase C sobre un acompañante que SÍ está certificado pero lleva
# tiempo sin bucear ("se certificó hace 8 años y no ha vuelto a bucear") --
# hallazgo en vivo (lote 12, 2026-09-02, conv. real 856): sin esta regla, el
# LLM confundió "inactivo hace tiempo" con "nunca certificado" y le dijo al
# cliente que su amigo (SÍ certificado) "no podrá unirse... necesita estar
# certificado" y debía hacer un minicurso -- ademas `capture_notes` capturó
# esa conclusión errónea como una nota nueva ("amigo no tiene certificación
# de buceo"), reforzando el error en turnos siguientes. Alguien certificado
# e inactivo necesita el REFRESHER (ya cubierto en el flujo normal si han
# pasado más de 2 años), NO un minicurso -- son productos distintos con
# elegibilidad distinta.
# Hallazgo en vivo, 2ª iteración (2026-09-02, reverificando en vivo el fix de
# arriba tras desplegarlo, mismo repro de la conv. 856): la primera version
# exigia "certificado" y la frase de inactividad EN LA MISMA nota, a <=40
# caracteres -- pero `capture_notes` (LLM, no determinista) parafraseo el
# mismo mensaje de forma distinta en la repeticion en vivo ("amigo no ha
# buceado en 8 años", SIN mencionar "certificado" en absoluto), y el guard
# no disparo -- la alucinacion volvio a pasar en vivo. Separado en dos
# regex de co-ocurrencia (no exigen proximidad ni la misma nota) para no
# depender de que el extractor de notas preserve ambos hechos juntos.
_INACTIVE_MENTION_RE = re.compile(
    # "bucea\w*" cubre buceado/buceando Y el infinitivo "bucear" (la forma
    # gramaticalmente correcta tras "a": "no ha vuelto A bucear") -- el
    # lexema "bucead" original solo cubria las dos primeras formas y no
    # disparaba nunca para la frase exacta del repro del lote 12 (hallazgo
    # en vivo, 2026-09-03: la regla de negocio nunca se inyectaba con esta
    # frase, asi que la nueva guarda post-respuesta tampoco podia activarse).
    r"no\s+ha\s+(?:vuelto\s+a\s+)?bucea\w*|hace\s+\d+\s*a[ñn]os?\s+que\s+no\s+bucea|"
    r"no\s+bucea\s+desde|tanto\s+tiempo\s+sin\s+bucear|"
    r"hasn'?t\s+(?:been\s+)?div(?:ed|ing)",
    re.IGNORECASE,
)
# Lexema completo "certific*" (no solo "certificad[oa]"): "se certificó hace
# 8 años" (verbo, tiempo pasado) no matcheaba la version anterior -- solo
# cubria la forma adjetivo/participio ("es/está certificado"), no la forma
# verbo ("se certificó"/"certificarse"). Encontrado verificando en vivo esta
# misma correccion (ver docstring de _mentions_inactive_but_certified_companion).
_CERTIFIED_MENTION_RE = re.compile(r"certific\w*|certified", re.IGNORECASE)


def _mentions_inactive_but_certified_companion(text: str) -> bool:
    """True si el texto (notas + mensajes del cliente) menciona a alguien
    certificado en algun punto Y menciona inactividad prolongada en algun
    punto -- sin exigir que ambos esten en la MISMA frase (ver el hallazgo
    de arriba). No dispara si el texto tambien dice explicitamente que la
    persona NO esta certificada (esa es la regla anterior, distinta)."""
    return bool(
        _INACTIVE_MENTION_RE.search(text)
        and _CERTIFIED_MENTION_RE.search(text)
        and not _UNCERTIFIED_COMPANION_NOTE_RE.search(text)
    )


def _build_extra_context(state: ConversationState) -> str | None:
    """Build a compact natural-language summary of the current state to help RAG.

    Called before EVERY rag_answer(...) in this file — no matter where in the
    tree the free-text question was asked, the LLM gets everything we already
    know about the client so it never re-asks or contradicts it:
    - Idioma de la conversacion
    - Ubicacion (Cartagena / isla / hotel)
    - Actividad activa: seleccionada en el arbol O en previsualizacion del
      carrito sin confirmar, con su "incluye"/"no incluye" real (ground truth,
      no depende de que la busqueda vectorial acierte el chunk)
    - Si es buzo certificado, colombiano, inactivo >2 anios, interes en refresher
    - Tamano de grupo (detectado o pendiente de confirmar), duracion (1 dia vs
      varios), menores de edad ya contabilizados, lancha privada
    - Carrito actual completo, con ground truth de incluye/no incluye por item
    - Paso actual del flujo guiado
    """

    parts: list[str] = []

    # Fecha/hora real (Colombia) — sin esto el LLM no tiene forma de saber si
    # un corte de horario ("cierra a las 4:30 PM del día anterior") ya pasó o
    # no, y termina inventando urgencia/cierre que no puede verificar.
    now = datetime.now(ZoneInfo("America/Bogota"))
    # arq-4b (G10 nº 4, g10-036): «mañana, jueves 23 de octubre» un jueves 22: el modelo calculaba mal el día de la
    # semana. Se le da el de hoy y el de mañana (las dos fechas que más se nombran).
    manana = now + timedelta(days=1)
    if state.language == "es":
        dias = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
        parts.append(f"Fecha y hora actual: {dias[now.weekday()]} {now.strftime('%Y-%m-%d %H:%M')} (hora de "
                     f"Cartagena/Colombia; mañana es {dias[manana.weekday()]} {manana.strftime('%Y-%m-%d')}).")
    else:
        parts.append(f"Current date and time: {now.strftime('%A %Y-%m-%d %H:%M')} (Cartagena/Colombia time; "
                     f"tomorrow is {manana.strftime('%A %Y-%m-%d')}).")

    # Idioma actual de la conversación
    if state.language == "es":
        parts.append("La conversación se esta llevando a cabo en español.")
    elif state.language == "en":
        parts.append("The conversation is currently happening in English.")

    # DIVE TO HEAL (buceo adaptado) — hallazgo en vivo (2026-09-01, Gadea, lote 7,
    # docs/multi-agent-refactor-plan.md §7): `rag_answer` busca el KB con el texto
    # literal del mensaje, y si encuentra un doc generico confiable (p.ej. "que
    # incluye el tour" -> paquete estandar de 2 inmersiones), ese doc ganaba
    # SIEMPRE aunque la conversacion estuviera en contexto DIVE TO HEAL, porque
    # `extra_context` no decia nada sobre ese contexto (solo se usaba para el
    # escape hatch "sin docs confiables") y el propio extra_context tampoco
    # llevaba esta senal. Sin ella, un seguimiento generico ("cuantas
    # inmersiones son") respondia con datos de un paquete normal sin mencionar
    # el programa adaptado. Esto no cambia la prioridad KB-vs-contexto: sigue
    # ganando el doc mas confiable, pero ahora el LLM sabe que debe interpretar
    # preguntas de seguimiento ambiguas dentro de DIVE TO HEAL en vez de tomar
    # al pie de la letra un dato de un paquete estandar no adaptado.
    # Hallazgo en vivo (2026-09-02, lote 9): confiar en que el LLM detecte el
    # override "en realidad quiero el programa normal" DENTRO del propio
    # parrafo de instruccion (la ultima frase de arriba) no funciono de forma
    # fiable -- verificado en vivo contra PRE (conversacion 782/792): la
    # aclaracion explicita seguia cayendo al fallback "no lo tengo a la mano"
    # en vez de responder con la info generica del paquete, y en la traza de
    # LangSmith la respuesta SI se generaba con datos de paquete pero el juez
    # de grounding la rechazaba (HALLUCINATED) las 2 veces -- probablemente
    # porque el propio texto de la nota DIVE TO HEAL seguia presente y sesgaba
    # la generacion hacia mezclar ambos contextos. Fix determinista (mismo
    # patron que las guardas de §6.bis: verificar el TEXTO del turno, no
    # confiar en que el LLM se autocorrija): si el ultimo mensaje del cliente
    # trae la aclaracion explicita, la nota NO se añade en absoluto para este
    # turno -- RAG responde con el KB normal, sin el sesgo de la nota. Esto no
    # toca el flag persistido `adaptive_diving_context` (sigue en pie por si
    # el cliente vuelve a preguntar por DIVE TO HEAL despues).
    last_user_message = next(
        (h.get("content", "") for h in reversed(state.history or []) if h.get("role") == "user"), ""
    )
    dive_to_heal_override = bool(_DIVE_TO_HEAL_OVERRIDE_RE.search(last_user_message))

    if getattr(state, "adaptive_diving_context", False) and not dive_to_heal_override:
        if state.language == "es":
            parts.append(
                "La conversacion esta dentro del programa DIVE TO HEAL (buceo adaptado para "
                "personas con discapacidad). Si el cliente hace una pregunta generica de "
                "seguimiento (numero de inmersiones, duracion, itinerario, que incluye, etc.) "
                "sin pedir explicitamente el programa normal/no adaptado, interpreta esa "
                "pregunta DENTRO de DIVE TO HEAL: esos detalles logisticos se coordinan caso a "
                "caso con el equipo segun la condicion de la persona, no son un numero fijo de "
                "un paquete estandar. NO respondas con datos de un paquete generico (p.ej. "
                "\"incluye 2 inmersiones\") como si aplicaran automaticamente al buceo adaptado; "
                "en su lugar, explica que esos detalles se ajustan con el equipo segun el caso. "
                "Si el cliente aclara que ahora pregunta por el programa normal (no adaptado), "
                "si puedes usar la informacion generica del paquete."
            )
        else:
            parts.append(
                "This conversation is happening within the DIVE TO HEAL program (adaptive "
                "diving for people with disabilities). If the customer asks a generic "
                "follow-up question (number of dives, duration, itinerary, what's included, "
                "etc.) without explicitly asking about the regular/non-adaptive program, "
                "interpret that question WITHIN DIVE TO HEAL: those logistics are coordinated "
                "case by case with the team based on the person's condition, not a fixed number "
                "from a standard package. Do NOT answer with generic package data (e.g. "
                "\"includes 2 dives\") as if it automatically applied to adaptive diving; "
                "instead, explain that those details are worked out with the team per case. "
                "If the customer clarifies they're now asking about the regular (non-adaptive) "
                "program, you can use the generic package information."
            )

    # CAL (17-oct, flag `contexto_tras_el_pase`): la conversación YA está con una persona del equipo. Tras un pase,
    # un "gracias" recibía una respuesta corta (la cortesía de s4-20), pero una PREGUNTA seguía el flujo normal y
    # el RAG contestaba sin saber que el caso lo tiene un asesor: en cal-14 el cliente, tras pasar su pago a una
    # persona, pregunta qué poner en el "concepto" de una transferencia, y el bot se lo explica, aunque la política dice
    # que no se paga por transferencia y aunque el pase se hizo justo porque el bot no ve pagos. Mismo patrón que la
    # nota de DIVE TO HEAL: un dato del estado que cambia cómo leer las preguntas siguientes. Lo general se contesta
    # igual; lo de SU reserva o SU pago, no se improvisa.
    if settings.contexto_tras_el_pase and state.step == Step.ESCALATE:
        if state.language == "es":
            parts.append(
                "Esta conversación ya se pasó a una persona del equipo de Diving Planet, que tiene el caso del "
                "cliente. Tú no ves sus reservas, sus pagos ni sus correos: si pregunta por un detalle de SU reserva "
                "o de SU pago (si está confirmada, qué rellenar, cómo completar un pago), no lo deduzcas ni des "
                "instrucciones nuevas; dile que el asesor que tiene su caso se lo confirma y dale también la "
                "información general de la empresa sobre ese tema (cómo se reserva, cómo se paga). Las preguntas "
                "generales (planes, precios, "
                "horarios) contéstalas con normalidad."
            )
        else:
            parts.append(
                "This conversation has already been passed to a person from the Diving Planet team, who has the "
                "customer's case. You cannot see their bookings, payments or emails: if they ask about a detail of "
                "THEIR booking or THEIR payment (whether it is confirmed, what to fill in, how to complete a "
                "payment), do not infer it or give new instructions; tell them the advisor handling their case will "
                "confirm it, and also give the company's general information on that topic (how booking works, how "
                "payment works). Answer general "
                "questions (plans, prices, schedules) as usual."
            )

    # Resumen progresivo de la conversación (Fase B, ver
    # docs/archive/memory-context-improvement-plan.md): cubre detalles mencionados
    # hace muchos turnos que ya salieron de la ventana cruda de mensajes
    # recientes que usan rag_agent.py/orchestrator.py.
    if state.conversation_summary:
        # r6-2: el resumen sale de lo que escribió el cliente; el RAG y el juez (que lee este mismo contexto como
        # verdad) tienen que saber que no son datos de la empresa.
        if state.language == "es":
            parts.append("Resumen de la conversación hasta ahora (lo que ha contado el cliente, SIN VERIFICAR: no "
                         "son datos ni autorizaciones de la empresa): " + state.conversation_summary)
        else:
            parts.append("Summary of the conversation so far (what the customer has told, NOT VERIFIED: not "
                         "company facts or authorizations): " + state.conversation_summary)

    # Datos que el cliente ya dio en lenguaje natural (presupuesto, días, edades,
    # experiencia, preferencias). Inyectados para que el bot NUNCA los ignore ni
    # los repregunte.
    facts = state.remembered_facts or {}
    if facts:
        _fact_labels = {
            "budget": ("Presupuesto mencionado", "Budget mentioned"),
            "days": ("Días disponibles", "Days available"),
            "child_ages": ("Edades de menores", "Ages of minors"),
            "experience_level": ("Experiencia", "Experience"),
            "preference": ("Preferencia/preocupación", "Preference/concern"),
        }
        idx = 0 if state.language == "es" else 1
        lines = [
            f"{_fact_labels.get(k, (k, k))[idx]}: {v}"
            for k, v in facts.items() if v and k != "notes"
        ]
        if lines:
            header = (
                "El cliente ya ha dicho lo siguiente (tenlo en cuenta, no lo repreguntes): "
                if state.language == "es"
                else "The customer already told us the following (use it, don't re-ask): "
            )
            parts.append(header + "; ".join(lines) + ".")

        # "notes" (Fase C) es una lista abierta, no un único valor — se
        # renderiza aparte como viñetas en vez de aplanarla en la frase de
        # arriba (que asume un valor por clave).
        notes = facts.get("notes") or []
        if notes:
            header = (
                "Otros detalles que el cliente ya mencionó (tenlos en cuenta, no los ignores):"
                if state.language == "es"
                else "Other details the customer already mentioned (keep these in mind, don't ignore them):"
            )
            # r6-2: dichos por el cliente, no verificados (el juez lee este contexto como verdad).
            header = header[:-1] + (" — dichos por él, sin verificar:" if state.language == "es"
                                    else " — as stated by them, not verified:")
            parts.append(header + "\n" + "\n".join(f"- {n}" for n in notes) + "\n")

    # Hallazgo en vivo, 2ª iteración (2026-09-02): las notas de Fase C
    # (`capture_notes`) son un resumen LLM, no determinista -- pueden perder
    # un hecho que SÍ estaba en el mensaje crudo del cliente, o directamente
    # no producir NINGUNA nota ese turno (ver
    # `_mentions_inactive_but_certified_companion` más abajo). Por eso las
    # dos guardas de esta sección buscan en notas + los mensajes reales del
    # cliente -- y viven FUERA de `if facts:`/`if notes:` (hallazgo en vivo,
    # 3ª iteración, 2026-09-03: cuando `remembered_facts` es None/vacío o
    # `capture_notes` no genera ninguna nota, este bloque quedaba anidado
    # dentro de esos `if` y nunca se evaluaba, aunque el hecho completo
    # siguiera en `state.history`).
    companion_notes = (state.remembered_facts or {}).get("notes") or []
    user_messages_text = " ".join(
        h.get("content", "") for h in (state.history or []) if h.get("role") == "user"
    )
    companion_search_text = " ".join(companion_notes) + " " + user_messages_text
    nota_sin_certificar = bool(_UNCERTIFIED_COMPANION_NOTE_RE.search(companion_search_text))
    nota_certificado_inactivo = _mentions_inactive_but_certified_companion(companion_search_text)
    if not state.extractor_ha_fallado:
        # ex-9b paso 6: las dos reglas salen del ESTADO, que llena el extractor con cita: OTRA persona del grupo no está
        # certificada (`acompanante_sin_certificar`) o lo está pero lleva tiempo sin bucear
        # (`acompanante_certificado_inactivo`). El regex leía todo lo que escribió el cliente y las notas del LLM de
        # notas: "no ha buceado" de cualquier cosa contaba, y "no estoy certificado" de quien escribe, según el idioma.
        # Lo de quien escribe ya va arriba (`is_certified`, `last_dive_over_2_years`). Si el extractor no leyó algún
        # mensaje de la conversación, el regex de siempre (solo si la IA calla).
        nota_sin_certificar = state.acompanante_sin_certificar
        nota_certificado_inactivo = state.acompanante_certificado_inactivo

    # Hallazgo en vivo (conversación real 831, 2026-09-02): con una
    # nota tipo "novia no es buzo certificado" ya en el contexto, el
    # LLM igual confirmó que ella podría "bucear junto con él" al día
    # siguiente del minicurso — contradice
    # policies.json["packages_certification_requirement"] ("los
    # paquetes de 5/7/9 buceos son EXCLUSIVAMENTE para certificados").
    # El juez de grounding no lo atrapó (GROUNDED a la primera): no
    # contradice ninguna FUENTE recuperada, solo la lógica de negocio
    # real. Tener el HECHO en las notas no bastaba — hace falta la
    # REGLA explícita, mismo principio que el fix de DIVE TO HEAL de
    # arriba (verificación/instrucción determinista, no confiar en
    # que el LLM infiera la regla de negocio él solo).
    if nota_sin_certificar:
        if state.language == "es":
            parts.append(
                "IMPORTANTE — regla de negocio real (no la inventes ni la relajes): un "
                "minicurso de buceo es UNA experiencia de iniciación de 1 día, NO una "
                "certificación. Los paquetes de 5, 7 y 9 inmersiones (y cualquier 'buceo "
                "certificado') son EXCLUSIVOS para buzos certificados (mínimo Open "
                "Water). Si el grupo tiene a alguien que hizo (o hará) el minicurso pero "
                "NO está certificado, esa persona NO puede sumarse a inmersiones de "
                "buceo certificado ese mismo viaje ni al día siguiente — necesitaría "
                "completar un curso de certificación real (Open Water) primero. Nunca "
                "confirmes ni des a entender que podrán 'bucear juntos' en el tramo "
                "certificado del plan; si preguntan por eso, acláralo con esta regla. "
                "Además, el minicurso es una reserva SEPARADA del paquete de buceo "
                "certificado (cada uno con su propio link) — no digas que uno 'incluye' "
                "al otro; si das los links de ambos, preséntalos como dos reservas "
                "distintas, no una anidada dentro de la otra."
            )
        else:
            parts.append(
                "IMPORTANT — real business rule (don't invent or soften it): a dive "
                "mini-course is a 1-day introductory experience, NOT a certification. "
                "The 5, 7, and 9-dive packages (and any 'certified diving') are "
                "EXCLUSIVE to certified divers (minimum Open Water). If the group has "
                "someone who did (or will do) the mini-course but is NOT certified, "
                "that person CANNOT join certified-diving dives on that same trip or the "
                "next day — they'd need to complete a real certification course (Open "
                "Water) first. Never confirm or imply they'll be able to 'dive together' "
                "on the certified leg of the plan; if asked, clarify with this rule. "
                "Also, the mini-course is a SEPARATE booking from the certified-diving "
                "package (each with its own link) — don't say one 'includes' the other; "
                "if you give both links, present them as two distinct bookings, not one "
                "nested inside the other."
            )

    # Hallazgo en vivo (lote 12, 2026-09-02, conv. real 856): sin esta
    # regla, "mi amigo se certifico hace 8 años y no ha vuelto a
    # bucear" hizo que el LLM confundiera "inactivo hace tiempo" con
    # "nunca certificado" -- le dijo al cliente que su amigo (SÍ
    # certificado) "no podrá unirse... necesita estar certificado" y
    # debía hacer un minicurso. `capture_notes` incluso capturó esa
    # conclusión errónea como una nota NUEVA ("amigo no tiene
    # certificación de buceo"), reforzando el error en turnos
    # siguientes -- un bucle de auto-refuerzo de la alucinación.
    if nota_certificado_inactivo:
        if state.language == "es":
            parts.append(
                "IMPORTANTE — regla de negocio real: alguien que SÍ está certificado "
                "pero lleva tiempo sin bucear SIGUE SIENDO un buzo certificado — puede "
                "sumarse normalmente al buceo certificado del grupo. Si han pasado más "
                "de 2 años desde su última inmersión, puede necesitar el *refresher* "
                "(repaso corto en el agua que el flujo normal de reserva ya ofrece; es "
                "un servicio con costo según la tarifa, nunca digas que es gratis) — "
                "eso es TODO lo que necesita. Nunca digas que "
                "'necesita estar certificado', que 'no puede unirse', ni le ofrezcas el "
                "minicurso — el minicurso es solo para quien NUNCA se ha certificado, "
                "una persona distinta a esta."
            )
        else:
            parts.append(
                "IMPORTANT — real business rule: someone who IS certified but hasn't "
                "dived in a while is STILL a certified diver — they can join the "
                "group's certified diving normally. If it's been over 2 years since "
                "their last dive, they may need the *refresher* (a short in-water "
                "review the normal booking flow already offers; it is a paid service "
                "per the rate card, never say it is free) — "
                "that's all they need. Never say they 'need to be certified', that "
                "they 'can't join', or offer them the mini-course — the mini-course is "
                "only for someone who has NEVER been certified, a different person from "
                "this one."
            )

    # Ubicacion base
    if state.location == "cartagena":
        if state.language == "es":
            parts.append(
                "El cliente indica que saldra desde Cartagena para su experiencia. "
                "Si pregunta por punto de encuentro, recogida u horarios, responde SOLO "
                "con la informacion de salida desde Cartagena (Muelle de la Bodeguita); "
                "no menciones la opcion de recogida en hotel/islas salvo que el cliente "
                "pregunte explicitamente por ese caso."
            )
        else:
            parts.append(
                "The customer is departing from Cartagena for their experience. "
                "If they ask about the meeting point, pickup, or schedule, answer ONLY "
                "with the Cartagena departure info (Muelle de la Bodeguita); do not "
                "mention the hotel/island pickup option unless they explicitly ask about it."
            )
    elif state.location == "island":
        if state.language == "es":
            parts.append(
                "El cliente indica que ya esta en las Islas del Rosario. "
                "Si pregunta por punto de encuentro, recogida u horarios, responde SOLO "
                "con la informacion de recogida en hotel/isla; no menciones la salida "
                "desde el Muelle de la Bodeguita en Cartagena salvo que el cliente "
                "pregunte explicitamente por ese caso."
            )
        else:
            parts.append(
                "The customer is already on the Rosario Islands. If they ask about the "
                "meeting point, pickup, or schedule, answer ONLY with the hotel/island "
                "pickup info; do not mention the Cartagena Muelle de la Bodeguita "
                "departure unless they explicitly ask about it."
            )
    # 6-oct: con el origen desconocido aquí iba un aviso para el RAG (V1 "no lo sabemos, pregúntalo"; V2 "la
    # conversación manda"). Medido y quitado: con texto el modelo o repreguntaba o volvía a suponer. Desde el 7-oct lo
    # hace el código (`conversational_core._origen_antes_del_precio`, opción C).

    # Isla / hotel
    if getattr(state, "island", None):
        parts.append(f"Se hospeda (o se hospedara) en la isla: {state.island}.")
    if getattr(state, "hotel", None):
        parts.append(f"Hotel/alojamiento reportado: {state.hotel}.")

    # Actividad seleccionada
    if getattr(state, "selected_service", None):
        try:
            from src.flows.catalog import MULTI_DAY_SERVICES, SERVICES

            service_id = state.selected_service
            service = SERVICES.get(service_id)
            if service:
                name_es = service.get("name_es", service_id)
                parts.append(
                    f"Actividad seleccionada en el arbol de opciones: {name_es} (id={service_id})."
                )

                # Contexto de tipo de plan: 1 día vs paquete/multi-día
                is_multi_day = service_id in MULTI_DAY_SERVICES or service.get("includes_night_dive", False)
                if state.language == "es":
                    if is_multi_day:
                        parts.append(
                            "El plan seleccionado es un paquete de varios dias o requiere al menos una noche de alojamiento en las islas."
                        )
                    else:
                        parts.append(
                            "El plan seleccionado es de un solo dia (ida y vuelta el mismo dia)."
                        )
                    parts.append(
                        "Si el cliente pregunta por amigos o acompanantes que quieran bucear o hacer snorkel, "
                        "prioriza opciones que respeten este contexto: mismo origen (Cartagena vs ya en las islas) "
                        "y, cuando sea posible, misma logica de duracion (plan de 1 dia vs paquete multi-dia), salvo que el cliente pida explicitamente otra cosa."
                    )
                else:
                    if is_multi_day:
                        parts.append(
                            "The selected plan is a multi-day package or requires at least one overnight stay on the islands."
                        )
                    else:
                        parts.append(
                            "The selected plan is a one-day experience (go and return on the same day)."
                        )
                    parts.append(
                        "If the customer asks about friends or companions who want to dive or snorkel, "
                        "prioritize options that keep this context: same origin (Cartagena vs already on the islands) "
                        "and, when possible, a similar duration pattern (1-day plan vs multi-day package), unless the customer explicitly asks otherwise."
                    )
        except Exception:
            parts.append(
                f"Actividad seleccionada en el arbol de opciones con id={state.selected_service}."
            )

    # Ground truth de la actividad activa (seleccionada en el arbol O en
    # previsualizacion del carrito sin confirmar aun) — inyecta directamente
    # que incluye/no incluye para que preguntas como "tengo que llevar equipo?"
    # o "esta el seguro incluido?" no dependan de que la busqueda vectorial
    # encuentre el chunk correcto del servicio.
    active_service_id = (
        getattr(state, "mixed_pending_preview_service_id", None)
        # Set as soon as the client picks a specific cert/course plan (e.g.
        # "Paquete multi-dia" -> "5 buceos"), well before the final preview
        # card — without this, questions asked mid cert-plan sub-flow (last
        # dive question, refresher interest/qty) had no service context.
        or getattr(state, "mixed_pending_qty_plan", None)
        or getattr(state, "selected_service", None)
    )
    if active_service_id:
        try:
            from src.flows.catalog import SERVICES

            active_service = SERVICES.get(active_service_id)
            if active_service:
                name = active_service.get(f"name_{state.language}", active_service_id)
                includes = active_service.get(f"includes_{state.language}")
                not_included = active_service.get(f"not_included_{state.language}") or []
                if state.language == "es":
                    parts.append(f"Actividad que el cliente esta viendo/considerando ahora: {name}.")
                    if includes:
                        parts.append(f"Esta actividad SI incluye: {includes}.")
                    if not_included:
                        parts.append(f"Esta actividad NO incluye: {', '.join(not_included)}.")
                    parts.append(
                        "Usa esta lista como fuente de verdad para preguntas de equipo, seguro o "
                        "que incluye/no incluye; no necesitas buscar en otra parte."
                    )
                else:
                    parts.append(f"Activity the customer is currently viewing/considering: {name}.")
                    if includes:
                        parts.append(f"This activity DOES include: {includes}.")
                    if not_included:
                        parts.append(f"This activity does NOT include: {', '.join(not_included)}.")
                    parts.append(
                        "Use this list as the source of truth for equipment, insurance, or "
                        "what's included/not included questions; no need to search elsewhere."
                    )
        except Exception:
            pass

    # Buzo certificado / principiante
    if getattr(state, "is_certified", None) is True:
        parts.append("El cliente marco que es buzo certificado (solo buzos certificados en el grupo).")
    elif getattr(state, "is_certified", None) is False:
        parts.append("El cliente marco que no es buzo certificado o que viene como principiante/snorkel.")

    # Colombiano o no
    if getattr(state, "is_colombian", None) is True:
        parts.append("El cliente indico que es colombiano/a (mostrar precios en COP, no hay descuento especial por ser colombiano).")
        # gen-4 (decisión de Gadea, Coral #862): al cerrar, un asesor coordina su pago en COP; el link de reserva que
        # el RAG le daba antes (banco dialogos-gen4-moneda, g4-colombiana) le hacía pagar por otro camino.
        parts.append("Al ser colombiano/a o residente, su pago (100 % online, o un anticipo del 50 % con el enlace, el "
                     "QR o Llave que le envía un asesor y el otro 50 % el día de la actividad, en COP) lo coordina un "
                     "asesor al cerrar la reserva: no le compartas el link de reserva.")
    elif getattr(state, "is_colombian", None) is False:
        parts.append("El cliente indico que no es colombiano/a (mostrar precios en USD).")
    else:
        # La moneda la decide el código con el estado, no el modelo (CAL-B). Sin nacionalidad, USD y COP
        # (lat-deuda-u, decisión de Gadea del 26-oct; `src/flows/moneda.py`).
        parts.append("Aun no sabemos la nacionalidad del cliente: si das un precio, en USD y en COP (es el mismo precio, "
                     "solo cambia la moneda; si dice que es colombiano/a o residente en Colombia, solo en COP).")

    # Inactividad y refresher
    if getattr(state, "last_dive_over_2_years", None) is True:
        parts.append("Segun el arbol, lleva mas de 2 años sin bucear.")
    elif getattr(state, "last_dive_over_2_years", None) is False:
        parts.append("Segun el arbol, su ultima inmersión fue hace menos de 2 años.")

    if getattr(state, "refresher_interested", None) is True:
        parts.append("En el flujo marco que SI le interesa incluir un refresher.")
    elif getattr(state, "refresher_interested", None) is False:
        parts.append("En el flujo marco que NO le interesa incluir un refresher.")

    # Tamano de grupo ya conocido (detectado en texto libre o pendiente de
    # confirmar cantidad) — para que el LLM no pida "cuantos son" si el
    # cliente ya lo dijo en otro punto de la conversacion.
    group_size = getattr(state, "detected_group_size", None) or getattr(state, "mixed_pending_qty_value", None)
    if group_size:
        if state.language == "es":
            parts.append(f"El cliente ya indico que son {group_size} persona(s) en total.")
        else:
            parts.append(f"The customer already said there are {group_size} people in total.")

    # Duracion detectada (un dia vs varios dias)
    duration = getattr(state, "detected_duration", None)
    if duration == "single_day":
        parts.append(
            "El cliente indico que estara solo un dia." if state.language == "es"
            else "The customer indicated they will be there for a single day."
        )
    elif duration == "multi_day":
        parts.append(
            "El cliente indico que estara varios dias." if state.language == "es"
            else "The customer indicated they will be there for multiple days."
        )

    # Edades concretas mencionadas -> ground truth de elegibilidad por edad.
    # Sin esto, un mensaje que solo trae edades ("familia con hijos de 5, 8,
    # 11 y 15") no recupera nada util del KB y cae al fallback generico,
    # aunque el motor determinista de eligibility.py sepa exactamente que
    # puede hacer cada uno.
    mentioned_ages = sorted({a for a in (state.detected_ages or []) if 1 <= a <= 17})
    if mentioned_ages:
        notes = " ".join(
            eligibility.age_eligibility_note(a, state.language or "es")
            for a in mentioned_ages
        )
        header = (
            "Edades de menores mencionadas y qué puede hacer cada uno (datos exactos, úsalos): "
            if state.language == "es"
            else "Ages of minors mentioned and what each can do (exact facts, use them): "
        )
        parts.append(header + notes)

    # Menores de edad ya contabilizados en el grupo
    kids_u8 = getattr(state, "kids_under_8_count", 0) or 0
    kids_8_10 = getattr(state, "kids_eight_to_ten_count", 0) or 0
    if kids_u8 or kids_8_10:
        if state.language == "es":
            parts.append(
                f"En el grupo ya se contabilizaron {kids_u8} menor(es) de 8 años "
                f"y {kids_8_10} de 8 a 10 años. No vuelvas a preguntar por edades de niños. "
                "Regla de edades (fuente de verdad): los menores de 8 años SOLO pueden hacer "
                "snorkel (edad minima 6 años), no pueden bucear. De 8 a 10 años: programa "
                "Bubble Makers — sesion especializada de buceo en piscina y aguas poco "
                "profundas (maximo 2 metros de profundidad) con un instructor PADI dedicado, "
                "es la forma en que los niños de esa edad si pueden iniciarse en el buceo de "
                "forma segura. Desde los 10 años: minicurso de buceo normal y cursos PADI."
            )
        else:
            parts.append(
                f"The group already accounts for {kids_u8} child(ren) under 8 and "
                f"{kids_8_10} aged 8-10. Do not ask about kids' ages again. "
                "Age rule (source of truth): children under 8 can ONLY do snorkeling "
                "(minimum age 6), they cannot dive. Ages 8 to 10: Bubble Makers program — "
                "a specialized dive session in a pool or very shallow water (max 2 meters "
                "deep) with a dedicated PADI instructor; that's how kids that age can safely "
                "start diving. From age 10: the regular dive mini-course and PADI courses."
            )

    # Lancha privada
    if getattr(state, "mixed_final_wants_private", None) is True:
        parts.append(
            "El cliente ya solicito lancha privada para el grupo." if state.language == "es"
            else "The customer already requested a private boat for the group."
        )
    elif getattr(state, "mixed_final_wants_private", None) is False:
        parts.append(
            "El cliente indico que NO quiere lancha privada." if state.language == "es"
            else "The customer indicated they do NOT want a private boat."
        )

    # Carrito actual (clave para no preguntar cosas que el cliente ya eligio)
    cart = getattr(state, "mixed_cart", None) or []
    if cart:
        items = ", ".join(
            f"{it.get('qty', 0)} x {it.get('label') or it.get('type', '')}" for it in cart
        )
        if state.language == "es":
            # s4-26 (7-oct): el cliente no ve ningun "carrito" (ve la tarjeta con el link) y el modelo
            # repetia la palabra ("el curso que tienes en tu carrito", manual-duracion-curso: el juez lo da por invento).
            donde = "en el plan que está armando"
            el_plan = "el plan"
            parts.append(
                f"El cliente YA tiene estas actividades {donde}: {items}. "
                "No vuelvas a preguntar por estas actividades; tenlas en cuenta como contexto. "
                "Cuando hables de equipo, seguro u otros detalles de la actividad, usa el "
                f"mismo termino que tiene en {el_plan} (buceo, snorkel o minicurso) sin "
                f"mezclarlo con otra actividad — por ejemplo, si {el_plan} tiene snorkel, "
                "habla de 'equipo de snorkel', no de 'equipo de buceo'."
            )
        else:
            where = "in the plan they are putting together"
            the_item = "the plan item"
            the_plan = "the plan"
            parts.append(
                f"The customer ALREADY has these activities {where}: {items}. "
                "Do not ask again about these activities; treat them as known context. "
                "When talking about equipment, insurance, or other activity details, use "
                f"the SAME term as {the_item} (diving, snorkeling, or mini-course) — do "
                f"not mix it with another activity (e.g. if {the_plan} has snorkeling, say "
                "'snorkeling gear', not 'diving gear')."
            )

        # Ground truth de incluye/no incluye por cada tipo de actividad distinto
        # en el carrito — mismo motivo que para la previsualizacion: evita que
        # la respuesta dependa de que la busqueda vectorial acierte el chunk.
        try:
            from src.flows.catalog import SERVICES

            seen_service_ids: set[str] = set()
            for item in cart:
                cart_service_id = cart_render.cart_service_id(
                    item.get("type"), item.get("plan"), state
                )
                if not cart_service_id or cart_service_id in seen_service_ids:
                    continue
                seen_service_ids.add(cart_service_id)
                cart_service = SERVICES.get(cart_service_id)
                if not cart_service:
                    continue
                name = cart_service.get(f"name_{state.language}", cart_service_id)
                includes = cart_service.get(f"includes_{state.language}")
                not_included = cart_service.get(f"not_included_{state.language}") or []
                if state.language == "es":
                    if includes:
                        parts.append(f"'{name}' SI incluye: {includes}.")
                    if not_included:
                        parts.append(f"'{name}' NO incluye: {', '.join(not_included)}.")
                else:
                    if includes:
                        parts.append(f"'{name}' DOES include: {includes}.")
                    if not_included:
                        parts.append(f"'{name}' does NOT include: {', '.join(not_included)}.")
        except Exception:
            pass

    # Paso actual del flujo guiado (para que el LLM sepa que esta esperando el bot)
    step_value = getattr(getattr(state, "step", None), "value", None)
    if step_value:
        if state.language == "es":
            parts.append(f"Paso actual del flujo guiado: {step_value}.")
        else:
            parts.append(f"Current guided-flow step: {step_value}.")

    if not parts:
        return None
    return " ".join(parts)
