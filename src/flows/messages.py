"""
Plantillas de mensajes y menús de botones.

Extraído de ``decision_tree.py`` (reorg §1): el diccionario ``MESSAGES``, los
``BUTTON_OPTIONS``, el helper ``get_button_options`` y la clase ``DecisionTree``
(arma los quick-replies del supervisor). Depende de ``state`` para
``ButtonOption``/``ConversationState``.
"""

from src.flows.state import ButtonOption, ConversationState

# --- Messages templates ---

MESSAGES = {
    "welcome": {
        "es": (
            "¡Hola! Soy *Coral* 🪸 y te doy la bienvenida a *Diving Planet*, el primer centro de buceo "
            "PADI 5 Estrellas de Colombia, con 30 años de experiencia en "
            "las Islas del Rosario, Cartagena.\n\n"
            "Selecciona tu idioma / Select your language:\n\n"
            "🌎 Español\n"
            "🌐 English"
        ),
        "en": (
            "Hi! I'm *Coral* 🪸, welcome to *Diving Planet* — Colombia's first "
            "PADI 5 Star Dive Center, with 30 years of experience in "
            "the Rosario Islands, Cartagena.\n\n"
            "Select your language / Selecciona tu idioma:\n\n"
            "🌎 Español\n"
            "🌐 English"
        ),
    },
    "main_menu": {
        "es": (
            "¡Cuéntame! ¿Qué te gustaría hacer?"
        ),
        "en": (
            "What would you like to do?"
        ),
    },
    "welcome_detected": {
        "es": (
            "¡Hola! Soy *Coral* 🪸 y te doy la bienvenida a *Diving Planet*, el primer centro de buceo "
            "PADI 5 Estrellas de Colombia, con 30 años de experiencia en "
            "las Islas del Rosario, Cartagena.\n\n"
            "¡Cuéntame! ¿Qué te gustaría hacer?"
        ),
        "en": (
            "Hi! I'm *Coral* 🪸, welcome to *Diving Planet* — Colombia's first "
            "PADI 5 Star Dive Center, with 30 years of experience in "
            "the Rosario Islands, Cartagena.\n\n"
            "What would you like to do?"
        ),
    },
    "reserva_menu": {
        "es": (
            "¡Perfecto! Vamos a armar tu reserva *paso a paso* desde el carrito.\n\n"
            "Cuando quieras, empezamos."
        ),
        "en": (
            "Great! Let's build your booking *step by step* from the cart flow.\n\n"
            "Whenever you're ready, let's begin."
        ),
    },
    "info_menu": {
        "es": (
            "¿Qué información te gustaría ver?"
        ),
        "en": (
            "What information do you need?"
        ),
    },
    "info_activity_location": {
        "es": (
            "Para darte información más precisa, ¿desde dónde harías la actividad?"
        ),
        "en": (
            "To share more accurate info, where would you do the activity from?"
        ),
    },
    "info_activities_menu": {
        "es": (
            "🧭 Dentro de actividades, ¿qué te gustaría explorar?"
        ),
        "en": (
            "🧭 Within activities, what would you like to explore?"
        ),
    },
    "info_tours_menu": {
        "es": (
            "Genial, cuéntame qué tipo de plan buscas:\n"
            "Elige la opción que mejor se ajuste."
        ),
        "en": (
            "Great! Tell me what kind of plan you're looking for:\n"
            "Choose the option that fits best."
        ),
    },
    "info_packages_menu": {
        "es": (
            "Perfecto. Dentro de buceo, ¿cómo está compuesto tu grupo?"
        ),
        "en": (
            "Perfect. Within diving, how is your group made up?"
        ),
    },
    "info_courses_menu": {
        "es": (
            "Nuestros cursos PADI en las Islas del Rosario:\n\n"
            "Todos combinan teoria online + practica en las islas."
        ),
        "en": (
            "Our PADI courses in the Rosario Islands:\n\n"
            "All combine online theory + island practice."
        ),
    },
    "info_specialties_menu": {
        "es": (
            "Estas son nuestras especialidades PADI disponibles.\n"
            "Elige una para ver la informacion del servicio."
        ),
        "en": (
            "These are our available PADI specialties.\n"
            "Choose one to see the service information."
        ),
    },
    "info_tours_certified_menu": {
        "es": (
            "Excelente! Estas son nuestras opciones para buzos certificados:\n\n"
            "🏨 *Importante*: si eliges un plan con inmersiones en días distintos, debes hospedarte en un hotel en las islas entre jornadas.\n"
            "- *4 inmersiones (2 días)* y *5 inmersiones (2 días)*: al menos *1 noche*\n"
            "- *7 inmersiones (3 días)*: al menos *2 noches*\n"
            "- *9 inmersiones (4 días)*: al menos *3 noches*\n\n"
            "✳️ *3 inmersiones (1 día)*: también se requiere hospedaje en la isla por la noche, porque incluye inmersión nocturna."
        ),
        "en": (
            "Excellent! Here are our options for certified divers:\n\n"
            "🏨 *Important*: if you choose a plan with dives on different days, you must stay at a hotel on the islands between dive days.\n"
            "- *4 dives (2 days)* and *5 dives (2 days)*: at least *1 night*\n"
            "- *7 dives (3 days)*: at least *2 nights*\n"
            "- *9 dives (4 days)*: at least *3 nights*\n\n"
            "✳️ *3 dives (1 day)*: island accommodation is also required that night because it includes a night dive."
        ),
    },
    "info_courses_advanced_menu": {
        "es": (
            "Estos son nuestros cursos PADI avanzados y profesionales.\n"
            "Elige el que más te interese."
        ),
        "en": (
            "These are our advanced and professional PADI courses.\n"
            "Choose the one you are most interested in."
        ),
    },
    "info_mixed_activity_menu": {
        "es": (
            "Perfecto. Para grupos mixtos *buceo + snorkel* combinamos actividades en un mismo tour.\n\n"
            "¿Sobre qué actividad quieres ver información primero?"
        ),
        "en": (
            "Great. For *diving + snorkeling* mixed groups we combine activities in a single tour.\n\n"
            "Which activity would you like to see information about first?"
        ),
    },
    "info_mixed_cert_beg_menu": {
        "es": (
            "Perfecto. Para grupos mixtos *certificados + principiantes* combinamos actividades en un mismo tour.\n\n"
            "¿Qué parte quieres revisar primero?"
        ),
        "en": (
            "Great. For *certified + beginners* mixed groups we combine activities in a single tour.\n\n"
            "Which part would you like to review first?"
        ),
    },
    "info_certified_4_dives_variant": {
        "es": (
            "Perfecto. Para *4 inmersiones (2 días)* desde las islas, ¿qué opción prefieres?"
        ),
        "en": (
            "Perfect. For *4 dives (2 days)* from the islands, which option would you prefer?"
        ),
    },
    "courses_menu": {
        "es": (
            "Nuestros cursos PADI en las Islas del Rosario:\n\n"
            "Todos combinan teoria online + practica en las islas."
        ),
        "en": (
            "Our PADI courses in the Rosario Islands:\n\n"
            "All combine online theory + island practice."
        ),
    },
    "courses_open_water_origin": {
        "es": (
            "Perfecto, vamos a ver tu curso Open Water.\n\n"
            "Primero, ¿desde dónde harías la parte práctica?"
        ),
        "en": (
            "Great, let's check your Open Water course.\n\n"
            "First, where would you do the practical part?"
        ),
    },
    "courses_open_water_time": {
        "es": (
            "¿Tienes al menos *2 días completos* para hacer la parte práctica del curso?"
        ),
        "en": (
            "Do you have at least *2 full days* for the practical part of the course?"
        ),
    },
    "courses_advanced_menu": {
        "es": (
            "Estos son nuestros cursos PADI avanzados y profesionales.\n"
            "Elige el que más te interese."
        ),
        "en": (
            "These are our advanced and professional PADI courses.\n"
            "Choose the one you are most interested in."
        ),
    },
    "courses_specialties_menu": {
        "es": (
            "Estas son nuestras especialidades PADI disponibles.\n"
            "Elige una para ver la información del servicio."
        ),
        "en": (
            "These are our available PADI specialties.\n"
            "Choose one to see the service information."
        ),
    },
    # ─── Cart-style mixed-group MESSAGES ───
    "mixed_entry": {
        "es": (
            "¡Genial! Vamos a armar tu reserva paso a paso. 🛒\n\n"
            "Puedes añadir varias reservas (buceo certificado, snorkel, minicurso, cursos PADI, acompañantes) "
            "y al final revisamos todo antes de confirmar."
        ),
        "en": (
            "Great! Let's build your booking step by step. 🛒\n\n"
            "You can add several bookings (certified diving, snorkeling, mini-course, PADI courses, companions) "
            "and we'll review everything before you confirm."
        ),
    },
    "mixed_entry_cert_beg": {
        "es": (
            "¡Genial! Vamos a armar tu reserva paso a paso. 🛒\n\n"
            "Puedes añadir varias actividades (buceo certificado, minicurso, acompañantes) "
            "y al final revisamos todo antes de confirmar."
        ),
        "en": (
            "Great! Let's build your booking step by step. 🛒\n\n"
            "You can add several activities (certified diving, mini-course, companions) "
            "and we'll review everything before you confirm."
        ),
    },
    "mixed_location": {
        "es": (
            "Genial 🤿 Para armarlo bien, dime desde dónde saldrías:\n\n"
            "🚤 *Desde Cartagena* — nosotros te llevamos a las Islas del Rosario (ida y vuelta el mismo día).\n"
            "🏝️ *Ya en las islas* — coordinamos la recogida en tu hotel.\n\n"
            "Elige una opción 👇"
        ),
        "en": (
            "Great 🤿 To set it up right, tell me where you'd be departing from:\n\n"
            "🚤 *From Cartagena* — we take you to the Rosario Islands (round trip, same day).\n"
            "🏝️ *Already on the islands* — we arrange pickup at your hotel.\n\n"
            "Pick an option 👇"
        ),
    },
    "mixed_ask_certification": {
        "es": (
            "Perfecto, te ayudo con el buceo. Para continuar necesito saber:\n\n"
            "¿Eres buzo certificado?"
        ),
        "en": (
            "Perfect, I'll help you with diving. To continue I need to know:\n\n"
            "Are you a certified diver?"
        ),
    },
    "mixed_ask_certification_group": {
        "es": (
            "Perfecto, os ayudo con el buceo. Para continuar necesito saber:\n\n"
            "¿Estáis certificados?"
        ),
        "en": (
            "Perfect, I'll help you with diving. To continue I need to know:\n\n"
            "Are you all certified divers?"
        ),
    },
    "mixed_add_activity": {
        "es": "¿Qué actividad quieres *añadir* al carrito?",
        "en": "Which activity would you like to *add* to the cart?",
    },
    "mixed_companion_upsell": {
        "es": (
            "¡Qué bueno que venga acompañante! 🌊 Te recomiendo apuntarle el *minicurso de buceo* "
            "(bautismo con instructor, sin experiencia previa) — es la opción más popular para quien "
            "viene acompañando. Si prefiere *snorkel* o *solo acompañar* sin hacer actividad en el agua, "
            "dímelo y lo ajusto. ¿Te parece?"
        ),
        "en": (
            "Love that a companion is coming along! 🌊 I'd recommend signing them up for the "
            "*dive mini-course* (Discover Scuba with an instructor, no experience needed) — it's the "
            "most popular pick for someone tagging along. If they'd rather *snorkel* or *just accompany* "
            "without any water activity, let me know and I'll adjust it. Sound good?"
        ),
    },
    "mixed_add_cert_plan": {
        "es": (
            "Para *buceo certificado*, ¿qué idea tienes?\n\n"
            "🤿 *2 inmersiones / 1 día*: salida de día completo a las Islas del Rosario con 2 inmersiones guiadas.\n"
            "📅 *Paquete multi-día (3 o más inmersiones)*: varios días seguidos para profundizar tu experiencia. "
            "Requiere dormir en las islas entre jornadas."
        ),
        "en": (
            "For *certified diving*, what do you have in mind?\n\n"
            "🤿 *2 dives / 1 day*: full-day trip to the Rosario Islands with 2 guided dives.\n"
            "📅 *Multi-day package (3 or more dives)*: several consecutive days to deepen your experience. "
            "Requires staying on the islands between dive days."
        ),
    },
    "mixed_add_cert_multi_day": {
        "es": (
            "Para *buceo certificado*, estas son las opciones de *3 o más inmersiones*:\n\n"
            "🏨 *Importante*: si eliges un plan con inmersiones en días distintos, debes hospedarte en un hotel en las islas entre jornadas.\n"
            "- *4 inmersiones (2 días)* y *5 inmersiones (2 días)*: al menos *1 noche*\n"
            "- *7 inmersiones (3 días)*: al menos *2 noches*\n"
            "- *9 inmersiones (4 días)*: al menos *3 noches*\n\n"
            "✳️ *3 inmersiones (1 día)*: también se requiere hospedaje en la isla por la noche, porque incluye inmersión nocturna.\n\n"
            "¿Qué paquete quieres añadir al carrito?"
        ),
        "en": (
            "For *certified diving*, these are the *3 or more dives* options:\n\n"
            "🏨 *Important*: if you choose a plan with dives on different days, you must stay at a hotel on the islands between dive days.\n"
            "- *4 dives (2 days)* and *5 dives (2 days)*: at least *1 night*\n"
            "- *7 dives (3 days)*: at least *2 nights*\n"
            "- *9 dives (4 days)*: at least *3 nights*\n\n"
            "✳️ *3 dives (1 day)*: island accommodation is also required that night because it includes a night dive.\n\n"
            "Which package would you like to add to the cart?"
        ),
    },
    "mixed_add_cert_4dive_variant": {
        "es": "🤿 Para las *4 inmersiones (2 días)*, ¿prefieres 🌞 *4 diurnas* o 🌙 *3 diurnas + 1 nocturna*?",
        "en": "🤿 For the *4-dive (2-day)* plan, would you prefer 🌞 *4 daytime dives* or 🌙 *3 daytime + 1 night dive*?",
    },
    "mixed_add_cert_1day_variant": {
        "es": "🤿 Para el plan de *1 día*, ¿prefieres 🤿 *2 inmersiones* o 🌙 *3 inmersiones (con nocturna)*?",
        "en": "🤿 For the *1-day* plan, would you prefer 🤿 *2 dives* or 🌙 *3 dives (with a night dive)*?",
    },
    "mixed_add_cert_2day_variant": {
        "es": "🤿 Para el plan de *2 días*, ¿prefieres 🤿 *4 inmersiones* o 🤿 *5 inmersiones*?",
        "en": "🤿 For the *2-day* plan, would you prefer 🤿 *4 dives* or 🤿 *5 dives*?",
    },
    "mixed_add_qty": {
        "es": "¿Para *cuántas personas*?",
        "en": "For *how many people*?",
    },
    "mixed_add_preview": {
        "es": "¿Te la *añado a tu reserva*? (al terminar te paso el enlace para reservarla)",
        "en": "Shall I *add it to your booking*? (at the end I'll send you the link to book it)",
    },
    "mixed_cert_last_dive": {
        "es": (
            "¿Han pasado *más de 2 años* desde tu última inmersión?\n\n"
            "Si es así, te recomendamos hacer un *refresher* antes de la salida."
        ),
        "en": (
            "Has it been *more than 2 years* since your last dive?\n\n"
            "If so, we recommend doing a *refresher* before the trip."
        ),
    },
    "mixed_cert_last_dive_group": {
        "es": (
            "¿Ha pasado *más de 2 años* desde la última inmersión de alguno del grupo?\n\n"
            "Si es así, recomendamos un *refresher* antes de la salida."
        ),
        "en": (
            "Has it been *more than 2 years* since any diver in the group last dived?\n\n"
            "If so, we recommend a *refresher* before the trip."
        ),
    },
    "refresher_info": {
        "es": (
            "El *refresher* es una sesión corta de repaso en el agua antes de la inmersión. "
            "Sin coste adicional — el guía adapta el ritmo a tu nivel.\n\n"
            "¿Te interesa el refresher?"
        ),
        "en": (
            "The *refresher* is a short in-water review session before the dive. "
            "No extra cost — the guide adapts the pace to your level.\n\n"
            "Are you interested in the refresher?"
        ),
    },
    "refresher_info_group": {
        "es": (
            "El *refresher* es una sesión corta de repaso en el agua antes de la inmersión. "
            "Sin coste adicional — el guía adapta el ritmo a vuestro nivel.\n\n"
            "¿Os interesa el refresher?"
        ),
        "en": (
            "The *refresher* is a short in-water review session before the dive. "
            "No extra cost — the guide adapts the pace to your group's level.\n\n"
            "Is your group interested in the refresher?"
        ),
    },
    "mixed_cert_refresh_qty": {
        "es": "¿Cuántas de estas personas quieren hacer el *refresher*?\n_(Sin coste adicional — el guía adapta la inmersión a su nivel)_",
        "en": "How many of these people want to do the *refresher*?\n_(No extra cost — the guide adapts the dive to their level)_",
    },
    "mixed_cart_empty": {
        "es": "Tu carrito está vacío. Añade al menos una actividad para continuar.",
        "en": "Your cart is empty. Add at least one activity to continue.",
    },
    "mixed_cart_actions": {
        "es": "¿Cómo quieres continuar?",
        "en": "How would you like to continue?",
    },
    "mixed_cart_modify_pick": {
        "es": "¿Qué *item del carrito* quieres modificar?",
        "en": "Which *cart item* do you want to modify?",
    },
    "mixed_cart_remove_pick": {
        "es": "¿Qué *item del carrito* quieres quitar?",
        "en": "Which *cart item* do you want to remove?",
    },
    "mixed_cart_location": {
        "es": "¿Desde dónde tomarán la salida? Los precios se actualizarán según tu elección.",
        "en": "Where will you depart from? Prices will update according to your choice.",
    },
    "mixed_final_colombian": {
        "es": (
            "Para terminar, ¿eres *colombiano/a o residente en Colombia*?\n"
            "_Es solo para mostrarte el precio en tu moneda: el precio es el mismo, "
            "no hay ningún cobro extra por el cambio de divisa — pesos (COP) o dólares (USD)._"
        ),
        "en": (
            "Last question: are you *Colombian / resident in Colombia*?\n"
            "_It's only to show the price in your currency: the price is the same, "
            "there's no extra charge for the currency — COP or USD._"
        ),
    },
    "mixed_final_kids": {
        "es": (
            "¿Hay *niños menores de 10 años* en el grupo? Dime el rango para planificar bien la actividad:\n\n"
            "• 👶 *Menores de 8 años*: solo pueden hacer *snorkel* (mín. 6 años); no pueden bucear.\n"
            "• 👦 *De 8 a 10 años*: programa *Bubble Makers* — sesión especializada en piscina y mar poco profundo "
            "(máx. 2 m de profundidad) con un instructor dedicado.\n"
            "• 🧑 *Todos 10+*: pueden hacer el minicurso normal sin cambios.\n"
            "• 🧒 *Varios rangos (mezcla)*: te pregunto cuántos hay en cada rango."
        ),
        "en": (
            "Are there any *children under 10* in the group? Tell me the range so I can plan the activity properly:\n\n"
            "• 👶 *Under 8*: snorkeling only (min. 6 years); cannot dive.\n"
            "• 👦 *Ages 8-10*: *Bubble Makers* program — specialized pool + shallow-water session "
            "(max. 2 m depth) with a dedicated instructor.\n"
            "• 🧑 *Everyone 10+*: regular mini-course, no changes.\n"
            "• 🧒 *Multiple ranges (mix)*: I'll ask how many are in each range."
        ),
    },
    "mixed_final_kids_qty": {
        "es": "¿*Cuántos niños* son en ese rango? Esto nos ayuda a desglosar bien la actividad:",
        "en": "*How many kids* in that range? This helps us break down the activity properly:",
    },
    "mixed_kids_age": {
        "es": (
            "¿Hay *niños menores de 10 años* en el grupo? Dime el rango para planificar bien la actividad:\n\n"
            "• 👶 *Menores de 8 años*: solo pueden hacer *snorkel* (mín. 6 años); no pueden bucear.\n"
            "• 👦 *De 8 a 10 años*: programa *Bubble Makers* — sesión especializada en piscina y mar poco profundo "
            "(máx. 2 m de profundidad) con un instructor dedicado.\n"
            "• 🧑 *Todos 10+*: pueden hacer el minicurso normal sin cambios.\n"
            "• 🧒 *Varios rangos (mezcla)*: te pregunto cuántos hay en cada rango."
        ),
        "en": (
            "Are there any *children under 10* in the group? Tell me the range so I can plan the activity properly:\n\n"
            "• 👶 *Under 8*: snorkeling only (min. 6 years); cannot dive.\n"
            "• 👦 *Ages 8-10*: *Bubble Makers* program — specialized pool + shallow-water session "
            "(max. 2 m depth) with a dedicated instructor.\n"
            "• 🧑 *Everyone 10+*: regular mini-course, no changes.\n"
            "• 🧒 *Multiple ranges (mix)*: I'll ask how many are in each range."
        ),
    },
    "mixed_final_kids_u8": {
        "es": "¿Cuántos *menores de 8* hay en el grupo? (no pueden bucear, snorkel desde 6 años)",
        "en": "How many *under 8* are in the group? (cannot dive, snorkel from age 6)",
    },
    "mixed_final_kids_810": {
        "es": "¿Y cuántos *entre 8 y 10*? (Bubble Makers — supervisor especializado)",
        "en": "And how many *between 8 and 10*? (Bubble Makers — specialized supervisor)",
    },
    "mixed_final_private": {
        "es": "¿Os interesa una *lancha privada exclusiva* para el grupo?",
        "en": "Are you interested in an *exclusive private boat* for the group?",
    },
    "mixed_final_summary_actions": {
        "es": "¿Cómo quieres continuar?",
        "en": "How would you like to continue?",
    },
    "pricing_menu": {
        "es": (
            "Sobre que tipo de plan quieres ver *precios y descuentos*?"
        ),
        "en": (
            "What would you like *prices and discounts* for?"
        ),
    },
    "booking_menu": {
        "es": (
            "Te explico como funcionan las *reservas y pagos*.\n"
            "Selecciona lo que mas se acerque a tu duda."
        ),
        "en": (
            "Let me explain how *bookings and payments* work.\n"
            "Choose what matches your question best."
        ),
    },
    "logistics_menu": {
        "es": (
            "Te ayudo con la *logistica* de tu experiencia: horarios, punto de encuentro, "
            "alojamiento, que llevar, clima y cancelaciones.\n"
            "¿Por donde empezamos?"
        ),
        "en": (
            "I can help with the *logistics* of your experience: schedule, meeting point, "
            "accommodation, what to bring, weather and cancellations.\n"
            "Where would you like to start?"
        ),
    },
    "island_menu": {
        "es": (
            "Perfecto, dime en que isla te estas hospedando o vas a hospedarte.\n"
            "Esto nos ayuda a coordinar mejor la recogida y la logistica."
        ),
        "en": (
            "Great, tell me on which island you are staying or will be staying.\n"
            "This helps us coordinate pickup and logistics."
        ),
    },
    "location": {
        "es": (
            "Genial 🤿 Para armarlo bien, dime desde dónde saldrías:\n\n"
            "🚤 *Desde Cartagena* — nosotros te llevamos a las Islas del Rosario (ida y vuelta el mismo día).\n"
            "🏝️ *Ya en las islas* — coordinamos la recogida en tu hotel.\n\n"
            "Elige una opción 👇"
        ),
        "en": (
            "Great 🤿 To set it up right, tell me where you'd be departing from:\n\n"
            "🚤 *From Cartagena* — we take you to the Rosario Islands (round trip, same day).\n"
            "🏝️ *Already on the islands* — we arrange pickup at your hotel.\n\n"
            "Pick an option 👇"
        ),
    },
    "colombian": {
        "es": (
            "🌎 ¿Eres colombiano/a o residente en Colombia? Así te mostramos el precio en pesos o en dólares."
        ),
        "en": (
            "🌎 Are you Colombian or a resident in Colombia? That way we show you the price in COP or USD."
        ),
    },
    "escalate": {
        "es": (
            "Te paso con un asesor del equipo de Diving Planet.\n"
            "Enseguida se pone en contacto contigo. ¡Gracias! :)"
        ),
        "en": (
            "I'll connect you with an advisor from the Diving Planet team.\n"
            "They will contact you shortly. Thanks! :)"
        ),
    },
    "not_understood": {
        "es": (
            "¡Uy! No te entendí bien 🙈 ¿Puedes elegir una de las opciones de abajo?"
        ),
        "en": (
            "Hmm, I didn't quite get that. Could you pick one of the options below?"
        ),
    },
}

