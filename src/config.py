import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- OpenAI ---
    openai_api_key: str = ""
    # Modelos (25-sep): los valores por defecto de este bloque SON los de PRE, para que un
    # entorno sin estas variables (el .env.dev de cualquiera) no mida otro bot. PRE ademas
    # los fija en docker-compose.vps.yml, y tests/test_models_pinned.py falla si el compose
    # y estos valores se separan. Mapa de que usa cada uno: README.md, "LLM models".
    # Hasta el 25-sep este valia "gpt-4o" (el del orquestador ya retirado) y PRE lo
    # cambiaba desde el .env.pre del VPS, fuera del repo.
    # Lo usan condense_query, el juez de grounding, el detector de idioma y el resumen.
    openai_model: str = "gpt-5.4-mini"  # mod (18-oct): fuera de gpt-4; solo valor de reserva (cada pieza tiene su modelo); antes "gpt-4o-mini"
    # MOD (18-oct): cada pieza de `openai_model` con su modelo, para medirlas y cambiarlas una a una (la familia gpt-4 se
    # retira en enero). Mismo valor que `openai_model` mientras no se promocione otro.
    reescritura_model: str = "deepseek/deepseek-v4.1-flash"  # PROMOCIONADO 18-oct (mod-C, HISTORY 0.31.53); revert = "gpt-4o-mini"
    resumen_model: str = "deepseek/deepseek-v4.1-flash"  # PROMOCIONADO 18-oct (mod-C, HISTORY 0.31.53); revert = "gpt-4o-mini"
    idioma_model: str = "deepseek/deepseek-v4.1-flash"  # PROMOCIONADO 18-oct (mod-C, HISTORY 0.31.53); revert = "gpt-4o-mini"
    # Model for the narrow, structured LLM gap-filler extractor
    # (src/agents/llm_extractor.py, robustness Fases 1-3). Kept SEPARATE from
    # openai_model (then used by the action orchestrator, retired in 308488d): the extraction is a small
    # forced-tool-call task where a cheaper/faster model suffices. Measured on
    # docs/robustness/eval-set.json (64 cases): gpt-4o-mini = 98.4% vs gpt-4o =
    # 99.2% — the only difference is 1 extra `missed` (it abstains on a hard
    # implicit-count case rather than misfilling), so its failure mode is safe
    # (degrades to "regex-only / ask", never to a wrong value). ~15-30x cheaper
    # and faster per call. Revert to "gpt-4o" here if ever needed. See
    # docs/robustness/progress-log.md (Fase 4).
    extraction_model: str = "gpt-5.4-mini"  # mod (18-oct): fuera de gpt-4; solo valor de reserva (cada pieza tiene su modelo); antes "gpt-4o-mini"
    # mod-3 (18-oct, fase MOD: la familia gpt-4 se retira en enero): cada pieza de `extraction_model` con su modelo,
    # para medirlas y cambiarlas una a una. Mismo valor que `extraction_model` mientras no se promocione otro.
    senales_model: str = "deepseek/deepseek-v4.1-flash"  # PROMOCIONADO 18-oct (mod-F, HISTORY 0.31.56); revert = "gpt-4o-mini"
    red_extractor_model: str = "gpt-6-luna"  # PROMOCIONADO 18-oct (mod-F, HISTORY 0.31.56); revert = "gpt-4o-mini"
    resolutor_model: str = "anthropic/claude-haiku-5.5"  # PROMOCIONADO 19-oct (mod-G2, HISTORY 0.31.57); revert = "gpt-5.4-nano"
    acuse_model: str = "gpt-5.4-nano"  # PROMOCIONADO 18-oct (mod-F, HISTORY 0.31.56); revert = "gpt-4o-mini"
    notas_model: str = "deepseek/deepseek-v4.1-flash"  # PROMOCIONADO 18-oct (mod-F, HISTORY 0.31.56); revert = "gpt-4o-mini"
    # ex-4 (fase EX, 12-oct): modelo del extractor "LLM primero" (src/agents/extractor_turno.py). Medido en PRE con el
    # banco ex0: gpt-4.1-mini 88-89 % de datos y 4,5 % de casos con invento en diseño; en el CIEGO 90,6 % y 5,6 % (hoy
    # 90,6 % y 21,8 %), p50 ~1,0 s. gpt-4o-mini parecido y algo peor; Luna inventa menos pero tarda 2,1-2,4 s.
    extractor_turno_model: str = "anthropic/claude-haiku-5.5"  # PROMOCIONADO 18-oct (mod-F, HISTORY 0.31.56); revert = "gpt-4.1-mini"
    # 18-oct (mod-2): RESPALDO del extractor (`llm_client.crear_con_respaldo`): si no contesta en estos segundos, la
    # misma petición va a este modelo y gana la primera. Vacío = sin respaldo. Ronda mod-F: Haiku por OpenRouter tuvo
    # 2 colas de 4-5 s en 47 turnos de reserva (p50 1,14 s, p90 1,67 s); gpt-5.4-mini es de OpenAI (otro proveedor).
    extractor_respaldo_modelo: str = "gpt-5.4-mini"  # ENCENDIDO 18-oct con mod-F (HISTORY 0.31.56); revert = ""
    extractor_respaldo_segundos: float = 2.0
    # EX-EST-2 (15-oct): regla del RAG: no sabe la fecha ni la hora de hoy ('ya pasó esa hora', 'como todavía estás a
    # tiempo' sobre el cierre de las 4:30, rondas est4-B/est5-B). prompts/info.RAG_SIN_HORA_*. DESCARTADO 15-oct (APAGADO):
    # en est6-B el RAG, sin fecha, calculo igual que 'desde el 3 de abril de 2025 ya pasaron mas de dos años' (falso).
    # El arreglo por causa es darle al RAG la fecha y la hora de hoy (ex-9b).
    rag_sin_hora: bool = False
    # EX-RAG-3 (14-oct): cuando el juez de grounding rechaza, cada frase rechazada tiene que traer la cita literal del
    # contexto que la respalda (el codigo comprueba la cita y que sus cifras y enlaces estan en el contexto); si todas
    # la traen, la respuesta pasa. El juez rechazaba ~6 % de respuestas, varias correctas (politicas). Solo corre al
    # rechazar. juez_segunda_opinion.respaldadas_con_cita. DESCARTADO 14-oct (APAGADO): el banco del revisor
    # (scripts/banco_revisor.py) mostro que deja pasar inventos: con la cita se escapan 12/30 errores sembrados
    # (sin ella 0/30), porque una cita real que respalda solo PARTE de la frase la daba por buena ("en un grupo mixto
    # los colombianos pagan en pesos" con la cita "pagan en pesos los colombianos"). Sin la cita: 0/30 rechazos injustos.
    juez_revisa_con_cita: bool = False
    # 18-oct (ronda mod-D, reserva-solo-link): el resolutor no fija un valor con una respuesta que se contradice ("no,
    # buceé hace poco" a "¿Eres buzo certificado?"). prompts/booking.SLOT_RESOLVER_CONTRADICCION. APAGADO.
    # ex-9b paso 4: los días cerrados (25 de diciembre y 1 de enero) los contesta el RAG, que lleva siempre las políticas
    # (`rag_politicas_en_contexto`), en vez del texto fijo que dispara `_CLOSED_DATE_RE` y se come el resto del mensaje.
    # Replay del golden: 0 cambios (ningún diálogo visible los nombra); pero sin el texto fijo, "quiero bucear el 25 de
    # diciembre, somos 2" no llega al RAG (Jev: no pregunta nada) y nadie avisa del cierre. nucleo/availability.
    # APAGADO hasta medirlo.
    dias_cerrados_por_rag: bool = False
    # ex-9b paso 6 (19-oct): los últimos datos de "entender al cliente" que decidía solo el regex, al extractor del turno
    # (campo nuevo con su cita; APAGADO = ni el campo ni su regla, la llamada de siempre). Si el extractor falla, lo de hoy.
    # - La duración: los días que quiere BUCEAR y los de su estancia, por separado (`dias_de_buceo`, `dias_de_estancia`).
    #   Manda lo que dice de bucear ("estaré del 5 al 9 pero solo quiero bucear un día" = un día) y, si solo dice cuánto
    #   estará, la estancia (decisión de Gadea, 19-oct). El contrato no cambia: `detected_duration` = single_day /
    #   multi_day. Fuera los falsos positivos del regex ("embarazada de 4 meses", "3 días esperando").
    #   nucleo/extractor._poner_duracion y la respuesta corta a "¿un día o varios?" (nucleo/routing).
    # ex-9b (19-oct): el reparto del extractor como lista de pares {actividad, personas}: con el objeto de 10 enteros
    # opcionales y los campos del paso 6, Anthropic rechazaba la llamada ("compiled grammar is too large") y
    # contestaba siempre el respaldo (ronda ex9b-4). APAGADO hasta medirlo.
    reparto_en_pares: bool = False
    # ex-9b (19-oct, decisión de Gadea): los campos del paso 6 en una SEGUNDA llamada al extractor, a la vez que la de
    # siempre (el esquema de todo junto no cabía en Haiku). APAGADO hasta medirlo.
    paso6_en_llamada_aparte: bool = True  # PROMOCIONADO 20-oct (ex9b-8); su espera, como mucho 1,5 s más; revert = False
    duracion_por_extractor: bool = True  # PROMOCIONADO 20-oct (ronda ex9b-8: 98,7 % 29/32, 0 regresiones; HISTORY 0.31.68); revert = False
    # - Las edades (`edades`), con su cita; el regex solo valida la cifra. `fill_gaps` ya no las rellena si el extractor
    #   leyó el mensaje. nucleo/extractor._poner_edades y la respuesta corta a "¿qué edades tienen?".
    edades_por_extractor: bool = True  # PROMOCIONADO 20-oct (ronda ex9b-8: 98,7 % 29/32, 0 regresiones; HISTORY 0.31.68); revert = False
    # - El plan elegido: si el mensaje ACEPTA el paquete que el bot acaba de proponer (`acepta_propuesta`, solo cuando el
    #   bot propuso uno), se da por elegido y sigue la reserva; preguntar el precio no es aceptar. Antes,
    #   `_CONFIRMS_DESCRIBED_PACKAGE_RE` ("quiero este paquete"). nucleo/routing._paquete_confirmado.
    plan_elegido_por_extractor: bool = False  # NO (ex9b-5, manual-duracion-curso): la descripción del curso Open Water
    # ("4 inmersiones") se tomaba por la propuesta de un paquete y "para mí" lo elegía: Curso Referido. 0 usos en PRE.
    # - Alguien que se SUMA a un grupo ya sabido ("mi hermano también viene, hace snorkel" sobre 2 buzos): el extractor
    #   ve el reparto sabido aunque no esté guardado ({buceo: 2} = la actividad para todos) y devuelve el nuevo; y el atajo
    #   de "reparto completo" deja pasar la red de acompañantes si Jev está seguro de que se suma alguien
    #   (`companion_joins`). nucleo/extractor._sabido_para_extractor y nucleo/extraction.
    reparto_al_sumarse_alguien: bool = True  # PROMOCIONADO 20-oct (ex9b-8): por el punto único del acompañante y con Jev; revert = False
    # - Las notas del RAG sobre OTRA persona del grupo ("el minicurso no certifica", "certificado inactivo = refresher")
    #   salen del estado (`otro_sin_certificar`, `otro_certificado_inactivo` del extractor, con cita) en vez de un regex
    #   sobre todo lo que escribió el cliente; si el extractor no leyó algún mensaje, el regex de siempre.
    #   rutas/contexto_rag.
    notas_rag_desde_estado: bool = True  # PROMOCIONADO 20-oct (ronda ex9b-8: 98,7 % 29/32, 0 regresiones; HISTORY 0.31.68); revert = False
    # gen-8 (21-oct): el ejemplo del acuse para reconocer un dato iba en plural ("none of you are Colombian") y lo
    # copiaba a quien va solo; con el flag, la regla de usar las palabras y el número del cliente. APAGADO.
    acuse_en_su_numero: bool = True  # PROMOCIONADO 21-oct (ronda sin desplegar gen8-B 97,9 % 27/32 frente a gen8-A 97,0 % 26/32; el que empeora es del RAG; HISTORY 0.31.79); revert = False
    # gen-8 (21-oct): la actividad de la que el cliente PREGUNTA sin elegirla ("en el minicurso, ¿el equipo está
    # incluido?", "si hiciera el Advanced…"), leída por el extractor con su cita. Mientras no elige, la pregunta de la
    # actividad le ofrece esa en vez del menú de 4 (textos-B: "Which one are you leaning toward — diving, a
    # mini-course…?" a quien llevaba 3 turnos preguntando por el Open Water). APAGADO.
    actividad_de_la_pregunta: bool = True  # PROMOCIONADO 21-oct (con `acuse_en_su_numero`, misma ronda gen8-A/B; banco gen-8: menú de 4 a quien ya hablaba de una actividad 2/24 -> 0/24; HISTORY 0.31.79); revert = False
    # gen-4 (21-oct): VIVIR en Colombia no es ser residente (G9, causa 6). El extractor leía "I live in Bogotá" o "sí,
    # vivo aquí" como colombiano (COP) en el banco docs/robustness/gen/banco_gen4_moneda.py (5/30 bien). Con el flag:
    # cuenta quien dice que es colombiano, viva donde viva, o que tiene cédula de extranjería (policies.json,
    # colombian_pricing; sin cédula = USD, decisión de Álvaro del 17-oct); vivir, trabajar o haber nacido allí no dice
    # ni lo uno ni lo otro (nacer allí no da la nacionalidad: Gadea, 21-oct). Y la pregunta nombra la cédula. APAGADO.
    vivir_no_es_residir: bool = True  # PROMOCIONADO 21-oct (ronda sin desplegar gen4-B2 frente a gen4-A2; las regresiones no pasan por la nacionalidad; banco del extractor 65/90 -> 86/90; HISTORY 0.31.81); revert = False
    # gen-14 (21-oct): «Somos de Cali y estamos alojados en Isla Grande» o «soy paisa» no contaban como colombianos (la
    # regla de vivir_no_es_residir ponía «estar» entre lo que no dice la nacionalidad) y el bot cotizaba en USD. Con el
    # flag, decir de qué ciudad o región de Colombia es (o su gentilicio) es ser colombiano; alojarse o viajar no dice
    # nada. Solo actúa con vivir_no_es_residir encendido. APAGADO.
    gentilicio_es_colombiano: bool = True  # PROMOCIONADO 21-oct (core gen14-A 96,5 % 26/32 frente a gen14-B 97,8 % 27/32; rejuzgado x3: 3 mejoras reales, 0 regresiones de la nacionalidad; HISTORY 0.31.85); revert = False
    # gen-14 (21-oct): en un turno con pregunta, el RAG contesta (o se adelanta) antes de que la extracción apunte la
    # nacionalidad que dice ESE mensaje, y a «Somos de Cali… ¿cuánto vale?» le daba USD. Con el flag, el RAG recibe la
    # nacionalidad que ya leyó la extracción del turno (conversational_core._con_la_nacionalidad_del_mensaje). APAGADO.
    rag_espera_la_nacionalidad: bool = True  # PROMOCIONADO 21-oct (con gentilicio_es_colombiano, misma ronda gen14-A/B); revert = False
    el_verbo_no_la_ciudad: bool = True  # PROMOCIONADO 22-oct (arq-1f: banco de moneda 87/93 -> 93/93; banco fijo p6 0/3 -> 3/3; HISTORY 0.31.92); revert = False
    cache_anthropic: bool = True  # PROMOCIONADO 22-oct (arq-2b: core A/B2 coste -31 %, turno p50 4,25 -> 4,07 s, extractor p50 0,78 -> 0,68 s; HISTORY 0.31.92); revert = False
    cache_anthropic_proveedor: str = "amazon-bedrock"  # ARQ-2b: con la caché, el proveedor de Haiku que va primero (los demás de respaldo). Sonda 22-oct (7 llamadas cada uno): bedrock caché 7/7 y p50 1,98 s (sin caché 1,94 s); anthropic 7/7 y 2,29 s; vertex 3/7
    # gen-15 (21-oct): los hoteles de las islas que da la base (policies.json other_island_hotels: Mulata, Rosario de
    # Mar, Eco Hotel Las Palmeras…) no estaban en la lista del bot ni en la pregunta del lugar de Jev, y el bot volvía a
    # preguntar desde dónde sale. Con el flag, el extractor y Jev los conocen (extractor_turno.HOTELES_DE_LA_BASE).
    # APAGADO.
    hoteles_de_la_base: bool = True  # PROMOCIONADO 21-oct (gen-15: banco Jev 15/33 -> 30/33, repregunta del lugar 5/10 -> 0/10; las regresiones de la core, repetidas x2, no pasan por el lugar; HISTORY 0.31.86); revert = False
    # gen-15 (21-oct): «We booked 3 nights at Mulata» salía en Jev como «ya tiene una reserva con nosotros» y el turno
    # iba a posventa (sin preguntas de la reserva). Con el flag, la pregunta YA_RESERVADO dice que reservar el hotel,
    # el alojamiento o el vuelo no es una reserva con el centro (jev_router._YA_RESERVADO_Q_SIN_HOTEL). APAGADO.
    reserva_de_hotel_no_es_nuestra: bool = True  # PROMOCIONADO 21-oct (con hoteles_de_la_base, gen-15); revert = False
    # gen-16 (21-oct): a quien quiere TERMINAR aquí un Open Water empezado (el extractor lee el Referido) se le
    # preguntaba «¿ya tienen el Curso referido o quieren sacarla?» porque nombraba «Open Water». Con el flag, no se
    # pregunta (nucleo/extraction._flag_cert_or_course). APAGADO.
    referido_no_pregunta_nivel: bool = True  # PROMOCIONADO 21-oct (gen-16: banco 2/2 -> 0/2; core sin regresiones del Referido; HISTORY 0.31.86); revert = False
    # gen-4 (21-oct, decisión de Gadea, Coral #862): el cierre para colombianos (pasa a un asesor que coordina el pago en
    # COP) decía "para confirmar disponibilidad" (siempre hay) y "Como son colombianos/residentes" también a quien va
    # solo. Con el flag, sin disponibilidad y en el número del cliente, sin género (nucleo/slotfill_close._finalize).
    # Y el RAG, que a un colombiano ya conocido le daba el link de reserva antes del cierre, sabe que su pago lo
    # coordina un asesor (rutas/contexto_rag). APAGADO.
    pago_colombiano_con_asesor: bool = True  # PROMOCIONADO 21-oct (con `vivir_no_es_residir`, misma ronda gen4-A2/B2; decisión de Gadea, Coral #862; HISTORY 0.31.81); revert = False
    # Model for the RAG answer-generation call only (rag_agent.py
    # `_answer_with_llm`). Kept SEPARATE from `openai_model` (used broadly
    # across the bot) so we can trial a stronger model for JUST this call --
    # scoped blast radius, same pattern as `extraction_model` above. Empty
    # string means "use `openai_model`". En PRE desde el 2026-09-03 (antes solo en
    # su .env.pre; default desde el 25-sep). Hallazgo en vivo (2026-09-03): gpt-4o-mini
    # ignora la regla de "certificado-pero-inactivo" (ver
    # docs/multi-agent-refactor-plan.md §7) pese a tenerla correctamente
    # inyectada en el contexto, en ~1/3 de las repeticiones -- un techo real
    # de fiabilidad del modelo, no un bug de codigo. gpt-5-mini/o-series NO
    # sirven aqui sin cambios de codigo adicionales (no soportan
    # `temperature`, usan `reasoning_effort`); cualquier modelo puesto aqui
    # debe seguir aceptando `temperature`/`max_tokens` como hoy (gpt-4.1-mini,
    # gpt-4o, etc.).
    # 8-oct (cambio de modelos): ronda core A/B con GPT-6 Luna en todo (modelos-A/B): calidad igual (94,7 %), p95 de los
    # turnos 5,4 -> 8,6 s (cola de Luna). Extraccion y secundarias vuelven a gpt-4o-mini. La respuesta del RAG: ver
    # `rag_respaldo_*` (Luna con respaldo).
    rag_answer_model: str = "gpt-6-luna"  # PROMOCIONADO 8-oct con respaldo (rag_respaldo_*); HISTORY 0.31.0
    openai_embedding_model: str = "text-embedding-3-small"
    # Model used to transcribe incoming customer voice notes (see
    # src/channels/audio.py). gpt-4o-mini-transcribe is cheaper/better than
    # whisper-1; switch to "whisper-1" if an older SDK is in play.
    # MOD-6 (18-oct, decisión de Gadea: "decide tú"): gpt-transcribe con vocabulario. PROMOCIONADO (HISTORY 0.31.53).
    openai_transcription_model: str = "gpt-transcribe"
    rag_top_k: int = 8
    rag_min_score: float = 0.40
    # Minimum raw ts_rank_cd score for a BM25-only hit to count as "confident".
    # Vector hits gate on rag_min_score (cosine); lexical hits gate on this.
    rag_min_bm25_rank: float = 0.05
    # Fuentes del indice que la busqueda ignora, separadas por coma (p. ej. "services").
    # Nacio en g-7 para medir el RAG sin los chats antiguos (conversations.json, retirados
    # en el paso 4, 2026-09-24); se queda como interruptor generico sin reindexar.
    rag_exclude_sources: str = ""
    # r6-1 (Fase R6): tiempo maximo de UNA llamada al LLM, en segundos.
    #
    # Por que: el cliente de OpenAI trae por defecto `Timeout(connect=5, read=600)`
    # con `max_retries=2`, o sea hasta ~30 min colgado en una sola llamada. Medido
    # en vivo: `eval_rag_answers` se quedo 5 h 44 min con 40 s de CPU, parado en el
    # 4º de 39 casos. En produccion eso es un turno que NUNCA responde.
    #
    # 30 s es margen de sobra: el turno ENTERO va hoy a p95 9 s con hasta 7-10
    # llamadas (linea base v7), asi que ninguna llamada legitima se acerca. Se
    # aplica en un unico punto, `llm_client.trace_openai`, que es por donde pasan
    # todas. Subirlo por entorno si algun dia hay una llamada legitimamente larga.
    llm_timeout_seconds: float = 30.0

    # U3 (u3-1, paso 1): las 9 señales del router con Jev (TypeSafe, vía el Decisions API
    # de OpenRouter) en vez de con el LLM. Evaluado en l2-4 (2026-09-24): mejor que el
    # router LLM en la batería (32/37 frente a 30/37, seguridad 11/11 frente a 8/11) y
    # ~0,27 s frente a ~1,3 s. Decisión de Gadea: Jev para U3 (en PRE sí; la privacidad
    # para PRO se decide antes). APAGADO por defecto; sin clave o si Jev falla o tarda
    # más de `jev_timeout_seconds`, se usa el router LLM de siempre. Ver
    # `src/agents/jev_router.py`.
    jev_router_enabled: bool = False
    openrouter_api_key: str = ""
    # Versión fija: si Jev cambia de versión, el comportamiento no cambia sin medirlo.
    jev_model: str = "typesafe/jev-1.13"
    # p95 medido ~0,37 s; en l2-4 1 de ~600 llamadas tardó >30 s (API en alpha).
    jev_timeout_seconds: float = 2.0

    # gen-6 (21-oct, Gonzalo con Claude): con G3-06, "estamos hospedados en Barú" se quedaba sin origen (Jev "none", el
    # extractor lo descartaba y con `lugar_con_dos_lectores` un "none" de Jev tumba al extractor) y el bot volvía a
    # preguntar "¿desde dónde saldrías?" (banco docs/robustness/gen/dialogos-gen6.json 2/2). La política (policies.json):
    # quien se aloja en Barú o Playa Blanca sale desde Cartagena. Con el flag, los tres lectores del lugar (Jev
    # customer_place, extractor_turno y el resolutor de la pregunta del origen) lo leen como 'cartagena'. Va con
    # `baru_no_es_rosario`. APAGADO.
    baru_sale_de_cartagena: bool = True  # PROMOCIONADO 21-oct (ronda sin desplegar gen6-B3 97,4 % 26/32 frente a gen6-A3 97,0 % 26/32; banco Barú 0/8 -> 8/8; HISTORY 0.31.81); revert = False
    # - gen-6 (21-oct): la puerta del origen quita las frases con importe; si el RAG escribía "…cuesta:", una línea en
    #   blanco y la lista de precios, el título quedaba colgado ("La salida de 2 inmersiones cuesta:" y luego la pregunta
    #   del origen). conversational_core._sin_importes. APAGADO.
    origen_sin_titulo_suelto: bool = True  # PROMOCIONADO 21-oct (con `baru_sale_de_cartagena`, misma ronda gen6-A3/B3; HISTORY 0.31.81); revert = False
    # (antes, mod-G/mod-H: APAGADO; con la regla de is_certified afinada sigue el
    # minicurso a 183 USD en reserva-solo-link: el extractor toma el «no» de «no, buceé hace poco» (a «¿eres buzo
    # certificado?») como no certificado; arreglado con «buceé hace poco» en IS_CERTIFIED_DICHO_*.)
    # mod-2 (18-oct, decisión de Gadea, revoca `extractor_precio_elige`): preguntar el precio de un producto es una duda:
    # no elige la actividad, no dice que quiera bucear ni que sea certificado. Cambia a la vez las cuatro frases del
    # extractor que hablan del precio (ver extractor_turno._PRECIO_NO_ELIGE). APAGADO hasta medirlo.
    precio_no_elige: bool = False  # mod-G (18-oct): repreguntas en 5 diálogos del core (quita deducciones válidas); a afinar

    # Modelo del juez de grounding v3 (el de siempre desde s4-25: sin flag). 28-sep (HISTORY 0.29.66): v3 con
    # gpt-4.1-mini 48/70 y gpt-4o-mini 37/70 frente a 70/70, y NO más rápidos: se quedó gpt-4.1.
    grounding_v3_model: str = "deepseek/deepseek-v4.1-flash"  # PROMOCIONADO 18-oct (mod-C, HISTORY 0.31.53); revert = "gpt-4.1"
    # J1 (1-oct): con un modelo de razonamiento como juez (GROUNDING_V3_MODEL=gpt-5-mini), su esfuerzo de razonamiento.
    grounding_reasoning_effort: str = "low"
    # 8-oct (cambio de modelos, fase 0): esfuerzo de razonamiento para los modelos gpt-6 cuando la llamada no lo pide.
    # GPT-6 Luna razona por defecto ("medium"); "none" = sin razonamiento, como los modelos de hoy (medido: 0 tokens
    # de razonamiento, misma latencia total que gpt-4.1-mini con el prompt del RAG). Ver `llm_client.adaptar_parametros`.
    razonamiento_modelos_nuevos: str = "none"
    # 8-oct (cambio de modelos): el texto que sale a Chatwoot/WhatsApp se pasa a formato de WhatsApp (`**x**` -> `*x*`,
    # `[texto](url)` -> `texto: url`, titulos -> negrita). GPT-6 Luna escribe Markdown de documento y WhatsApp lo ensenaba
    # con los asteriscos. Solo presentacion; lo que ya esta en formato WhatsApp no cambia. `channels/formato.py`.
    formato_whatsapp: bool = True
    # 8-oct: respuesta del RAG con RESPALDO (`rag_agent.generar_con_respaldo`): si el modelo principal
    # (`rag_answer_model`) no ha terminado en `rag_respaldo_segundos`, se lanza la misma peticion a `rag_respaldo_modelo`
    # en paralelo y se usa la primera que termine. Corta la cola de GPT-6 Luna. Vacio o 0 = sin respaldo.
    # PROMOCIONADO 8-oct: ronda respaldo-A/B (misma franja): calidad 95,6 -> 94,7 % (ruido: las regresiones son del
    # flujo y del juez), turnos p50 +0,07 s, p95 +0,6 s, maximo 9,7 -> 7,6 s; turnos de RAG p50 +0,8 s; el respaldo
    # salto en el 10 % y corto las colas de 11-13 s. Revert = rag_answer_model "gpt-4.1-mini" y esto vacio.
    rag_respaldo_modelo: str = "deepseek/deepseek-v4.1-flash"  # PROMOCIONADO 18-oct (mod-5, mod-E, HISTORY 0.31.55); revert = "gpt-4.1-mini"
    rag_respaldo_segundos: float = 3.0
    # r6-1(d) (17-oct, salir de gpt-4.1; acordado con Gadea): el respaldo del RAG es otra petición al MISMO modelo
    # (Luna) a los `rag_respaldo_segundos`, en vez de gpt-4.1-mini. APAGADO hasta medir latencia (p95/máx) y calidad.
    respaldo_mismo_modelo: bool = False
    # CAL-A1 (16-oct): la respuesta del RAG se redacta a temperatura 0 (hoy 0,3). 18 de los 56 fallos del RAG en ex-10
    # eran azar (docs/robustness/investigacion/diagnostico-73-fallos.md). APAGADO hasta medirlo (banco de fallos, 3 reps).
    rag_temperatura_cero: bool = True  # PROMOCIONADO 21-oct (ord-4: core ord4-A 96,5 % 25/32 frente a ord4-B 97,4 % 26/32, 3 mejoras reales y 0 regresiones; banco de omisiones 15 -> 17/54; HISTORY 0.31.86); revert = False
    # CAL-A2 (16-oct): antes de redactar, un PLAN (src/agents/rag_plan.py) saca la lista de lo que el cliente pregunta y la
    # redacción la contesta punto por punto. APAGADO hasta medirlo.
    rag_plan_primero: bool = False
    # CAL-A3 (16-oct): tras el revisor de siempre, se comprueba que la respuesta cubre cada punto del plan; si falta
    # alguno, se reintenta una vez (y si el reintento sale peor, vale la primera). APAGADO hasta medirlo.
    rag_revisor_completitud: bool = False
    # CAL-A4 (16-oct): tras el revisor de siempre, otro lee lo mismo que él y busca como mucho 2 AVISOS que el cliente
    # necesita y la respuesta no da (no le da tiempo, el minicurso no certifica, falta un documento...); si falta alguno,
    # un reintento con ellos (si sale peor, vale la primera). A1-A3 no mejoraron estos fallos. APAGADO hasta medirlo.
    rag_revisor_avisos: bool = False
    # CAL-A5 (16-oct, CAL-A reabierta por Gadea): los AVISOS que el cliente necesita y no pregunta, como DATOS con
    # condiciones (`data/knowledge_base/avisos.json`) que elige el CÓDIGO con el estado de la conversación
    # (`src/flows/avisos.py`), no un modelo: A4 los elegía mal (metía relleno) con el mecanismo bueno. Van al RAG como
    # puntos obligatorios y el revisor de completitud comprueba que estén. Banco CAL-A 16×3: 47/48 → 37/48, tres
    # casos arreglados 3 de 3. **REVERTIDO 17-oct tras la ronda A/B del core** (`2026-10-16-cal-A` vs `-cal-B`): el
    # banco mejora pero el golden EMPEORA (97,4 % → 96,0 % de criterios; 2 mejoras reales y 6 regresiones reales). El
    # daño es de desplazamiento: los avisos obligatorios ocupan el sitio de lo que la respuesta ya tenía que decir (la
    # peor regresión: se queda sin dar el enlace de reserva) y desdibujan datos ("varios días" por 2 días, "tu
    # reserva" sin reserva). Ver docs/robustness/cal/cal-a5-avisos-condicionados.md §9.
    # **NO PROMOCIONADO (17-oct), con DOS rondas del golden core medidas**: A (apagado) 97,4 % de criterios y 27/32
    # diálogos sin fallo; B (2 avisos) 96,0 % y 25/32; B2 (refinados: 1 aviso, primero lo que pidió el cliente) 96,1 %
    # y 24/32. El banco mejora (47/48 → 37/48) y el golden empeora: el aviso obligatorio compite con lo que la
    # respuesta ya tenía que decir. Se queda APAGADO y el código se conserva con las tres medidas apuntadas; lo que
    # habría que probar está en docs/robustness/cal/cal-a5-avisos-condicionados.md §10.
    avisos_condicionados: bool = False
    # Modelo del revisor de `avisos_al_final` (vacío = `rag_plan_model`). Va a la vez que el juez de grounding.
    # Medido en local (17-oct, 5 casos del banco + los 93 turnos de la ronda core cal-D): gpt-4.1-mini acierta 4 de 5
    # pero añade aviso en 64 de 93 turnos (relleno); gpt-4.1 y GPT-6 Luna (sin razonamiento) aciertan 4 de 5 y añaden
    # en 20-24 y 24-27. Latencia, a la vez que el juez: gpt-4.1 no añade nada (p50 0,0 s) y Luna p50 0,4 s / p90 0,8 s.
    # DECISIÓN DE GADEA (17-oct): Luna, el último modelo y el más barato.
    avisos_al_final_model: str = "gpt-6-luna"
    # G3-05 (18-oct, decisión de Gadea: DeepSeek, el más barato y rápido): el modelo de la pregunta sola
    # (`busqueda_con_la_pregunta_sola`). La familia gpt-4 se retira en enero. Medido con 12 mensajes en es/en/pt/fr x3 y la
    # instrucción endurecida: deepseek-v4.1-flash 36/36, 0,45 s de mediana (OpenRouter, proveedores de EE. UU., sin
    # retención de datos, como Jev); Luna 36/36 0,78 s; gpt-5.4-mini 36/36 0,68 s; Haiku 5.5 36/36 0,79 s; gpt-4o-mini no
    # traducía el portugués. En PRE (sonda), todos traen la FAQ de nadar: el modelo no cambia la búsqueda, sí la latencia.
    pregunta_sola_model: str = "deepseek/deepseek-v4.1-flash"
    # Modelo del plan y de la comprobación de completitud (llamadas cortas, temperatura 0).
    rag_plan_model: str = "gpt-6-luna"  # mod (18-oct): fuera de gpt-4 (flags del plan apagados); antes "gpt-4.1-mini"
    # 8-oct (prueba de DeepSeek): un modelo con prefijo de proveedor ("deepseek/deepseek-v4.1-flash") sale por
    # OpenRouter (`llm_client.parametros_openrouter`), solo por estos proveedores (separados por comas, por latencia,
    # sin retención de datos). "deepseek" = la API oficial (servidores en China: solo para pruebas sin datos de
    # clientes); "baseten,fireworks/us,coreweave" = EE. UU. Vacío = cualquiera, por latencia.
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # 18-oct (Gadea: probar Haiku): + Anthropic, Google Vertex y Amazon Bedrock, empresas de EE. UU., con las mismas
    # condiciones de mod-7 (sin retención ni entrenamiento, datos personales tapados). PROMOCIONADO (HISTORY 0.31.56).
    openrouter_proveedores: str = "baseten,fireworks/us,coreweave,google-vertex,anthropic,amazon-bedrock"
    # OpenRouter solo deja usar la API oficial de DeepSeek si se acepta que ENTRENEN con los datos (su politica "Paid
    # model training"). Apagado = nunca. Solo para pruebas con datos anonimizados; nunca con clientes reales.
    openrouter_permitir_entrenamiento: bool = False
    # 18-oct (ronda mod-G: la clave de OpenRouter llegó a su límite y el revisor dejaba pasar las respuestas sin
    # revisar): si una llamada a OpenRouter falla, se repite con este modelo de OpenAI (llm_client._por_proveedor).
    # Solo actúa cuando OpenRouter falla. Vacío = sube el error como antes.
    respaldo_si_openrouter_falla: str = "gpt-5.4-mini"
    # mej-7 (23-oct, Gonzalo con Claude, encargo de Gadea #1566): si OpenRouter contesta 401, 402 o 403 (la clave o el
    # crédito: el 21-oct, ronda respaldo-luna, 401 en las 93 vueltas y en cada pieza), se deja de llamar a OpenRouter
    # estos segundos: cada pieza va directa a su respaldo de OpenAI y Jev se salta (decide el router LLM), en vez de
    # perder ~0,25 s por llamada y repetir el fallo en cada pieza de cada turno. Se avisa una vez por corte en el log
    # (ERROR) y en [TURN_METRICS] (`openrouter=cortado`). 0 = apagado (hoy: se intenta siempre y se repite en OpenAI).
    openrouter_corte_segundos: float = 300.0  # PROMOCIONADO 23-oct (mej-7, decisión de Gadea: 300 s; HISTORY 0.31.98); revert = 0.0
    # ex-9b (19-oct, ronda ex9b-3): una llamada a OpenRouter (la reescritura de DeepSeek) se quedó colgada 30 s, el
    # límite general, y el turno tardó 34 s. Si OpenRouter no ha contestado en estos segundos, se lanza la misma
    # petición por OpenAI (`respaldo_si_openrouter_falla`) y gana la primera que termine bien, para todas las piezas.
    # 0 = apagado (el respaldo solo cuando OpenRouter falla, como hasta hoy).
    openrouter_respaldo_segundos: float = 5.0  # PROMOCIONADO 19-oct (ex9b-4: saltó 1 vez, ganó el respaldo); revert = 0.0
    # gen-1 + gen-3 (20-oct, fase GEN; docs/robustness/gen/gen1-diagnostico.md). El RAG a solas cubre el 96 % de los
    # datos; en una conversación el dato se perdía en el PASE por tema sensible: la respuesta fija se comía el resto del
    # mensaje ("¿cómo estará el mar el jueves? ¿el precio incluye el equipo?" -> solo "te conecto con el equipo").
    # - Contestar lo contestable y luego pasar (médico y clima): el RAG contesta las OTRAS preguntas del mensaje, sin
    #   tocar el tema sensible, y después va la línea del pase. escalation_agent._lo_contestable.
    # - gen-13 (21-oct): lo mismo para CUALQUIER pase a un asesor (contacto, pago, grupo privado, cambios de reserva,
    #   necesidades especiales, post-venta, «pásame con alguien»), en un solo sitio: el cierre del turno
    #   (supervisor.route_message -> escalation_agent.lo_contestable_en_cualquier_pase). Causa 2 de G10/G9 (~27 fallos).
    #   Las emergencias, las quejas, los datos personales y el fallo técnico se pasan solos.
    contesta_antes_de_cualquier_pase: bool = True  # PROMOCIONADO 21-oct (banco 4/16 -> 16/16; core gen13-A 97,4 % 27/32 frente a gen13-B 97,4 % 26/32, 0 regresiones del flag; HISTORY 0.31.84); revert = False
    # 22-oct (Gonzalo con Claude; propuesta #1252, Gadea #1255): la palabra de control «NADA» de contestar antes del
    # pase le llegaba al cliente cuando el aviso al final iba pegado detrás (se miraba len < 30): 8 turnos en las rondas
    # del 21-22, también en G10. Con el flag cuenta la primera línea entera. escalation_agent._es_nada. APAGADO.
    nada_en_primera_linea: bool = True  # PROMOCIONADO 22-oct (Gonzalo: el NADA de contestar antes del pase ya no llega al cliente; 8 turnos en las rondas del 21-22; HISTORY 0.31.92); revert = False
    # - Textos fijos del flujo en el español de Cartagena (decisión de Gadea, 20-oct): vosotros -> ustedes, sin género
    #   supuesto y sin "podemos recogerte saliendo desde Cartagena" (no hay recogida en Cartagena). flows/textos.py.
    textos_de_cartagena: bool = True  # PROMOCIONADO 20-oct (textos-B 97,4 % 26/32 frente a gen2-B 97,4 % 27/32: los 3 que empeoran no pasan por estos textos; HISTORY 0.31.72); revert = False
    # gen-5 (20-oct, Gonzalo con Claude; idioma del primer turno): el idioma de la apertura se decidía en cuatro sitios.
    # La reserva (`_setup_phase`) usaba el extractor, las palabras vacías, el LLM y G-10 (otro idioma → inglés); lo
    # sensible, `_reply_language` (solo palabras); el contacto y "¿eres un bot?", `_infer_language` (solo pistas); la
    # edad y el buceo adaptado, el "es" por defecto. Ninguno de los tres últimos aplicaba G-10. Con el flag se decide
    # UNA vez en el router, a la vez que las señales, con la cadena de la reserva (`nucleo.setup.idioma_de_apertura`),
    # y todos los caminos la heredan. APAGADO hasta medirlo (banco docs/robustness/gen/dialogos-gen5.json).
    idioma_unico_de_apertura: bool = True  # PROMOCIONADO 21-oct (gen5-B 96,6 % 27/32 frente a gen5-A 97,0 % 26/32; los que empeoran no pasan por el idioma; HISTORY 0.31.74); revert = False
    # gen-12 (21-oct): el RAG no da por hecho si el cliente es hombre o mujer (prompts/info.RAG_SIN_GENERO_*). Va con
    # `rag_no_adivina` (promocionado). La base, además, ya no nombra el sistema interno de reservas (criterio sin-fugas).
    sin_genero_supuesto: bool = True  # PROMOCIONADO 21-oct (ronda sin desplegar gen12-B 96,5 % 26/32 frente a gen12-A 96,1 % 24/32; banco gen-2: género 2/52 -> 0/39; HISTORY 0.31.75); revert = False
    # gen-3b (21-oct, Gonzalo con Claude; "pasa directamente cuando toca"): cambiar la fecha, cancelar o cambiar el
    # número de personas de una reserva YA HECHA daba la política y OFRECÍA el pase («¿te conecto con un asesor o
    # prefieres volver al menú principal?», un menú que ya no existe) sin marcarlo. Con el flag se da la política y se
    # pasa a un asesor (motivo + resumen), como `needs_staff`: el bot no ve las reservas. rutas/changes.py. APAGADO.
    cambio_de_reserva_pasa: bool = True  # PROMOCIONADO 21-oct (ronda sin desplegar gen3b-B 97,8 % 28/32 frente a gen3b-A 98,3 % 28/32; los 2 que empeoran no pasan por el pase; banco gen-3b 8/26 -> 26/26; HISTORY 0.31.77); revert = False
    # - El servicio privado (salida, lancha o instructor solo para su grupo, grupo cerrado, evento de empresa) pasa
    #   DIRECTAMENTE en cuanto lo pide (decisión de Gadea, 21-oct). Solo pasaba si el mensaje decía "servicio privado",
    #   "grupo cerrado" o "evento corporativo"; lo demás iba al RAG, que solo puede OFRECER el pase. Lo dice Jev
    #   (`pide_servicio_privado`) y responde el grupo privado (rutas/info.py). APAGADO.
    privado_pasa_directo: bool = True  # PROMOCIONADO 21-oct (con `cambio_de_reserva_pasa`, misma ronda gen3b-A/B; HISTORY 0.31.77); revert = False
    # s4-33 (9-oct): razonamiento de GPT-6 Luna cuando hace de juez de grounding ("none" = como el resto de llamadas a
    # gpt-6; "low"/"medium" = razona antes de la lista y el tope de salida sube 4000 tokens, como el juez gpt-5/o).
    # Se mide con scripts/banco_juez_reales.py --ajuste juez_luna_razonamiento=low.
    juez_luna_razonamiento: str = "none"
    # ord-7 (21-oct, decisión de Gadea con ord-0): cuando la puerta del origen salta, quitaba también lo que incluye,
    # el almuerzo y el enlace, y el cliente se quedaba sin nada de lo que preguntó (ord-0: 3 de las 4 omisiones de
    # redacción). Ahora, si se sabe de qué actividad pregunta y tiene un plan por origen, el código pone las DOS
    # variantes del catálogo (desde Cartagena y ya en las islas: precio online por persona en su moneda, el transporte
    # y si lleva almuerzo) y pregunta el origen para seguir. Sin actividad concreta (los paquetes de buceo), como hoy.
    origen_dos_variantes: bool = True  # PROMOCIONADO 21-oct (ord-7: bancos 2/14 -> 12/14 y 2/8 -> 8/8; core ord7-B2 96,6 % 25/32 frente a ord4-A 96,5 % 25/32, ninguna regresion de ord-7; HISTORY 0.31.86); revert = False
    # ord-7b (21-oct, decisión de Gadea con ord-0: con niños, la edad mínima EN CIFRA): la tarjeta «qué puede hacer cada
    # quien» pone la edad mínima de cada opción («minicurso de buceo (desde 10 años)») y dice quién es cada línea en el
    # idioma del cliente (en inglés salía «8 años», g10-049).
    tarjeta_edades_en_cifra: bool = True  # PROMOCIONADO 21-oct (con ord-7); revert = False
    # ord-7 (21-oct): la pregunta de Jev «¿pide el precio?» nombra las actividades del centro; con «the dive center's
    # activities» a secas, «¿Cuánto cuesta el snorkel?» salía 0,55 (umbral 0,7) y la puerta del origen no saltaba.
    # ARQ (22-oct, fase ARQ, decisión de Gadea: docs/robustness/arq/plan-hechos-por-codigo.md): Jev da las intenciones
    # del mensaje (precio, qué incluye, requisitos, horario, disponibilidad, edad, enlace), el código saca los hechos
    # con las reglas aplicadas (src/flows/hechos.py) y el redactor solo los pone en palabras, sin el catálogo entero.
    # APAGADO hasta medirlo con el banco fijo del RAG ×3 y su ronda core.
    hechos_por_codigo: bool = True  # PROMOCIONADO 22-oct (arq-1d/1e/1h + arq-3: banco fijo x3 100/120 -> 115-119/120, 0 invenciones; core A/B3 97,4 % -> 97,9 % 27/32 con votos, sin regresiones del redactor; G10 de control 86,4 % 22/72 -> 87,7 % 25/72, votos 27 mejoras y 23 regresiones reales, ~9 ya arregladas; HISTORY 0.31.92); revert = False
    hechos_al_rag: bool = True  # PROMOCIONADO 22-oct (arq-1g: banco de mezclados x3, la parte de la tabla 61/66 -> 66/66; HISTORY 0.31.92); revert = False
    # ARQ-1p (22-oct): sin saber la actividad, la hora o la recogida, qué llevar y si hay sitio salen de las políticas
    # (son iguales para todas) y las escribe el redactor; antes contestaba el RAG (G10 nº 4: 24 turnos sin actividad, 11
    # de este tipo). Precio, qué incluye, edad y enlace siguen necesitando la actividad. APAGADO hasta medirlo.
    hechos_sin_actividad: bool = True  # PROMOCIONADO 23-oct (G10 nº 5 con los 11: 90,1 % 34/72 -> 91,2 % 40/72; HISTORY 0.31.96); revert = False
    # ARQ-1q (22-oct): decir que YA reservó no basta para pasar a una persona (needs_staff de Jev): con la reserva hecha,
    # preguntar el horario, la recogida o qué llevar lo contesta Coral; ver o tocar esa reserva o pago sigue yendo a un
    # asesor. APAGADO hasta medirlo.
    ya_reservo_no_es_pase: bool = True  # PROMOCIONADO 23-oct (G10 nº 5 con los 11: 90,1 % 34/72 -> 91,2 % 40/72; HISTORY 0.31.96); revert = False
    # ARQ-1r (22-oct): «extranjero o turista: false» (CAL-C) chocaba con la cédula de extranjería, que tienen los
    # extranjeros residentes (pagan en COP): el extractor leía false 2 de 9 veces. Una frase: salvo que tenga cédula de
    # extranjería. APAGADO hasta medirlo.
    cedula_de_extranjeria_manda: bool = True  # PROMOCIONADO 23-oct (G10 nº 5 con los 11: 90,1 % 34/72 -> 91,2 % 40/72; HISTORY 0.31.96); revert = False
    # ARQ-1s (22-oct): requisitos coherentes en los hechos: en un curso, solo el formulario médico de curso (no además el
    # de buzo certificado: G10 lo vio contradictorio), y el requisito previo (Open Water para el Advanced) y la edad
    # mínima en cifra. APAGADO hasta medirlo.
    requisitos_coherentes: bool = True  # PROMOCIONADO 23-oct (G10 nº 5 con los 11: 90,1 % 34/72 -> 91,2 % 40/72; HISTORY 0.31.96); revert = False
    # ARQ-1u (22-oct): con el enlace de reserva, los hechos dicen cómo se reserva y se paga por él (el extranjero, 100 %
    # con tarjeta en la web), que la reserva queda confirmada cuando el equipo concilia el pago (política
    # payment_confirmation) y, si pide certificación, el carné. APAGADO hasta medirlo.
    enlace_con_como_pagar: bool = True  # PROMOCIONADO 23-oct (G10 nº 5 con los 11: 90,1 % 34/72 -> 91,2 % 40/72; HISTORY 0.31.96); revert = False
    # ARQ-1t (22-oct): «el paquete de varios días» sin cifra: el extractor lo dice (paso 6, `paquete_varios_dias`), la
    # duración queda en varios días y, sin plan elegido, los hechos son los de los paquetes (precio desde el primero con
    # la lista de todos; qué incluye: lo común a todos), no los de la salida de un día. APAGADO hasta medirlo.
    paquete_varios_dias: bool = True  # PROMOCIONADO 23-oct (G10 nº 5 con los 11: 90,1 % 34/72 -> 91,2 % 40/72; HISTORY 0.31.96); revert = False
    # ARQ-1v (22-oct): «me voy mañana al mediodía, ¿me da tiempo?» entra en la tabla (Jev pide_si_alcanza): los hechos
    # dan la decisión de Gadea (desde las islas va muy justo y lo confirma un asesor; desde Cartagena no alcanza; cierre
    # de las 4:30 del día anterior) y la espera antes de volar, solo si vuela. APAGADO hasta medirlo.
    tiempo_limitado: bool = True  # PROMOCIONADO 23-oct (G10 nº 6 con los 8: 92,4 % 42/72 -> 94,3 % 46/72; HISTORY 0.31.98); revert = False
    # ARQ-1i (23-oct, Gonzalo con Claude, decisión de Gadea #1312 y #1477; G10 nº 5: g10-034 el clima, g10-067/045/006 el
    # pago): dos intenciones más de la tabla, que no dependen de la actividad. El clima en GENERAL (política
    # weather_cancellation: si Capitanía cierra se reprograma o se reembolsa el 100 %; sin pronósticos, ofrece un asesor)
    # ya no va a la ruta sensible; con un día concreto o una reserva hecha, sigue el pase. Y cómo se paga (según la
    # nacionalidad: el extranjero 100 % con tarjeta en la web; el colombiano, 100 % o 50 % y 50 %, con un asesor), la
    # confirmación y la transferencia solo si falla el online. APAGADO hasta medirlo.
    intenciones_clima_pago: bool = True  # PROMOCIONADO 23-oct (G10 nº 6 con los 8: 92,4 % 42/72 -> 94,3 % 46/72; HISTORY 0.31.98); revert = False
    # ARQ-5f (23-oct, Gonzalo con Claude, reparto de Gadea #1525; G10 nº 5): hechos que faltaban en la tabla. La excepción
    # del refresher (500+ inmersiones o Divemaster: lo revisa un asesor) en los requisitos del buceo certificado y del
    # refresher; que el horario no se adelanta (lo ve un asesor); buceo y snorkel en la misma lancha si el turno trae los
    # dos; y que alojados en Barú o Playa Blanca salen desde Cartagena. APAGADO hasta medirlo.
    hechos_que_faltaban: bool = True  # PROMOCIONADO 23-oct (G10 nº 6 con los 8: 92,4 % 42/72 -> 94,3 % 46/72; HISTORY 0.31.98); revert = False
    varias_actividades: bool = False  # ARQ-1j (22-oct): el extractor da TODAS las actividades del mensaje (y el acompañante) y los hechos salen de cada una
    adaptado_contesta_lo_demas: bool = True  # PROMOCIONADO 22-oct (arq-1l: banco DIVE TO HEAL 3/12 -> 11/12; HISTORY 0.31.93); revert = False
    enlace_con_disponibilidad: bool = True  # PROMOCIONADO 22-oct (arq-1m: banco de enlace 3/12 -> 12/12; HISTORY 0.31.93); revert = False
    rag_enlace_al_recomendar: bool = False  # ARQ-1o (22-oct, decisión de Gadea): el RAG da el enlace del plan que recomienda si sabe el origen (a colombianos no)
    grupo_de_una_persona: bool = True  # PROMOCIONADO 22-oct (FLU-1: «es para una persona» cuenta como el tamaño del grupo en la pregunta de Jev; banco flu-1 19/24 -> 20/24, controles iguales; HISTORY 0.31.94); revert = False
    curso_preguntado_no_es_nivel: bool = True  # PROMOCIONADO 22-oct (FLU-1: si el extractor lee que el mensaje PREGUNTA por un curso con nivel, no se pregunta «¿ya tienen el Open Water o quieren sacarlo?»; banco flu-1b 9/24 -> 24/24 con el de abajo; HISTORY 0.31.94); revert = False
    # arq-5a (23-oct, G10 nº 5: ~15 fallos con hechos=None): el RAG de «contestar antes del pase» (asesor, pago, DIVE TO
    # HEAL) recibe los hechos del código como en la ruta normal. APAGADO hasta medirlo.
    hechos_en_el_pase: bool = True  # PROMOCIONADO 23-oct (G10 nº 6 con los 8: 92,4 % 42/72 -> 94,3 % 46/72; HISTORY 0.31.98); revert = False
    # arq-5c (23-oct, decisión de Gadea; G10 nº 5, ~6 fallos): sin saber si el cliente es colombiano, el precio de los
    # hechos va en USD y en COP. APAGADO hasta medirlo.
    dos_monedas_sin_nacionalidad: bool = True  # PROMOCIONADO 23-oct (G10 nº 6 con los 8: 92,4 % 42/72 -> 94,3 % 46/72; HISTORY 0.31.98); revert = False
    # arq-5b (23-oct, G10 nº 5): en los mensajes mezclados el redactor escribe la parte de la tabla con los hechos y el
    # RAG, a la vez, solo lo demás (las listas salen completas y sobra el reintento del RAG). APAGADO hasta medirlo.
    mezclados_por_partes: bool = False
    # arq-7 (23-oct, latencia, decisión de Gadea; antes del G10 nº 6). arq-7a: las listas largas del redactor (incluye,
    # requisitos, descuento) las pone el código donde el modelo deja una marca: sin segunda redacción. APAGADO.
    listas_por_codigo: bool = True  # PROMOCIONADO 23-oct (G10 nº 6 con los 8: 92,4 % 42/72 -> 94,3 % 46/72; HISTORY 0.31.98); revert = False
    # arq-7b: en los mezclados, si al RAG le faltan puntos de las listas de los hechos, los añade el código en vez de
    # rehacer la respuesta (el reintento de completitud: ~5 s). APAGADO.
    rag_hechos_sin_reintento: bool = True  # PROMOCIONADO 23-oct (G10 nº 6 con los 8: 92,4 % 42/72 -> 94,3 % 46/72; HISTORY 0.31.98); revert = False
    # arq-7d: con `listas_por_codigo`, también la recogida y el alojamiento los pone el código donde el modelo deja la
    # marca (las segundas redacciones que quedaban eran casi todas por esas dos frases). APAGADO.
    frases_por_codigo: bool = True  # PROMOCIONADO 23-oct (G10 nº 6 con los 8: 92,4 % 42/72 -> 94,3 % 46/72; HISTORY 0.31.98); revert = False
    # arq-4b (22-oct, fallos del G10 nº 4), APAGADOS hasta medirlos con su banco:
    recotizar_al_cambiar_moneda: bool = True  # PROMOCIONADO 23-oct (G10 nº 5 con los 11: 90,1 % 34/72 -> 91,2 % 40/72; HISTORY 0.31.96); revert = False · «soy colombiano» DESPUÉS de recibir el precio en USD: se vuelve a dar en COP (g10-003/016/047)
    rag_comprueba_los_hechos: bool = True  # PROMOCIONADO 23-oct (G10 nº 5 con los 11: 90,1 % 34/72 -> 91,2 % 40/72; HISTORY 0.31.96); revert = False · arq-3 también para el RAG con hechos (mensajes mezclados): si deja fuera un hecho, se rehace una vez
    redactor_sin_preguntas_de_cierre: bool = True  # PROMOCIONADO 23-oct (G10 nº 5 con los 11: 90,1 % 34/72 -> 91,2 % 40/72; HISTORY 0.31.96); revert = False · el redactor no cierra preguntando datos (fecha, personas, origen…): los pregunta el sistema
    descuentos_en_la_tabla: bool = True  # PROMOCIONADO 23-oct (G10 nº 5 con los 11: 90,1 % 34/72 -> 91,2 % 40/72; HISTORY 0.31.96); revert = False · los descuentos son una intención de la tabla (Jev): el redactor los da con sus condiciones (g10-027/035/067)
    fecha_con_dia_de_la_semana: bool = True  # PROMOCIONADO 23-oct (G10 nº 5 con los 11: 90,1 % 34/72 -> 91,2 % 40/72; HISTORY 0.31.96); revert = False · la fecha del contexto del RAG lleva el día de la semana y el de mañana («jueves 23» era viernes)
    sin_certificacion_no_hace_falta: bool = True  # PROMOCIONADO 22-oct (FLU-1: al decir «no estoy certificado» para una actividad que no lo pide, el bot dice que no hace falta; HISTORY 0.31.94); revert = False
    # arq-2a (22-oct, Gonzalo con Claude): fuera del prompt del RAG las reglas que el código ya pone en el contexto que
    # el RAG lee siempre (catálogo y políticas, en los dos caminos de `hechos_por_codigo`): moneda, 5 % por equipo
    # completo, no calcular totales, días de cierre y mal tiempo, y una viñeta repetida del tono. Las que solo vigila un
    # guarda se quedan. prompts/info.RAG_SIN_REGLAS_DEL_CODIGO_*; docs/robustness/arq/arq2a-inventario.md. APAGADO.
    rag_sin_reglas_del_codigo: bool = True  # PROMOCIONADO 22-oct (arq-2a, Gonzalo: banco neutro 105/104 y 115/115, core con votos 97,9 % 27/32 -> 98,3 % 29/32, prompt -4,7 %; HISTORY 0.31.92); revert = False
    jev_precio_nombra_actividades: bool = True  # PROMOCIONADO 21-oct (con ord-7); revert = False
    # CAL (17-oct): la preparación de cada producto (`preparation_*`, 18 de 36) en el catálogo, SIEMPRE. MEDIDO: arregla
    # cal-49 (la carta de referido) pero rompe cal-26 y cal-64 (banco CAL-A 41/48 frente a 38/48): dieciocho párrafos
    # en todos los turnos compiten con lo que hace falta en cada uno. APAGADO; la preparación va mejor en la ficha del
    # producto del que se habla.
    catalogo_preparacion: bool = False
    # CAL (17-oct): cuando la conversación YA está con una persona (paso ESCALATE), el contexto del RAG lo dice. Una
    # pregunta tras el pase seguía el flujo normal y el RAG improvisaba sobre la reserva o el pago concreto, que no ve
    # (cal-14: explicaba qué poner en el concepto de una transferencia, contra la política). Lo general se contesta
    # igual; lo del caso concreto lo confirma el asesor. APAGADO hasta medirlo.
    contexto_tras_el_pase: bool = False
    # Esquema de la base curada que lee la busqueda (rag-2, `scripts/kb_v2.py`). Solo para medir una base nueva sin
    # tocar la que usa PRE (p. ej. RAG_KB_ESQUEMA=kb_v2_prueba con `rag_piezas --codigo-local`); en PRE es siempre "kb_v2".
    rag_kb_esquema: str = "kb_v2"

    # --- Observabilidad: Langfuse (sustituye a LangSmith, cuota Developer
    # agotada; ver docs/robustness/progress-log.md "Tarea 8"). Sin claves, el
    # tracing queda apagado y `langfuse` ni se importa (3.14-safe). Claves por
    # entorno vía secrets de GitHub inyectados en .env.pre por el deploy. ---
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # --- Supabase ---
    supabase_url: str = ""
    supabase_anon_key: str = ""
    database_url: str = "postgresql://postgres:postgres@localhost:5432/diving_planet"

    # --- Chatwoot ---
    chatwoot_base_url: str = "http://localhost:3000"
    # Backend-to-Chatwoot API calls (sending messages, polling, assignments).
    # Defaults to chatwoot_base_url. Override when the bot should reach Chatwoot
    # over an internal network path (e.g. Docker service name) instead of the
    # public URL — needed on the VPS where the reverse proxy silently drops the
    # api_access_token header (underscore in the name) before forwarding it.
    chatwoot_api_base_url: str = ""
    chatwoot_api_token: str = ""
    chatwoot_account_id: int = 1
    chatwoot_inbox_id: int = 1
    chatwoot_owner_agent_id: int = 0  # 0 = auto-assign disabled
    # l2-3 (28-sep): "escribiendo…" en el chat mientras el bot prepara la respuesta. Una pregunta
    # tarda ~4 s (medido en PRE: escribir la respuesta ~1,9 s + juez ~1,2 s + búsqueda ~0,4 s); sin
    # aviso, el cliente no sabe si le han leído. No cambia lo que dice el bot. Revert = "false".
    chatwoot_typing_indicator: bool = True
    chatwoot_website_token: str = "T49iSq16SvRnqUqbayMQWmni"  # inbox website channel token (widget SDK)

    @property
    def chatwoot_api_url(self) -> str:
        return self.chatwoot_api_base_url or self.chatwoot_base_url

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"
    conversation_state_ttl_seconds: int = 30 * 24 * 3600

    # --- App ---
    app_env: str = "development"
    app_port: int = 8000
    app_log_level: str = "INFO"
    default_language: str = "es"
    supported_languages: str = "es,en"

    # --- Conversation memory (Fase A, docs/archive/memory-context-improvement-plan.md) ---
    # How many raw state.history messages every RAG/orchestrator call reads
    # (rag_agent.py's LLM answer + grounding context, orchestrator.py's
    # decision). The rolling-summary trigger (conversation_summarizer.py)
    # derives from this same setting so it stays in sync — no gap of messages
    # that are neither in the raw window nor yet folded into the summary.
    # A single settings field instead of the literal repeated in 3+ places, so
    # tuning it later (cost/latency vs. how much detail gets lost) is one
    # number to change, overridable via the HISTORY_WINDOW_SIZE env var.
    history_window_size: int = 24
    # Smaller window used only to enrich the retrieval QUERY with recent user
    # turns (not the full LLM context) — kept separate and smaller on purpose.
    history_retrieval_enrichment_window: int = 10

    # --- Robustness Fases 0, 1, 2, 3 y 8 (docs/robustness/plan.md §4): la sonda en sombra de la Fase 0
    # (`llm_extraction_shadow_mode`) y el cutover por dominio del extractor LLM (certificación, grupo/cantidad/edades,
    # ubicación y perfil/logística, flags `llm_extraction_cutover_*`) ya no existen: s4-25 quitó los flags del cutover
    # y s4-1 sus funciones y la sonda, que no llamaba nadie desde el 28-jul (308488d, se retiró el orquestador
    # antiguo). El relleno de huecos vivo es el del núcleo (`conversational_core._understand`).
    # --- Robustness Fase 9 (vetos por campo, sep-2026): un LLM verificaba un campo que el regex ya había resuelto y lo
    # corregía. ex-9 (15-oct) lo sacó del camino real (el extractor con cita manda) y MEJ-1 (21-oct) borró la maquinaria
    # muerta (`rutas.booking`) y sus 12 flags `llm_*_veto_shadow_mode` / `llm_*_veto_cutover`.

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def languages(self) -> list[str]:
        return [lang.strip() for lang in self.supported_languages.split(",")]


settings = Settings()

# Observabilidad: inicializa Langfuse (con la máscara de PII) si hay claves.
# Sin claves es no-op y `langfuse` ni se importa (3.14-safe). La integración vive
# en `src/observability.py` (módulo hoja) para no crear un ciclo con este módulo.
from src.observability import init_langfuse  # noqa: E402 — tras definir `settings`

init_langfuse(settings)