BUTTON_OPTIONS = {
    "welcome": {
        "es": [
            {"title": "🌎 Español", "value": "1"},
            {"title": "🌐 English", "value": "2"},
        ],
        "en": [
            {"title": "🌎 Español", "value": "1"},
            {"title": "🌐 English", "value": "2"},
        ],
    },
    "main_menu": {
        "es": [
            {"title": "🤿 Reservar", "value": "1"},
            {"title": "ℹ️ Información", "value": "2"},
        ],
        "en": [
            {"title": "🤿 Book", "value": "1"},
            {"title": "ℹ️ Information", "value": "2"},
        ],
    },
    "reserva_menu": {
        "es": [
            {"title": "🛒 Empezar reserva paso a paso", "value": "1"},
            {"title": "🔙 Volver al menú principal", "value": "back"},
        ],
        "en": [
            {"title": "🛒 Start booking step by step", "value": "1"},
            {"title": "🔙 Back to main menu", "value": "back"},
        ],
    },
    "info_menu": {
        "es": [
            {"title": "🧭 Actividades y cursos", "value": "1"},
            {"title": "💰 Precios y descuentos", "value": "2"},
            {"title": "💳 Reservas y pago", "value": "3"},
            {"title": "📍 Logística", "value": "4"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🧭 Activities and courses", "value": "1"},
            {"title": "💰 Prices and discounts", "value": "2"},
            {"title": "💳 Bookings and payment", "value": "3"},
            {"title": "📍 Logistics", "value": "4"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_activity_location": {
        "es": [
            {"title": "🚤 Salgo desde Cartagena", "value": "1"},
            {"title": "🏝️ Ya estoy en las islas", "value": "2"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🚤 Departing from Cartagena", "value": "1"},
            {"title": "🏝️ Already on the islands", "value": "2"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_activities_menu": {
        "es": [
            {"title": "🤿 Tours de buceo / snorkel", "value": "1"},
            {"title": "📘 Cursos PADI y certificaciones", "value": "2"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 Diving / snorkel tours", "value": "1"},
            {"title": "📘 PADI courses and certifications", "value": "2"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_tours_menu": {
        "es": [
            {"title": "🤿 Buceo", "value": "1"},
            {"title": "🐠 Snorkel", "value": "2"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 Diving", "value": "1"},
            {"title": "🐠 Snorkeling", "value": "2"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_packages_menu": {
        "es": [
            {"title": "🤿 Solo buzos certificados", "value": "1"},
            {"title": "🆕 Solo principiantes", "value": "2"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 Only certified divers", "value": "1"},
            {"title": "🆕 Only beginners", "value": "2"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_courses_menu": {
        "es": [
            {"title": "🐠 Descubriendo el buceo (Open Water Diver)", "value": "1"},
            {"title": "🚀 Convierte en pro (Advanced / Rescue / Dive Master)", "value": "2"},
            {"title": "✨ Amplía tus habilidades (Especialidades PADI)", "value": "3"},
            {"title": "Ya empece un curso en otro centro (referral / reactivate)", "value": "4"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🐠 Discover diving (Open Water Diver)", "value": "1"},
            {"title": "🚀 Go pro (Advanced / Rescue / Divemaster)", "value": "2"},
            {"title": "✨ Expand your skills (PADI Specialties)", "value": "3"},
            {"title": "I already started a course elsewhere (referral / reactivate)", "value": "4"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_specialties_menu": {
        "es": [
            {"title": "✨ Mindful Diving", "value": "1"},
            {"title": "🐠 Identificación de peces", "value": "2"},
            {"title": "🌿 Naturalista", "value": "3"},
            {"title": "⚖️ Flotabilidad", "value": "4"},
            {"title": "🫧 Nitrox", "value": "5"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "✨ Mindful Diving", "value": "1"},
            {"title": "🐠 Fish Identification", "value": "2"},
            {"title": "🌿 Naturalist", "value": "3"},
            {"title": "⚖️ Buoyancy", "value": "4"},
            {"title": "🫧 Nitrox", "value": "5"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_tours_certified_menu": {
        "es": [
            {"title": "🤿 2 inmersiones (1 día)", "value": "1"},
            {"title": "🤿 3 inmersiones (1 día)*", "value": "2"},
            {"title": "🤿 4 inmersiones (2 días)", "value": "3"},
            {"title": "🤿 5 inmersiones (2 días)", "value": "4"},
            {"title": "🤿 7 inmersiones (3 días)", "value": "5"},
            {"title": "🤿 9 inmersiones (4 días)", "value": "6"},
            {"title": "🧑‍💬 Servicio Privado", "value": "7"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 2 Dives (1 day)", "value": "1"},
            {"title": "🤿 3 Dives (1 day)*", "value": "2"},
            {"title": "🤿 4 Dives (2 days)", "value": "3"},
            {"title": "🤿 5 Dives (2 days)", "value": "4"},
            {"title": "🤿 7 Dives (3 days)", "value": "5"},
            {"title": "🤿 9 Dives (4 days)", "value": "6"},
            {"title": "🧑‍💬 Private Service", "value": "7"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_courses_advanced_menu": {
        "es": [
            {"title": "📘 Curso Avanzado", "value": "1"},
            {"title": "🚑 Rescate + EFR", "value": "2"},
            {"title": "🏅 Dive Master", "value": "3"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "📘 Advanced Course", "value": "1"},
            {"title": "🚑 Rescue + EFR", "value": "2"},
            {"title": "🏅 Divemaster", "value": "3"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_mixed_activity_menu": {
        "es": [
            {"title": "🎓 Buceo certificado", "value": "1"},
            {"title": "🆕 Buceo principiantes (Minicurso)", "value": "2"},
            {"title": "🐠 Snorkel", "value": "3"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🎓 Certified diving", "value": "1"},
            {"title": "🆕 Beginner diving (Mini-course)", "value": "2"},
            {"title": "🐠 Snorkeling", "value": "3"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_mixed_cert_beg_menu": {
        "es": [
            {"title": "🎓 Buceo certificado", "value": "1"},
            {"title": "🆕 Buceo principiantes (Minicurso)", "value": "2"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🎓 Certified diving", "value": "1"},
            {"title": "🆕 Beginner diving (Mini-course)", "value": "2"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_certified_4_dives_variant": {
        "es": [
            {"title": "🤿 4 inmersiones (2 días) · 4 diurnas", "value": "1"},
            {"title": "🤿 4 inmersiones (2 días) · 3 diurnas + 1 nocturna", "value": "2"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 4 Dives (2 days) · 4 daytime dives", "value": "1"},
            {"title": "🤿 4 Dives (2 days) · 3 daytime + 1 night dive", "value": "2"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "info_detail_actions": {
        "es": [
            {"title": "🤿 Reservar esta opción", "value": "1"},
            {"title": "🗺️ Ver itinerario", "value": "itinerary"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 Book this option", "value": "1"},
            {"title": "🗺️ View itinerary", "value": "itinerary"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "tours_location": {
        "es": [
            {"title": "🚤 Salgo desde Cartagena", "value": "1"},
            {"title": "🏝️ Ya estoy en las islas", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🚤 Departing from Cartagena", "value": "1"},
            {"title": "🏝️ Already on the islands", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "group_type": {
        "es": [
            {"title": "🤿 Buceo", "value": "1"},
            {"title": "🐠 Snorkel", "value": "2"},
            {"title": "👥 Grupo mixto (buceo + snorkel)", "value": "3"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 Diving", "value": "1"},
            {"title": "🐠 Snorkeling", "value": "2"},
            {"title": "👥 Mixed group (diving + snorkel)", "value": "3"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "tours_experience": {
        "es": [
            {"title": "🤿 Solo buzos certificados", "value": "1"},
            {"title": "🆕 Solo principiantes", "value": "2"},
            {"title": "👥 Grupo mixto (certificados + principiantes)", "value": "3"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 Only certified divers", "value": "1"},
            {"title": "🆕 Only beginners", "value": "2"},
            {"title": "👥 Mixed group (certified + beginners)", "value": "3"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    # ─── Cart-style mixed-group buttons ───
    "mixed_entry": {
        "es": [
            {"title": "🤿 Añadir actividades", "value": "1"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 Add activities", "value": "1"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_ask_certification": {
        "es": [
            {"title": "✅ Sí, estoy certificado", "value": "1"},
            {"title": "❌ No, soy principiante", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "✅ Yes, I'm certified", "value": "1"},
            {"title": "❌ No, I'm a beginner", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_ask_certification_group": {
        "es": [
            {"title": "✅ Todos certificados", "value": "1"},
            {"title": "❌ Ninguno certificado", "value": "2"},
            {"title": "⚠️ Algunos sí, otros no", "value": "3"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "✅ All certified", "value": "1"},
            {"title": "❌ None certified", "value": "2"},
            {"title": "⚠️ Some yes, some no", "value": "3"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_add_activity": {
        "es": [
            {"title": "🎓 Buceo certificado", "value": "1"},
            {"title": "🆕 Buceo principiantes (Minicurso)", "value": "2"},
            {"title": "🐠 Snorkel", "value": "3"},
            {"title": "🤿 Curso PADI", "value": "4"},
            {"title": "👤 Acompañante (sin actividad)", "value": "5"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🎓 Certified diving", "value": "1"},
            {"title": "🆕 Beginner diving (Mini-course)", "value": "2"},
            {"title": "🐠 Snorkeling", "value": "3"},
            {"title": "🤿 PADI course", "value": "4"},
            {"title": "👤 Companion (no activity)", "value": "5"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_companion_upsell": {
        "es": [
            {"title": "✅ Perfecto, minicurso", "value": "1"},
            {"title": "🐠 Mejor snorkel", "value": "2"},
            {"title": "👤 No, solo acompañar", "value": "3"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "✅ Perfect, mini-course", "value": "1"},
            {"title": "🐠 Snorkeling instead", "value": "2"},
            {"title": "👤 No, just accompany", "value": "3"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_add_cert_plan": {
        "es": [
            {"title": "🤿 2 Inmersiones / 1 día", "value": "1"},
            {"title": "📅 Paquete multi-día (3 o más inmersiones)", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 2 Dives / 1 day", "value": "1"},
            {"title": "📅 Multi-day package (3 or more dives)", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_add_cert_multi_day": {
        "es": [
            {"title": "🤿 3 inmersiones (1 día)*", "value": "1"},
            {"title": "🤿 4 inmersiones (2 días)", "value": "2"},
            {"title": "🤿 5 inmersiones (2 días)", "value": "3"},
            {"title": "🤿 7 inmersiones (3 días)", "value": "4"},
            {"title": "🤿 9 inmersiones (4 días)", "value": "5"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 3 Dives (1 day)*", "value": "1"},
            {"title": "🤿 4 Dives (2 days)", "value": "2"},
            {"title": "🤿 5 Dives (2 days)", "value": "3"},
            {"title": "🤿 7 Dives (3 days)", "value": "4"},
            {"title": "🤿 9 Dives (4 days)", "value": "5"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_add_cert_4dive_variant": {
        "es": [
            {"title": "🌞 4 diurnas", "value": "1"},
            {"title": "🌙 3 diurnas + 1 nocturna", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🌞 4 daytime dives", "value": "1"},
            {"title": "🌙 3 daytime + 1 night dive", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_add_cert_1day_variant": {
        "es": [
            {"title": "🤿 2 inmersiones", "value": "1"},
            {"title": "🌙 3 inmersiones (con nocturna)", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 2 dives", "value": "1"},
            {"title": "🌙 3 dives (with a night dive)", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_add_cert_2day_variant": {
        "es": [
            {"title": "🤿 4 inmersiones", "value": "1"},
            {"title": "🤿 5 inmersiones", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🤿 4 dives", "value": "1"},
            {"title": "🤿 5 dives", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_quantity": {
        "es": [
            {"title": "1", "value": "1"},
            {"title": "2", "value": "2"},
            {"title": "3", "value": "3"},
            {"title": "4", "value": "4"},
            {"title": "5", "value": "5"},
            {"title": "6 o mas", "value": "6+"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "1", "value": "1"},
            {"title": "2", "value": "2"},
            {"title": "3", "value": "3"},
            {"title": "4", "value": "4"},
            {"title": "5", "value": "5"},
            {"title": "6 or more", "value": "6+"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_preview_actions": {
        "es": [
            {"title": "✅ Sí, añadir a mi reserva", "value": "1"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "✅ Yes, add to my booking", "value": "1"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "mixed_cert_split_review": {
        "es": [
            {"title": "🎓 Continuar con el buceo", "value": "1"},
            {"title": "❌ Quitar el refresher", "value": "2"},
            {"title": "🔄 Empezar de nuevo", "value": "3"},
        ],
        "en": [
            {"title": "🎓 Continue with diving", "value": "1"},
            {"title": "❌ Remove the refresher", "value": "2"},
            {"title": "🔄 Start over", "value": "3"},
        ],
    },
    "mixed_cert_last_dive": {
        "es": [
            {"title": "Sí", "value": "1"},
            {"title": "No", "value": "2"},
        ],
        "en": [
            {"title": "Yes", "value": "1"},
            {"title": "No", "value": "2"},
        ],
    },
    "refresher_interest": {
        "es": [
            {"title": "✅ Sí, quiero el refresher", "value": "1"},
            {"title": "❌ No, lo saltamos", "value": "2"},
        ],
        "en": [
            {"title": "✅ Yes, I want the refresher", "value": "1"},
            {"title": "❌ No, skip it", "value": "2"},
        ],
    },
    "mixed_yes_no": {
        "es": [
            {"title": "✅ Si", "value": "1"},
            {"title": "❌ No", "value": "2"},
        ],
        "en": [
            {"title": "✅ Yes", "value": "1"},
            {"title": "❌ No", "value": "2"},
        ],
    },
    "mixed_cart_actions": {
        "es": [
            {"title": "📍 Cambiar origen", "value": "1"},
            {"title": "➕ Añadir otra actividad", "value": "2"},
            {"title": "🔧 Modificar item", "value": "3"},
            {"title": "❌ Quitar item", "value": "4"},
            {"title": "🔄 Empezar de nuevo", "value": "5"},
            {"title": "✅ Confirmar carrito", "value": "6"},
        ],
        "en": [
            {"title": "📍 Change origin", "value": "1"},
            {"title": "➕ Add another activity", "value": "2"},
            {"title": "🔧 Modify item", "value": "3"},
            {"title": "❌ Remove item", "value": "4"},
            {"title": "🔄 Start over", "value": "5"},
            {"title": "✅ Confirm cart", "value": "6"},
        ],
    },
    "mixed_final_summary_actions": {
        "es": [
            {"title": "🧑‍💼 Reservar / contactar asesor", "value": "1"},
            {"title": "🔄 Empezar de nuevo", "value": "2"},
            {"title": "💵 Pagar en persona", "value": "3"},
        ],
        "en": [
            {"title": "🧑‍💼 Book / contact advisor", "value": "1"},
            {"title": "🔄 Start over", "value": "2"},
            {"title": "💵 Pay in person", "value": "3"},
        ],
    },
    "mixed_kids_age": {
        "es": [
            {"title": "👶 Hay menores de 8 años", "value": "1"},
            {"title": "👦 De 8 a 10 (Bubble Makers)", "value": "2"},
            {"title": "🧑 Todos tienen 10+ años", "value": "3"},
            {"title": "🧒 Varios rangos (mezcla)", "value": "4"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "👶 Under 8 years old", "value": "1"},
            {"title": "👦 Ages 8-10 (Bubble Makers)", "value": "2"},
            {"title": "🧑 Everyone 10+ years old", "value": "3"},
            {"title": "🧒 Multiple ranges (mix)", "value": "4"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "courses_menu": {
        "es": [
            {"title": "🐠 Descubriendo el buceo (Open Water Diver)", "value": "1"},
            {"title": "🚀 Convierte en pro (Advanced / Rescue / Dive Master)", "value": "2"},
            {"title": "✨ Amplía tus habilidades (Especialidades PADI)", "value": "3"},
            {"title": "Ya empece un curso en otro centro (referral / reactivate)", "value": "4"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🐠 Discover diving (Open Water Diver)", "value": "1"},
            {"title": "🚀 Go pro (Advanced / Rescue / Divemaster)", "value": "2"},
            {"title": "✨ Expand your skills (PADI Specialties)", "value": "3"},
            {"title": "I already started a course elsewhere (referral / reactivate)", "value": "4"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "courses_open_water_origin": {
        "es": [
            {"title": "🚤 Salgo desde Cartagena", "value": "1"},
            {"title": "🏝️ Ya estoy en las islas", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🚤 Departing from Cartagena", "value": "1"},
            {"title": "🏝️ Already on the islands", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "courses_open_water_time": {
        "es": [
            {"title": "Si, tengo al menos 2 dias completos", "value": "1"},
            {"title": "No estoy seguro / tengo menos tiempo", "value": "2"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "Yes, I have at least 2 full days", "value": "1"},
            {"title": "Not sure / I have less time", "value": "2"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "courses_advanced_menu": {
        "es": [
            {"title": "📘 Curso Avanzado", "value": "1"},
            {"title": "🚑 Rescate + EFR", "value": "2"},
            {"title": "🏅 Dive Master", "value": "3"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "📘 Advanced Course", "value": "1"},
            {"title": "🚑 Rescue + EFR", "value": "2"},
            {"title": "🏅 Divemaster", "value": "3"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "courses_specialties_menu": {
        "es": [
            {"title": "✨ Mindful Diving", "value": "1"},
            {"title": "🐠 Identificación de peces", "value": "2"},
            {"title": "🌿 Naturalista", "value": "3"},
            {"title": "⚖️ Flotabilidad", "value": "4"},
            {"title": "🫧 Nitrox", "value": "5"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "✨ Mindful Diving", "value": "1"},
            {"title": "🐠 Fish Identification", "value": "2"},
            {"title": "🌿 Naturalist", "value": "3"},
            {"title": "⚖️ Buoyancy", "value": "4"},
            {"title": "🫧 Nitrox", "value": "5"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "pricing_menu": {
        "es": [
            {"title": "🚤 Precios saliendo desde Cartagena", "value": "1"},
            {"title": "🏝️ Precios si ya estoy en las islas", "value": "2"},
            {"title": "📦 Paquetes 5/7/9 inmersiones (multi-día)", "value": "3"},
            {"title": "🎁 Descuentos disponibles", "value": "4"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🚤 Prices departing from Cartagena", "value": "1"},
            {"title": "🏝️ Prices if I'm already on the islands", "value": "2"},
            {"title": "📦 5/7/9-dive multi-day packages", "value": "3"},
            {"title": "🎁 Available discounts", "value": "4"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "pricing_leaf": {
        "es": [
            {"title": "🤿 Reservar", "value": "reserve"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "🤿 Book", "value": "reserve"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "booking_menu": {
        "es": [
            {"title": "💳 Pagar todo online", "value": "1"},
            {"title": "🤝 Pagar 50% ahora y 50% después", "value": "2"},
            {"title": "💰 Formas de pago (tarjeta / transferencia)", "value": "3"},
            {"title": "👥 Reservas de grupo o agencia", "value": "4"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "💳 Pay everything online", "value": "1"},
            {"title": "🤝 Pay 50% now and 50% later", "value": "2"},
            {"title": "💰 Payment methods (card / transfer)", "value": "3"},
            {"title": "👥 Group or agency bookings", "value": "4"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "logistics_menu": {
        "es": [
            {"title": "📍 Punto de encuentro y horarios", "value": "1"},
            {"title": "🏨 Alojamiento en islas y recogida en hotel", "value": "2"},
            {"title": "✅ Qué incluye / qué no incluye el plan", "value": "3"},
            {"title": "🎒 Qué llevar y recomendaciones", "value": "4"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "📍 Meeting point and schedule", "value": "1"},
            {"title": "🏨 Accommodation on the islands & hotel pickup", "value": "2"},
            {"title": "✅ What's included / not included", "value": "3"},
            {"title": "🎒 What to bring & recommendations", "value": "4"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "logistics_leaf": {
        "es": [
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "island_menu": {
        "es": [
            {"title": "Isla Grande", "value": "1"},
            {"title": "Isla Marina", "value": "2"},
            {"title": "Isla del Pirata", "value": "3"},
            {"title": "Isla del Sol", "value": "4"},
            {"title": "Isleta", "value": "5"},
            {"title": "Isla Arena", "value": "6"},
            {"title": "Isla Pavitos", "value": "7"},
            {"title": "Isla Lizamar", "value": "8"},
            {"title": "Isla Gigi", "value": "9"},
            {"title": "Isla Rosa", "value": "10"},
            {"title": "Isla Pelicano", "value": "11"},
            {"title": "Isla Rosario", "value": "12"},
            {"title": "⬅️ Volver", "value": "back"},
            {"title": "🏠 Inicio", "value": "inicio"},
        ],
        "en": [
            {"title": "Isla Grande", "value": "1"},
            {"title": "Isla Marina", "value": "2"},
            {"title": "Isla del Pirata", "value": "3"},
            {"title": "Isla del Sol", "value": "4"},
            {"title": "Isleta", "value": "5"},
            {"title": "Isla Arena", "value": "6"},
            {"title": "Isla Pavitos", "value": "7"},
            {"title": "Isla Lizamar", "value": "8"},
            {"title": "Isla Gigi", "value": "9"},
            {"title": "Isla Rosa", "value": "10"},
            {"title": "Isla Pelicano", "value": "11"},
            {"title": "Isla Rosario", "value": "12"},
            {"title": "⬅️ Back", "value": "back"},
            {"title": "🏠 Home", "value": "inicio"},
        ],
    },
    "location": {
        "es": [
            {"title": "🚤 Salgo desde Cartagena", "value": "1"},
            {"title": "🏝️ Ya estoy en las islas", "value": "2"},
        ],
        "en": [
            {"title": "🚤 Departing from Cartagena", "value": "1"},
            {"title": "🏝️ Already on the islands", "value": "2"},
        ],
    },
    "colombian": {
        "es": [
            {"title": "Si", "value": "1"},
            {"title": "No", "value": "2"},
        ],
        "en": [
            {"title": "Yes", "value": "1"},
            {"title": "No", "value": "2"},
        ],
    },
    "summary": {
        "es": [
            {"title": "❓ Sí, tengo más preguntas", "value": "ask"},
            {"title": "💵 Pagar en persona", "value": "cash"},
            {"title": "🔙 Volver al menú", "value": "back"},
        ],
        "en": [
            {"title": "❓ Yes, I have more questions", "value": "ask"},
            {"title": "💵 Pay in person", "value": "cash"},
            {"title": "🔙 Back to menu", "value": "back"},
        ],
    },
    "summary_referral": {
        "es": [
            {"title": "🧑‍💼 Contactar/Reservar", "value": "contact"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🧑‍💼 Contact / Book", "value": "contact"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "summary_contact": {
        "es": [
            {"title": "🧑‍💼 Contactar/Reservar", "value": "contact"},
            {"title": "❓ Tengo mas preguntas", "value": "ask"},
            {"title": "🙏 No, gracias", "value": "done"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🧑‍💼 Contact / Book", "value": "contact"},
            {"title": "❓ I have more questions", "value": "ask"},
            {"title": "🙏 No, thanks", "value": "done"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
    "itinerary_offer": {
        "es": [
            {"title": "🗺️ Ver itinerario completo", "value": "itinerary"},
            {"title": "💵 Pagar en persona", "value": "cash"},
            {"title": "🔙 Volver al menú", "value": "back"},
        ],
        "en": [
            {"title": "🗺️ View full itinerary", "value": "itinerary"},
            {"title": "💵 Pay in person", "value": "cash"},
            {"title": "🔙 Back to menu", "value": "back"},
        ],
    },
    "itinerary_offer_contact": {
        "es": [
            {"title": "🗺️ Ver itinerario completo", "value": "itinerary"},
            {"title": "🧑‍💼 Contactar/Reservar", "value": "contact"},
            {"title": "🔙 Volver", "value": "back"},
        ],
        "en": [
            {"title": "🗺️ View full itinerary", "value": "itinerary"},
            {"title": "🧑‍💼 Contact / Book", "value": "contact"},
            {"title": "🔙 Back", "value": "back"},
        ],
    },
}


def get_button_options(key: str, language: str) -> list[dict]:
    return [
        ButtonOption(title=option["title"], value=option["value"]).as_chatwoot_item()
        for option in BUTTON_OPTIONS.get(key, {}).get(language, [])
    ]


class DecisionTree:
    """
    Stateful decision tree that guides customers through predefined flows.
    No LLM calls — pure logic for Phase 1.
    """

    # Booking-cart menus that must NOT show a "Volver" button (owner decision
    # 2026-07-21): a certified diver who already said what they want shouldn't be
    # sent back into menus — changes are handled by natural language, and typing
    # "volver" still works (is_back). Info/navigation menus keep their Back.
    _CART_MENU_KEYS = frozenset({
        "mixed_entry", "mixed_ask_certification", "mixed_ask_certification_group",
        "mixed_add_activity", "mixed_companion_upsell", "mixed_add_cert_plan",
        "mixed_add_cert_multi_day", "mixed_add_cert_4dive_variant",
        "mixed_add_cert_1day_variant", "mixed_add_cert_2day_variant",
        "mixed_quantity", "mixed_preview_actions", "mixed_kids_age",
        "courses_menu", "courses_open_water_origin", "courses_open_water_time",
        "courses_advanced_menu", "courses_specialties_menu",
    })

    def set_quick_replies(self, state: ConversationState, key: str):
        if key == "tours_certified" and state.location == "island":
            options = self._island_certified_options(state.language)
        elif key == "info_tours_certified_menu" and state.location == "island":
            options = self._info_island_certified_options(state.language)
        elif key == "mixed_add_cert_multi_day" and state.location == "island":
            options = self._mixed_island_certified_multiday_options(state.language)
        elif key == "mixed_add_activity" and state.mixed_entry_path == "cert_beg":
            # Filtramos snorkel cuando entran por la rama de certificados + principiantes.
            options = [
                opt for opt in get_button_options(key, state.language)
                if opt.get("value") != "3"
            ]
        else:
            options = get_button_options(key, state.language)
        if key in self._CART_MENU_KEYS:
            options = [o for o in options if o.get("value") != "back"]
        state.quick_replies = options

    @staticmethod
    def _info_island_certified_options(lang: str) -> list[dict]:
        if lang == "es":
            options = [
                {"title": "🤿 2 inmersiones (1 día)", "value": "1"},
                {"title": "🤿 3 inmersiones (1 día)*", "value": "2"},
                {"title": "🤿 4 inmersiones (2 días)", "value": "3"},
                {"title": "🤿 5 inmersiones (2 días)", "value": "4"},
                {"title": "🤿 7 inmersiones (3 días)", "value": "5"},
                {"title": "🤿 9 inmersiones (4 días)", "value": "6"},
                {"title": "🧑‍💬 Servicio Privado", "value": "7"},
                {"title": "⬅️ Volver", "value": "back"},
                {"title": "🏠 Inicio", "value": "inicio"},
            ]
        else:
            options = [
                {"title": "🤿 2 Dives (1 day)", "value": "1"},
                {"title": "🤿 3 Dives (1 day)*", "value": "2"},
                {"title": "🤿 4 Dives (2 days)", "value": "3"},
                {"title": "🤿 5 Dives (2 days)", "value": "4"},
                {"title": "🤿 7 Dives (3 days)", "value": "5"},
                {"title": "🤿 9 Dives (4 days)", "value": "6"},
                {"title": "🧑‍💬 Private Service", "value": "7"},
                {"title": "⬅️ Back", "value": "back"},
                {"title": "🏠 Home", "value": "inicio"},
            ]
        return [ButtonOption(title=option["title"], value=option["value"]).as_chatwoot_item() for option in options]


    def _island_certified_options(self, lang: str) -> list[dict]:
        if lang == "es":
            return [
                {"title": "🤿 2 inmersiones (1 día)", "value": "1"},
                {"title": "🤿 3 inmersiones (1 día)*", "value": "2"},
                {"title": "🤿 4 inmersiones (2 días)", "value": "3"},
                {"title": "🤿 5 inmersiones (2 días)", "value": "4"},
                {"title": "🤿 7 inmersiones (3 días)", "value": "5"},
                {"title": "🤿 9 inmersiones (4 días)", "value": "6"},
                {"title": "🧑‍💬 Servicio Privado", "value": "7"},
                {"title": "🔙 Volver", "value": "back"},
            ]
        return [
            {"title": "🤿 2 Dives (1 day)", "value": "1"},
            {"title": "🤿 3 Dives (1 day)*", "value": "2"},
            {"title": "🤿 4 Dives (2 days)", "value": "3"},
            {"title": "🤿 5 Dives (2 days)", "value": "4"},
            {"title": "🤿 7 Dives (3 days)", "value": "5"},
            {"title": "🤿 9 Dives (4 days)", "value": "6"},
            {"title": "🧑‍💬 Private Service", "value": "7"},
            {"title": "🔙 Back", "value": "back"},
        ]

    def _mixed_island_certified_multiday_options(self, lang: str) -> list[dict]:
        if lang == "es":
            return [
                {"title": "🤿 3 inmersiones (1 día)*", "value": "1"},
                {"title": "🤿 4 inmersiones (2 días) · 4 diurnas", "value": "2"},
                {"title": "🤿 4 inmersiones (2 días) · 3 diurnas + 1 nocturna", "value": "3"},
                {"title": "🤿 5 inmersiones (2 días)", "value": "4"},
                {"title": "🤿 7 inmersiones (3 días)", "value": "5"},
                {"title": "🤿 9 inmersiones (4 días)", "value": "6"},
                {"title": "🔙 Volver", "value": "back"},
            ]
        return [
            {"title": "🤿 3 Dives (1 day)*", "value": "1"},
            {"title": "🤿 4 Dives (2 days) · 4 daytime dives", "value": "2"},
            {"title": "🤿 4 Dives (2 days) · 3 daytime + 1 night dive", "value": "3"},
            {"title": "🤿 5 Dives (2 days)", "value": "4"},
            {"title": "🤿 7 Dives (3 days)", "value": "5"},
            {"title": "🤿 9 Dives (4 days)", "value": "6"},
            {"title": "🔙 Back", "value": "back"},
        ]

    # ───────────────────── Cart-style mixed group flow ─────────────────────


        # NOTE: kids info is now collected INLINE before append (in
        # `_handle_mixed_add_qty` for the beginner branch), so we do NOT
        # invalidate here — that would wipe the answer the user just gave.
        # Invalidation lives in the add/modify entry handlers instead.



    # ─── Step handlers ───



    # Emojis numéricos para listas dinámicas (botones de modificar/quitar item)
    _NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


    # ─── Cambiar origen desde el carrito ───


    # ─── Final-question handlers ───
