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
    # G-10 (decision de Gadea, 14-oct): el bot atiende en espanol e ingles; si el cliente escribe en OTRO idioma
    # (portugues, frances...) contesta en INGLES. El idioma principal del mensaje lo dice el extractor de la fase EX
    # (misma llamada, sin coste); unas palabras sueltas de otro idioma no cuentan. conversational_core.
    # _otro_idioma_en_ingles. PROMOCIONADO 14-oct (HISTORY 0.31.22: g10-A/B 89,8 -> 91,2 %). Revert = False aqui y en el compose.
    idioma_otro_en_ingles: bool = True
    # EX-RAG-1 (aprobado por Gadea el 14-oct para medir): las politicas del negocio enteras van SIEMPRE en el contexto
    # del RAG, como el catalogo (prefijo fijo, cacheable; ~2.000 tokens). El RAG no recuperaba la de equipaje en un
    # mensaje largo. rag_agent (bloque del catalogo). PROMOCIONADO 14-oct (HISTORY 0.31.22: g10-A/B 89,8 -> 91,2 %). Revert = False aqui y en el compose.
    rag_politicas_en_contexto: bool = True
    # EX-RAG-2 (14-oct): regla del RAG: no atribuir al cliente un servicio o una reserva que no dijo ('For the 3-dive
    # package...' a quien solo dijo que dormia en la isla). rag_agent.build_system_prompt. PROMOCIONADO 14-oct (HISTORY 0.31.22: g10-A/B 89,8 -> 91,2 %).
    # Revert = False aqui y en el compose.
    rag_no_supone_reserva: bool = True
    # 18-oct (decision de Gadea: no adivinar nada que el cliente no haya dicho): la regla de EX-RAG-2 ampliada a origen,
    # nacionalidad, certificacion, cuantos son y fechas; la sustituye. Fallos estables de CAL-F (zona RAG).
    # rag_agent.build_system_prompt, prompts/info.RAG_NO_ADIVINA_*. APAGADO.
    rag_no_adivina: bool = True  # PROMOCIONADO 18-oct (mod-E, HISTORY 0.31.55); revert = False
    # EX-FLUJO-1 (decision de Gadea, 14-oct, opcion 2): si el cliente no contesta una pregunta de la reserva, no se
    # repite en el turno siguiente: se aplaza y vuelve justo antes del resumen. Solo las preguntas de datos que no
    # condicionan a otras (origen, hotel, cuantos, ultima inmersion, refresher, edades, nacionalidad).
    # conversational_core._siguiente_pregunta. PROMOCIONADO 14-oct (HISTORY 0.31.23; se aplaza a la TERCERA vez). Revert = False aqui y en el compose.
    aplazar_pregunta_sin_respuesta: bool = True
    # EX-EXTRACTOR-1 (14-oct): la regla de la ubicacion del extractor con la NEGACION primero ('sin ir de Cartagena' =
    # no sale de Cartagena: 0 -> 10/10, sin mover otros campos). La primera version (un bloque de aclaraciones al final,
    # ronda flujo1-B) movia otros campos y se cambio. extractor_turno.UBICACION_NEGACION_*. PROMOCIONADO 14-oct (HISTORY 0.31.23).
    # Revert = False aqui y en el compose.
    extractor_aclaraciones: bool = True
    # EX-EST-2 (14-oct): arreglos del prompt del extractor por causa (est3-B), version v3 tras la ronda est4-B: (1) la
    # cita siempre del cliente, nunca del bot ni de 'Lo que ya sabemos'; aceptar la opcion que propone el bot es elegirla;
    # (2) 'un solo buzo', 'dos adultos' en los ejemplos del grupo ('Un solo buzo avanzado' con la actividad sabida 0 ->
    # 10/10); (3) el ejemplo 'quiero bucear con mi amigo' (no elige actividad) ya no le quita el grupo (8 -> 10/10);
    # (4) la cedula de extranjeria es ser residente (0 -> 8/8 COP). La v1 ('extrae todo aunque ya se sepa') rompia las
    # respuestas cortas ('Frances' a la nacionalidad 4/8 -> 0/8, regresion de est4-B) y repetia lo sabido.
    # Banco ex0 3 pasadas (v3): aciertos 91,8 % (igual), casos con invento 5 -> 3, peor caso 89,3 -> 91,0 %.
    # extractor_turno.TODO_LO_DICHO_*, GRUPO_*, ACTIVIDAD_EJEMPLOS_*, RESIDENTE_*, ELIGE_*. Ronda est5-B: arregla la repregunta
    # de 'Frances'; ninguna regresion suya. PROMOCIONADO 15-oct (HISTORY 0.31.29).
    # Revert = False aqui y en el compose.
    extractor_todo_lo_dicho: bool = True
    # CAL-C2 (16-oct): aceptar lo que propone el bot ("nos gusta") se citaba con el texto del BOT y la comprobación
    # de la cita lo descartaba; ahora, para la actividad, vale una cita que esté en la última pregunta del bot.
    # APAGADO hasta medirlo.
    extractor_cita_del_cliente: bool = True  # PROMOCIONADO 17-oct (CAL-C, ronda core calc-A/B; decisión de Álvaro)
    # EX-EST-2 (14-oct, tanda est5): arreglos del flujo por causa. (1) Lo que el cliente dice en el turno que acaba en
    # el pase a una persona se guarda (antes la extraccion se cancelaba: 'staying at the Ubuntu Hotel' y luego 'Where will
    # you be joining us from?'). conversational_core.guardar_lo_dicho_en_el_pase. Ronda est5-B: sin regresiones suyas.
    # PROMOCIONADO 15-oct (HISTORY 0.31.29).
    # Revert = False aqui y en el compose.
    est4_flujo: bool = True
    # EX-EST-2 (15-oct): la señal de Jev "¿hay algo que CONTESTAR?" (`asks_question`) cuenta también las peticiones en
    # imperativo ('dame la cuenta y transfiero', 'send me the payment link', 'Full name of dive center…'): antes no
    # llegaban al RAG. Banco de 257 mensajes: ve 140 -> 146/157, falsas alarmas 3 -> 5/100. jev_router._ASKS_QUESTION_Q_V2.
    # Ronda est6-B: 'dame la cuenta y transfiero' ya se contesta (forma de pago). PROMOCIONADO 15-oct (HISTORY 0.31.31).
    # Revert = False aqui y en el compose.
    jev_pide_algo: bool = True
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
    # EX-EST-2 (14-oct): a quien ya dijo que es buzo certificado y no ha elegido actividad se le recomiendan SUS opciones
    # (salida de 2 inmersiones, paquetes, curso avanzado) en vez del menu entero con minicurso y snorkel (regla de
    # Gadea: recomendar segun el contexto). conversational_core.ask_slot. PROMOCIONADO 14-oct (HISTORY 0.31.24).
    # Revert = False aqui y en el compose.
    recomendar_a_certificados: bool = True
    # 18-oct (ronda mod-F): el simétrico para quien NO es certificado y no ha elegido: minicurso, snorkel o Open Water en
    # vez del menú entero (que ofrece "buceo", solo para certificados). conversational_core.ask_slot. APAGADO.
    recomendar_a_no_certificados: bool = True  # PROMOCIONADO 19-oct (mod-G2, HISTORY 0.31.57); revert = False
    # 18-oct (ronda mod-D, reserva-solo-link): el resolutor no fija un valor con una respuesta que se contradice ("no,
    # buceé hace poco" a "¿Eres buzo certificado?"). prompts/booking.SLOT_RESOLVER_CONTRADICCION. APAGADO.
    resolutor_sin_contradicciones: bool = True  # PROMOCIONADO 19-oct (mod-G2, HISTORY 0.31.57); revert = False
    # EX-EST-2 (14-oct): el acuse reconoce SOLO lo que dice el mensaje (el resumen de la reserva no se repite; ante
    # 'gracias' o una fecha suelta, nada). Banco scripts/banco_acuse.py: inventaba en 33/40 casos reales
    # ('tienes una reserva para el sabado'). prompts/booking.ACUSE_SOLO_MENSAJE_*. Ronda est3-B: 91,3 % (est2-B 88,8 %),
    # 16/29 sin fallos (antes 12), ninguna regresion del acuse. PROMOCIONADO 14-oct (HISTORY 0.31.25).
    # Revert = False aqui y en el compose.
    acuse_solo_el_mensaje: bool = True
    # EX-EST-2 (14-oct): arreglos de datos de la tanda est3 (la pregunta del origen solo dice 'ida y vuelta el mismo dia'
    # si se SABE que el plan es de un dia; ...). PROMOCIONADO 14-oct tras est3-B (HISTORY 0.31.25).
    # Revert = False aqui y en el compose.
    est2_datos: bool = True
    # 13-oct (Gonzalo): el NOMBRE del cliente lo lee el extractor con su cita (campo `nombre`, solo con este flag; con
    # el flag apagado la llamada al extractor es la de antes). La regex se queda con las formas sin ambiguedad ("me
    # llamo", "mi nombre es", "my name is"). Caso: "yo soy gringo" -> "¡Hola, Gringo!" (HISTORY 0.31.18).
    # ENCENDIDO para su mini-ronda B (atencion-B, 13-oct); si no pasa, False aqui y quitar la linea del compose.
    nombre_por_extractor: bool = True
    # 13-oct (Gonzalo): el grupo privado / evento de empresa contesta "Te paso con un asesor…" y ahora MARCA el pase
    # (motivo + resumen para el asesor, como el link roto o needs_staff). Antes no se marcaba: solo llegaba a una persona
    # si el cliente respondia "si/ok" justo despues (HISTORY 0.31.17). ENCENDIDO para su mini-ronda B (atencion-B,
    # 13-oct); si no pasa, False aqui y quitar la linea del compose.
    grupo_privado_pase: bool = True
    # 13-oct (Gonzalo): en las instrucciones del extractor, la regla general daba "¿cuanto cuesta el buceo certificado?"
    # como algo que NO es un dato y la de `activity` dice que preguntar el precio de un producto SI lo elige (Gadea
    # 14/27-sep). Con el flag el ejemplo vale solo para la certificacion (extractor_turno.GENERAL_PRECIO_*_V2).
    # Caso: regateo-grupo-6 repreguntaba "¿buceo, minicurso, snorkel o curso?". ENCENDIDO para su mini-ronda B (atencion-B,
    # 13-oct); si no pasa, False aqui y quitar la linea del compose.
    extractor_precio_elige: bool = True
    # 13-oct (Gonzalo): con la conversacion ya pasada a una persona (Step.ESCALATE), el bot no vuelve a hacer preguntas
    # de la reserva: contesta lo que se pregunte y si no, una nota corta. Caso: cambio-fecha-por-enfermedad (tras el
    # pase por la intoxicacion, "Which one are you leaning toward — diving, a mini-course…?" en 3 turnos).
    # ENCENDIDO para su mini-ronda B (atencion-B, 13-oct); si no pasa, False aqui y quitar la linea del compose.
    tras_pase_sin_vender: bool = True
    # 13-oct (Gonzalo): el aviso medico pasa la conversacion a una persona pero no lo decia; con el flag anade "Te paso
    # ahora con alguien del equipo, que te escribe por aqui enseguida" (escalation._PASE_MEDICO). ENCENDIDO para su mini-ronda B (atencion-B,
    # 13-oct); si no pasa, False aqui y quitar la linea del compose.
    aviso_medico_dice_pase: bool = True
    # 13-oct (Gonzalo): posventa. Jev (`ya_reservado`, misma llamada) dice si el cliente YA tiene una reserva o ya hizo la
    # actividad; mientras valga, el bot contesta lo que pregunte pero no hace preguntas de la reserva ni ofrece el menu
    # de actividades. Casos: cambio-fecha-por-enfermedad ("Just completed the waivers" -> "Which one are you leaning
    # toward…?"), pedir-fotos-postventa ("Fueron muy buenos buceos" -> "¿Con cual te animas?"). ENCENDIDO para su mini-ronda B (atencion-B,
    # 13-oct); si no pasa, False aqui y quitar la linea del compose.
    posventa_sin_vender: bool = True
    # CAL-B (15-oct, Gonzalo; decision de Gadea del 15-oct): sin saber la nacionalidad, el precio va en USD. La regla del
    # catalogo decia "si no sabes la nacionalidad, da las dos monedas" (catalog.MONEDA_SIN_NACIONALIDAD) y el resumen del
    # estado no decia nada: con el flag, la regla del catalogo es la de Gadea y el resumen da la moneda ya resuelta.
    # Banco de fallos (8 casos x 3): fallan 12/24 -> 7/24 (6 de los 7 son del choque con la regla del origen).
    # Mini-ronda calb-A2/B2 (16-oct, 24 dialogos, con credito): 92,7 -> 95,4 %, 12 -> 17/24 sin fallos, 9 mejoras / 5
    # regresiones (2 por criterios desfasados o el choque con el origen, 3 ajenas). PROMOCIONADO 16-oct (decision de Alvaro;
    # HISTORY 0.31.35). Revert = False aqui.
    moneda_sin_nacionalidad_usd: bool = True
    # ex-2 (fase EX): las palabras clave que pasan a un asesor ANTES de que opine la IA se quedan con las EMERGENCIAS
    # (escalation.EMERGENCY_KEYWORDS) y las incidencias en tiempo real; lo medico, el tiempo y las quejas los decide
    # Jev (`sensitive_topic`). Con la lista entera, "completed the medical form" o "mi amigo es abogado" pasaban a un
    # asesor. Escalon 0 (docs/robustness/escalado/, scripts/banco_escalado.py): falsas alarmas 32-33 -> 11-12,
    # perdidas 4-5 -> 5-7 (solo del tiempo). PROMOCIONADO 13-oct (decision de Alvaro; HISTORY 0.31.18: ronda ex23
    # 95,3 -> 95,3 %, "medical form" ya no recibe el aviso medico). Revert = False aqui y en el compose.
    escalado_solo_emergencias: bool = True
    # ex-3 (fase EX): respuestas de texto fijo ACTIVAS que pasan al RAG, una por flag (inventario y motivos:
    # docs/robustness/atajos/inventario-ex3.md). APAGADOS hasta medirlos.
    # - resumen de "¿qué ofrecen para bucear?" (rag_agent._canonical_diving_overview_answer): en las 38 rondas guardadas
    #   de PRE solo saltó con un buzo certificado que daba fechas ("soy open… no sé qué tienen"), al que le contestaba
    #   "¿Nunca has buceado? → minicurso". El catálogo entero ya va en el contexto del RAG.
    atajo_resumen_por_rag: bool = True  # PROMOCIONADO 13-oct (Alvaro, HISTORY 0.31.18)
    # - "¿cambia el precio si es colombiano?": la regla de moneda va en el catálogo y en 2 FAQs curadas.
    atajo_nacionalidad_por_rag: bool = True  # PROMOCIONADO 13-oct (Alvaro, HISTORY 0.31.18): sonda igual o mejor
    # - alergia a un alimento (sin alcohol en el mensaje): la FAQ curada "Soy vegetariano o tengo una alergia" lo
    #   cubre. NO PASA el escalón 0 (13-oct): con el flag la alergia acaba en el aviso médico ("Para preguntas médicas…");
    #   se queda la respuesta fija. APAGADO.
    atajo_alergia_por_rag: bool = False
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
    # MOD-6 (18-oct): la pista de vocabulario del negocio en la transcripción (src/channels/audio.py). Con
    # gpt-transcribe (fuera de la familia gpt-4o): 3,2 % de palabras mal frente al 3,7 % de hoy. APAGADO hasta decidir el
    # modelo de transcripción (docs/robustness/mod/README.md, mod-6). PROMOCIONADO 18-oct (HISTORY 0.31.53); revert = False.
    transcripcion_con_vocabulario: bool = True
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

    # l1-4 (Fase L1): las notas del asesor se calculan EN PARALELO, no antes.
    #
    # `_maybe_capture_notes` cuesta ~0,75 s de media (nodo `setup` en Langfuse:
    # p50 0,748 / p95 1,266 sobre 90 turnos, foto 2026-09-23-core-l11-B1) de un
    # turno de ~4,2 s, y en ese paso no hay ninguna otra llamada al LLM: es la
    # ganancia entera de l1-4.
    #
    # Por que en paralelo y no despues de responder (propuesta de Gadea, mejor
    # que la primera version): las notas ALIMENTAN `_build_extra_context`, el
    # contexto que recibe el RAG. Si se retrasan, la respuesta de ESE turno se
    # queda sin la nota de ESE mensaje -> cambia la conducta. Lanzandolas al
    # principio y esperandolas justo antes de quien las usa, la respuesta sigue
    # viendo la nota y el tiempo queda escondido detras del router (1,4 s) y la
    # extraccion (1,0 s), que corren mientras tanto.
    #
    # El resumen (`maybe_update_summary`) se queda como esta: solo recalcula cada
    # N mensajes, asi que casi nunca cuesta nada.
    notes_in_parallel: bool = True

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

    # u3-1 paso 3 (24-sep): el acuse cálido (`compose_acknowledgement`) se lanza en
    # paralelo al empezar el turno y se espera en el cierre, en vez de ir DESPUÉS de la
    # extracción (en el 48 % de los turnos iban en serie: 0,85 s + 1,0 s). Si la pregunta
    # pendiente es de sí/no (seguridad, certificación, nacionalidad, refresher), sigue en
    # serie: su resumen necesita el valor recién extraído. ENCENDIDO por defecto (= PRE, paso 10).
    ack_in_parallel: bool = True

    # u3-4 (24-sep): "contesta y sigue". Un mensaje que trae una pregunta (regex, "?" o
    # Jev >= 0,7 en la MISMA llamada del router) ya no se trata como pregunta O como dato:
    # el RAG la contesta en paralelo, la extracción sigue su camino normal y la respuesta
    # lleva las dos cosas (primero la respuesta, luego lo que toque de la reserva). Ver
    # docs/robustness/u3-4-diseno.md. ENCENDIDO por defecto (= PRE, paso 10).
    answer_and_continue: bool = True

    # u3-5 (27-sep): correcciones de datos ya guardados ("¿lo cambio?"). Paso 1, deterministas:
    # (a) no se propone un cambio que se lee igual para el cliente; (b) la confirmación se pregunta
    # UNA vez: si el cliente no contesta sí/no, se queda lo guardado y esa propuesta no se repite.
    # Ronda A del paso 3: de 12 "¿lo cambio?", 6 eran repeticiones y 2 "X -> X". ENCENDIDO por defecto (= PRE, paso 10).
    corrections_v2: bool = True
    # u3-5 (27-sep, decision de Gadea): el minicurso DEDUCIDO ("primera vez") se recomienda y lo confirma
    # el cliente. Separado de `corrections_v2` tras la ronda B del 27-sep (su unica regresion propia:
    # "MINI CURSOS" en plural no contaba como nombrarlo, y con acompanante la recomendacion no se llegaba
    # a mostrar). ENCENDIDO por defecto (= PRE, paso 10).
    recommend_inferred_minicourse: bool = True
    # CAL-C1 (16-oct): quien ya dijo que quiere bucear no recibe el menú de actividades; sin certificación se le
    # recomienda el minicurso y, sin saberla, se le pregunta (regla de Gadea). APAGADO hasta medirlo.
    actividad_por_lo_sabido: bool = True  # PROMOCIONADO 17-oct (CAL-C, ronda core calc-A/B; decisión de Álvaro)
    # CAL-C3 (17-oct): el extractor lee también el HOTEL donde se aloja (con su cita, sin lista cerrada) y no se le
    # vuelve a preguntar (cal-41 "Isla Mulata", cal-67/68 "Bodegas de Santa Clara"). APAGADO hasta medirlo.
    hotel_por_extractor: bool = True  # PROMOCIONADO 17-oct (CAL-C, ronda core calc-A/B; decisión de Álvaro)
    # CAL-C3b (17-oct): si la respuesta a la pregunta del cliente ya acaba preguntando, no se le pega detrás la
    # pregunta de la reserva (cualquier dato, no solo la actividad): una sola pregunta por turno (cal-71/73).
    # APAGADO hasta medirlo.
    una_sola_pregunta: bool = True  # PROMOCIONADO 17-oct (CAL-C, ronda core calc-A/B; decisión de Álvaro)
    # CAL-C3c (17-oct): el origen del extractor se guarda solo si Jev no está seguro de que el mensaje NO lo dice
    # ("bucear en islas del rosario" ≠ estar en las islas: cal-71/73). APAGADO hasta medirlo.
    lugar_con_dos_lectores: bool = True  # PROMOCIONADO 17-oct (CAL-C, ronda core calc-A/B; decisión de Álvaro)
    # CAL-C (17-oct, DECISIÓN DE ÁLVARO): quien dice que no tiene cédula colombiana (ni de extranjería), o que es
    # extranjero, no es colombiano y paga en USD (cal-32: "que no tenga cedula"). APAGADO hasta medirlo.
    sin_cedula_extranjero: bool = True  # PROMOCIONADO 17-oct (CAL-C, ronda core calc-A/B; decisión de Álvaro)
    # CAL-C3d (17-oct): con la conversación ya pasada a un asesor, el RAG lo sabe y no pide al cliente que repita su
    # caso (cal-59: "¿me podrías ayudar con este tema?" → "Cuéntame, ¿qué tema?"). APAGADO hasta medirlo.
    tras_pase_recuerda_el_pase: bool = True  # PROMOCIONADO 17-oct (CAL-C, ronda core calc-A/B; decisión de Álvaro)
    # CAL-C4 (17-oct): si el cliente afirma un lugar que Jev, seguro, no reconoce como Cartagena ni las islas ("En baru
    # y Rosario", cal-55), se le pregunta a la base, que sabe dónde no operamos. APAGADO hasta medirlo.
    lugar_desconocido_al_rag: bool = True  # PROMOCIONADO 17-oct (CAL-C, ronda core calc2-A/B)
    # CAL-C5 (17-oct): la red de menciones por palabras clave (actividades nombradas que no están en el reparto →
    # "¿cuántos para X?") solo actúa si el extractor no pudo leer el mensaje: "We snorkeled in Roatan yesterday"
    # preguntaba por snorkel (cal-69/70). APAGADO hasta medirlo.
    red_menciones_solo_sin_extractor: bool = True  # PROMOCIONADO 17-oct (CAL-C, ronda core calc2-A/B)
    # CAL-C3e (17-oct, propuesta de Gadea): el hotel que lee el extractor, si está en el catálogo de hoteles de las islas
    # del detector, da su isla y "está en las islas"; y también se guarda en el turno que acaba en el pase a una
    # persona (cal-46: "staying at the Ubuntu Hotel" se perdía). APAGADO hasta medirlo.
    hotel_del_catalogo_da_isla: bool = True  # PROMOCIONADO 17-oct (CAL-C, ronda core calc2-A/B)
    # G3-01 (17-oct, charla G3 de Gadea, conv 5567): lo que el cliente dice en un turno que contesta una respuesta fija
    # (p. ej. la de edades) se guarda como en el turno del pase: solo campos aún no sabidos y con cita comprobada.
    # "la salida de 2 inmersiones para nosotros dos. y los niños qué pueden hacer?" perdía la actividad. APAGADO.
    lo_dicho_en_respuesta_fija: bool = True  # PROMOCIONADO 18-oct (G3-01, ronda core g301-A/B)
    # G3-01 (17-oct): si la actividad principal ya elegida sigue en el reparto del grupo con gente, la actividad nueva
    # del turno es la de otra parte del grupo y no la sustituye ("el de 12 minicurso" no convierte a los padres
    # certificados en alumnos del minicurso). APAGADO hasta medirlo.
    actividad_principal_en_el_reparto: bool = True  # PROMOCIONADO 18-oct (G3-01, ronda core g301-A/B)
    # G3-01 (17-oct): un reparto que no suma el total, sin reparto guardado y con la actividad principal ya elegida, se
    # completa con ella (sin reparto, todo el grupo hace la principal): "el de 12 minicurso y el de 8 snorkel" en una
    # familia de 4 con la salida de 2 inmersiones elegida = {certified_diving: 2, minicourse: 1, snorkel: 1}. Antes se
    # descartaba y se cotizaba 3 × minicurso. APAGADO hasta medirlo.
    reparto_parcial_con_lo_sabido: bool = True  # PROMOCIONADO 18-oct (G3-01, ronda core g301-A/B)
    # G3-01b (17-oct): en la tarjeta del precio, si hay plazas de snorkel, los niños más pequeños van primero ahí; el
    # niño de 8 que hace snorkel ya no convierte el minicurso del de 12 en "Bubble Makers (8-10)". APAGADO.
    ninos_primero_al_snorkel: bool = True  # PROMOCIONADO 18-oct (G3-01, ronda core g301-A/B)
    # CAL-F (18-oct, refresher-rechaza-acepta 3/3 en PRE): el extractor lee si el cliente quiere o no el refresher, con su
    # cita, aunque el bot no se lo haya preguntado ("en realidad sí lo quiero, mejor prevenir" se perdía). APAGADO.
    refresher_por_extractor: bool = True  # PROMOCIONADO 18-oct (CAL-F, decisión de Álvaro)
    # CAL-F (18-oct, grupo-mixto-precio-cop-total): si la actividad que lee el extractor no es de nadie del reparto que
    # lee a la vez, manda el reparto ("1 buzo avanzado y 2 para bautismo" no es el Curso Avanzado). APAGADO.
    actividad_del_reparto: bool = True  # PROMOCIONADO 18-oct (CAL-F, decisión de Álvaro)
    # CAL-F (18-oct, precios-y-disponibilidad-con-negociacion): si el servicio guardado es de un día y la duración dice
    # varios ("dos buceos o el pack de 5 en 2 días"), el plan no está elegido: la pregunta del origen es la neutra, sin
    # "dura 1 día y hay que dormir en las islas". APAGADO.
    origen_neutro_con_dos_planes: bool = True  # PROMOCIONADO 18-oct (CAL-F, decisión de Álvaro)
    # G3-06 (18-oct, decisión de Gadea): Barú y Playa Blanca NO son Islas del Rosario (península unida a tierra, donde no
    # operamos). Quien se aloja allí no queda como "ya en las islas" (Jev, el extractor de respaldo, el resolutor de la
    # pregunta del origen); el lugar se le pregunta a la base, que da el aviso. APAGADO.
    baru_no_es_rosario: bool = True  # PROMOCIONADO 18-oct (mod-B, HISTORY 0.31.53); revert = False
    # mod-2 (18-oct, decisión de Gadea): elegir el buceo certificado ("fun dives") no dice que el cliente esté
    # certificado; tiene que confirmarlo. Con el flag, el extractor no lo deduce (la regla del catálogo lo hacía para
    # todos los modelos). APAGADO.
    certificado_solo_si_lo_dice: bool = False  # mod-G/mod-H (19-oct): APAGADO; con la regla de is_certified afinada sigue el
    # minicurso a 183 USD en reserva-solo-link: el extractor toma el «no» de «no, buceé hace poco» (a «¿eres buzo
    # certificado?») como no certificado. Falta la regla de contradicción también en el extractor.
    # mod-2 (18-oct, decisión de Gadea, revoca `extractor_precio_elige`): preguntar el precio de un producto es una duda:
    # no elige la actividad, no dice que quiera bucear ni que sea certificado. Cambia a la vez las cuatro frases del
    # extractor que hablan del precio (ver extractor_turno._PRECIO_NO_ELIGE). APAGADO hasta medirlo.
    precio_no_elige: bool = False  # mod-G (18-oct): repreguntas en 5 diálogos del core (quita deducciones válidas); a afinar
    # CAL-F (18-oct, decisión de Gadea): la tarjeta con el precio sale aunque el cliente no conteste la pregunta de
    # seguridad (solo si es lo único que falta), con la pregunta una vez dentro y el precio del refresher. APAGADO.
    tarjeta_sin_seguridad: bool = True  # PROMOCIONADO 19-oct (mod-G2, HISTORY 0.31.57); revert = False
    # r6-1(b) (17-oct): si en un turno NINGUNA llamada a OpenAI funciona (sin saldo, clave inválida, caído), el bot dice
    # que hay un problema técnico y pasa a un asesor (motivo = alerta en Chatwoot), en vez de "no lo tengo a la mano".
    # PROMOCIONADO 18-oct (decisión de Álvaro, tras la 2.ª caída por saldo en un día): comprobado en PRE con una clave
    # inválida (mensaje honesto + pase) y sin falsos disparos con la clave buena (4/4).
    aviso_si_openai_falla: bool = True

    # Modelo del juez de grounding v3 (el de siempre desde s4-25: sin flag). 28-sep (HISTORY 0.29.66): v3 con
    # gpt-4.1-mini 48/70 y gpt-4o-mini 37/70 frente a 70/70, y NO más rápidos: se quedó gpt-4.1.
    grounding_v3_model: str = "deepseek/deepseek-v4.1-flash"  # PROMOCIONADO 18-oct (mod-C, HISTORY 0.31.53); revert = "gpt-4.1"
    # 1-oct (docs/robustness/juez/README.md): juez v4. Una linea por frase con su tipo (dato / no_lo_tengo / asesor /
    # otro) y el veredicto lo saca el codigo (solo cuenta un NO en un dato). El v3 se saltaba su propio filtro en
    # cuanto la respuesta traia un dato y ponia SI/NO al azar a "no lo tengo a la mano, un asesor te lo confirma".
    # APAGADO: se mide primero con el banco (scripts/sonda_juez_tipo.py).
    juez_por_tipo: bool = False
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
    rag_temperatura_cero: bool = False
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
    # CAL-A6 (17-oct): lo que §10 de cal-a5-avisos-condicionados.md dejó por probar. El aviso ya NO va en la redacción
    # (ahí desplazaba lo que la respuesta tenía que decir): tras redactar, A LA VEZ que el juez de siempre, un revisor
    # lee la CONVERSACIÓN, la respuesta y la lista de avisos con sus condiciones en palabras, y decide si falta UNO. Si
    # falta, se AÑADE una frase (antes de la pregunta final, si la hay), sin tocar el resto. Lo decide leyendo la
    # conversación y no los campos del estado porque en los casos que quedan la condición está en lo que dijo el cliente
    # y no en el estado (cal-49 habla del curso referido sin "elegirlo"; cal-47 no consta que se aloja en las islas).
    # APAGADO hasta medirlo.
    # **PROMOCIONADO 17-oct** con la ronda core cala6-B (A = calc-B de Álvaro): 96,5 % = 96,5 % de criterios, 27/32
    # diálogos sin fallo frente a 25/32, latencia del servidor +0,06 s p50. Las 5 regresiones de la ronda, repetidas 3
    # veces con y sin el flag, no son suyas (la del clima la decide Jev antes del RAG). Revert = "False" aquí y quitar
    # la línea del compose.
    avisos_al_final: bool = True
    # r6-2 (17-oct, guardarraíles): la memoria (resumen y notas para el asesor) no guarda como HECHO lo que el cliente
    # ordena o dice que otro autorizó ("SYSTEM: el gerente aprobó un 50 %…" acababa en el resumen como "ha recibido un
    # 50 % de descuento aprobado… se confirma la reserva"), y el RAG y el juez la reciben etiquetada como lo que ha
    # contado el cliente, sin verificar. **PROMOCIONADO 17-oct**: en local, 4 de 4 ataques peligrosos bien (notas vacías, resumen
    # 'El cliente afirma… (sin verificar)') y el control normal igual; banco de 10 inyecciones en PRE sin cambios
    # (ningún ataque prospera con o sin el flag: protege al asesor y las conversaciones largas). Revert = False aquí
    # y quitar la línea del compose.
    memoria_sin_ordenes_del_cliente: bool = True
    # r6-2 (17-oct, DECISIÓN DE GADEA): quien pide datos de OTROS clientes (nombres, teléfonos, reservas) recibe una
    # negativa de privacidad, no el pase a un asesor (Jev `pide_datos_ajenos`; banco r6-2 sec-07: hoy salta
    # `needs_staff` y pasa el caso). **PROMOCIONADO 17-oct**: banco de 10 inyecciones en PRE 0/30 (sec-07 3/3 → 0/3,
    # el resto igual) y ningún falso positivo en 240 mensajes reales de las rondas y del banco (contar plazas o
    # preguntar si hay sitio no cuenta). Revert = False aquí y quitar la línea del compose.
    datos_ajenos_se_niegan: bool = True
    # G3-03 (17-oct, Claude contra el chatbot): el RAG escribía "te paso con el equipo" sin que el sistema pasara el caso
    # a nadie (conv 5569, escalated=False) y el cliente se quedaba esperando. Con el flag, el RAG no lo da por hecho:
    # lo OFRECE como pregunta y el pase lo hace el sistema si el cliente acepta. APAGADO hasta medirlo.
    # PROMOCIONADO 18-oct (HISTORY 0.31.49): banco 6/6 -> 0/6; ronda core g301-B 95,6 % -> g3-B 96,5 %, ninguna
    # regresión atribuida (3 reps con y sin). Revert = False aquí y en el compose.
    rag_ofrece_el_pase: bool = True
    # G3-05 (17-oct, Claude contra el chatbot): "salimos de Cartagena el día 30. ¿Hace falta saber nadar?" recibía "no
    # tengo ese dato" (3 de 3, en español, inglés y portugués) aunque la FAQ existe: buscando el mensaje entero, el
    # origen y la fecha tapan la pregunta con las fichas que salen desde Cartagena; en portugués, además, se buscaba
    # tal cual contra la base en español e inglés. Con el flag, la búsqueda doble usa la PREGUNTA SOLA (sin los datos
    # que da el cliente y en el idioma de la respuesta), una llamada corta a la vez que la búsqueda principal, solo
    # para mensajes largos o en otro idioma. APAGADO hasta medirlo.
    # 18-oct: banco G3 9/9 -> 1/9, rag_piezas sin pérdidas, core sin regresiones atribuidas, pero +0,7 s de mediana en
    # los turnos del RAG con gpt-4o-mini (que además no traducía el portugués). APAGADO hasta que Gadea elija el
    # modelo (`pregunta_sola_model`): gpt-4.1-nano 0,5-0,6 s (familia 4.1, que Álvaro quiere dejar) o Luna 0,98 s.
    busqueda_con_la_pregunta_sola: bool = True  # PROMOCIONADO 18-oct (mod-B, HISTORY 0.31.53); revert = False
    # G3-07a (18-oct, decisión de Gadea: en un mismo mensaje, una sola moneda): cuando el turno lleva la tarjeta del plan
    # (precio en su moneda y enlace), el flujo pide al RAG la respuesta SIN precio (`rag_answer(sin_precio=True)`). El
    # RAG lo hace Gadea; el punto de decisión del flujo, Álvaro. APAGADO hasta medirlo con g3-07a y g3-02.
    rag_sin_precio_con_tarjeta: bool = True  # PROMOCIONADO 18-oct (mod-B, HISTORY 0.31.53); revert = False
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
    # CAL-E1 (DECISIÓN DE GADEA del 16-oct, que sustituye a la del 17-sep): esto es un chatbot y NO da números de
    # teléfono ni de WhatsApp. Si el cliente pide un número o quiere hablar con alguien, la conversación se PASA A UN
    # ASESOR (mismo pase que `needs_staff`). De paso desaparece la invención que el juez marcaba en cal-03: el texto
    # añadía "(solo mensajes, no llamadas)", que la base no dice. Criterio del golden `contacto-real` y casos cal-03 y
    # cal-33 del banco actualizados a esta decisión. Banco: cal-03 3/3 → 0/3. **ENCENDIDO 17-oct para la RONDA B**
    # del golden core. **PROMOCIONADO 17-oct**: en la ronda no causó ninguna regresión (las 6 son de la respuesta del
    # RAG, por los avisos). La base ya no reparte el número (28 menciones fuera de `faqs.json`).
    contacto_pasa_a_persona: bool = True
    # CAL-E5 (16-oct): Jev contesta las señales del router viendo solo el mensaje del turno, así que un mensaje que se
    # refiere a lo anterior pierde a qué se refiere ("me lo podrías compartir" tras "se me perdió el número",
    # "pero un link especial"). Con el flag le viajan los 2 últimos mensajes como referencia. APAGADO hasta medirlo.
    # **PROMOCIONADO 17-oct** (ronda D del core: 96,5 % frente al 96,1 % de la C, con 3 mejoras reales de no
    # repreguntar y el p95 más bajo de la noche, 5,0 s). Banco CAL-E: cal-33 arreglado 3 de 3 con el contexto también
    # en el enrutador de respaldo. Revert = "false" aquí y quitar la línea del compose.
    jev_con_contexto: bool = True
    # CAL-E4 (16-oct): el idioma del PRIMER turno lo decidía una lista de palabras vacías, que corta la cadena antes
    # del LLM: un mensaje en portugués con muchas palabras iguales al español ("Busco el seguinte: Vamos en família a
    # Cartagena") se contestaba en español (cal-12). Con el flag lo dice el EXTRACTOR, que ya va lanzado en paralelo
    # (campo `idioma`): ni una llamada más ni una lista de palabras. APAGADO hasta medirlo.
    # **NO PROMOCIONADO 17-oct**: medido en la ronda D y NO mejora nada (su caso, cal-12, sigue fallando porque el
    # extractor lee ese portugués como español) y tampoco rompe nada (la regresión de idioma de la ronda sale en
    # español 3/3 CON el flag y 3/3 SIN él: es cal-75, un defecto de siempre). Un flag que no mide nada no entra: el
    # código se queda apagado porque la idea es buena (quita una lista de palabras de la decisión) y le falta un caso.
    idioma_del_extractor: bool = True  # PROMOCIONADO 17-oct (CAL-C, ronda core calc-A/B; decisión de Álvaro)
    # CAL-E3 (16-oct, decisión de Gadea): quien pide algo que el sistema de reservas no da (un enlace de pago
    # especial para una agencia, una factura, una salida privada por cotizar) o quiere hablar con alguien, se pasa a un
    # asesor. Con el flag, la señal `needs_staff` incluye esa clase (cal-29). APAGADO hasta medirlo.
    # **PROMOCIONADO 17-oct** con la ronda D (banco CAL-E: cal-29 arreglado 3 de 3). La "regresión" del diálogo del
    # clima no se reproduce: 3 de 3 ofrecen el pase y hablan del estado del mar, con los tres flags y con uno solo.
    pase_si_pide_fuera_del_sistema: bool = True
    # CAL-D (16-oct): la consulta de búsqueda de un mensaje referido no nombra el asunto. Medido con
    # `scripts/sonda_senales.py`: el reescritor dejaba "And how much is per a day" en "How much is the price per day?"
    # (arregla la gramática, no el contenido) y la búsqueda traía los paquetes de varios días en vez de la ficha del
    # plan de un día (cal-42); "Vale, en concepto le coloco otros?" no traía nada de cómo se confirma la reserva
    # (cal-14). Con el flag, el reescritor recibe lo que ya sabemos del cliente (actividad, origen, nacionalidad: los
    # mismos hechos del estado que eligen los avisos) y la regla de no dejar elipsis. APAGADO hasta medirlo.
    # **PROMOCIONADO 17-oct** (ronda C del core, `2026-10-17-cal-C`). La ronda dio 96,1 % frente al 97,4 % de la A,
    # pero sus 3 regresiones NO son de este flag y se demostró repitiendo: "varios días" en el Open Water sale 3 de 3
    # CON el flag y 3 de 3 SIN él (defecto de siempre, ahora en el banco como cal-74) y la de la ventana de reserva no
    # se reproduce ninguna de 3. A favor: cal-42 arreglado 3 de 3 en el banco y la MEJOR latencia de las cuatro rondas
    # (p95 6,0 s frente a 6,4 de la A). Revert = "false" aquí y quitar la línea del compose.
    consulta_con_lo_sabido: bool = True
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
    # s4-33 (8-oct, Alvaro): instrucciones del juez de grounding v3 para GPT-6 Luna (prompts/info.py
    # GROUNDING_VERIFY_V3_LUNA_*): el v3 entero + 3 aclaraciones (lo que dice el cliente de si mismo no se comprueba;
    # valoraciones y ofertas de ayuda no son datos; las deducciones directas del contexto cuentan). Va con
    # GROUNDING_V3_MODEL=gpt-6-luna. APAGADO hasta medirlo (banco sonda_juez_modelo, escalon 0, A/B core).
    juez_v3_luna: bool = True  # PROMOCIONADO 18-oct (mod-C, HISTORY 0.31.53: va con el revisor en DeepSeek); revert = False
    # s4-33 (9-oct): razonamiento de GPT-6 Luna cuando hace de juez de grounding ("none" = como el resto de llamadas a
    # gpt-6; "low"/"medium" = razona antes de la lista y el tope de salida sube 4000 tokens, como el juez gpt-5/o).
    # Se mide con scripts/banco_juez_reales.py --ajuste juez_luna_razonamiento=low.
    juez_luna_razonamiento: str = "none"
    # 1-oct (Alvaro, paso 1 del "Siguiente" de Gonzalo): el juez ve la presentacion de Diving Planet (PADI 5
    # Estrellas, 30 años), la misma frase que el bot tiene ordenado decir (prompts/info.py PRESENTACION_*). Sin ella
    # el juez tiraba esas frases por inventadas (ronda 2026-10-01-juez-B). APAGADO hasta medirlo
    # (scripts/sonda_juez_presentacion.py y ronda core). Banco 1-oct: ciertos que pasan 3 -> 12 de 12, inventos
    # cazados 17 -> 18 de 18 (docs/robustness/juez/presentacion-2026-10-01.json). PROMOCIONADO 1-oct (ronda core
    # 2026-10-01-presentacion-B, HISTORY 0.29.91): rechazos del juez 3 -> 0, turnos con pregunta 4,29 -> 3,91 s;
    # calidad dentro del ruido. (Que la cancelacion pasara a una persona en esa ronda NO fue por este flag: ese turno
    # no paso por el RAG; HISTORY 0.29.93.) Revert = False aqui y en el compose.
    juez_presentacion: bool = True
    # 2-oct (Alvaro, paso 2 del "Siguiente" de Gonzalo): el juez tapa los datos personales LINEA A LINEA. `redact_pii`
    # sobre el contexto entero tapaba todos los precios >= 1.000.000 COP del catalogo si una FAQ decia "pasaporte"
    # o "Bancolombia", y el juez rechazaba el precio correcto (paquete de 5 en conversacion; reproducido en PRE con
    # scripts/reproducir_juez_pre.py: 50 precios tapados). Por lineas: 0 precios tapados y la cedula de un cliente
    # se sigue tapando. Escalon 0 (el dialogo x5 en PRE): rechazos 10 -> 0, precio dado 0/5 -> 5/5, "no lo tengo"
    # 4 -> 0. PROMOCIONADO 2-oct (HISTORY 0.29.92): ronda core 2026-10-01-privacidad-B frente a presentacion-B,
    # el paquete de 5 da el precio en pesos, calidad 93,4 -> 94,3 % (ruido), turnos con pregunta p50 3,91 -> 3,36 s.
    # Limite conocido: si la palabra "cedula" y su numero van en lineas distintas, el numero no se tapa (solo afecta
    # a lo que ve el juez). Revert = False aqui y en el compose.
    juez_privacidad_por_linea: bool = True
    # Punto 3 (el ORIGEN del cliente en los precios; 15 de 63 fallos visibles de la ronda 2026-10-02-completa: el modelo
    # cotizaba un origen por su cuenta). 6-oct: dos versiones con un AVISO en el contexto del RAG, medidas y quitadas
    # (V1 "no lo sabemos, preguntalo": ronda 2026-10-06-origen-B 93,9 -> 93,4 %, repreguntaba lo ya dado a entender; V2
    # "la conversacion manda": volvia a cotizar Cartagena). 7-oct, opcion C (decision de Alvaro): lo hace el CODIGO
    # (`conversational_core._origen_antes_del_precio`): si el cliente pide un precio, el origen no consta y el cliente
    # no ha nombrado Cartagena ni las islas, el bot pregunta el origen con un texto fijo (con sus botones), guarda la
    # pregunta y la contesta en cuanto el cliente lo dice. Y si una respuesta ya pregunta el origen, la reserva no
    # repite su pregunta. Escalon 0 en PRE (7-oct, Gonzalo, docs/robustness/origen-c/): PASA -- mejor que hoy en los 8
    # dialogos, peor en ninguno, sin las repreguntas de V1; hueco: "¿y en pesos?" (precio sin palabras de precio).
    # Ronda core origen-c-B (7-oct): 93,9 -> 92,9 %; la puerta miraba la PREGUNTA ("¿dice precio?") y fallaba por los
    # dos lados (pregunta de MONEDA sin contestar; "¿y en pesos?" cotizaba). Arreglo: mira si la RESPUESTA del RAG
    # lleva un importe. Ronda core origen-c2-B (7-oct): 93,9 -> 93,0 % (ruido), ninguna regresion real; la puerta salta
    # donde debe (5 veces, incluido "¿y en pesos?") y ya no en la pregunta de la moneda. PROMOCIONADO: ENCENDIDO.
    # Revert = False aqui y "false" en el compose.
    rag_origen_pregunta: bool = True
    # s4-31 (8-oct, Alvaro): cuando la puerta del origen salta, en vez de SUSTITUIR la respuesta del RAG por la pregunta
    # fija, se quitan solo las frases con un importe y su pregunta final, y se anade la del origen. En la ronda del
    # golden visible con Luna (2026-10-08-luna-visible) 6 de 33 fallos del RAG eran de perder lo que no era el precio
    # ("no hay precio especial para colombianos", "con 1,5 anos no hace falta refresher"). Tambien quita los links de
    # reserva y lo que incluye (dependen del origen). Escalon 0 en PRE: las 6 conservan lo que no es precio. Mini-ronda
    # conserva-A/B (9 dialogos, misma franja): 92,6 -> 97,0 %, 5 -> 8/9 sin fallos, 6 mejoras, ninguna regresion del flag.
    # PROMOCIONADO 8-oct (HISTORY 0.31.1). Revert = False aqui y en el compose.
    origen_conserva_respuesta: bool = True
    # CAL (17-oct): el catálogo del RAG pinta hasta qué profundidad certifica cada curso (`max_depth_m`: Open Water
    # 18 m, Advanced 30 m, lo que dice el registro de actividades) y una línea general de profundidad por certificación
    # (cal-18: "¿cuántos metros bajan?" no tenía el dato en nada que viera el RAG). APAGADO hasta medirlo.
    # **PROMOCIONADO 17-oct** con la ronda core cala6-B (A = calc-B de Álvaro): 96,5 % = 96,5 % de criterios, 27/32
    # diálogos sin fallo frente a 25/32, latencia del servidor +0,06 s p50. Las 5 regresiones de la ronda, repetidas 3
    # veces con y sin el flag, no son suyas (la del clima la decide Jev antes del RAG). Revert = "False" aquí y quitar
    # la línea del compose.
    catalogo_profundidad: bool = True
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
    # Punto 4 (s4-26, 7-oct): si Jev esta SEGURO de que el mensaje no mete a otra persona (companion_joins <
    # COMPANION_NONE_MAX, la misma puerta de u3-6), la regex de "menciona a alguien" (`_mentions_person`) no puede
    # contradecirlo. "Si cuantos dias son?" casaba "son" (hijo, en ingles) y el flujo preguntaba la actividad de un
    # acompañante inexistente ("¡Qué bien que venga alguien más!", manual-duracion-curso) con Jev en 0,04. Sin Jev
    # (flag o Jev apagados, o fallo) = la regex de hoy.
    # PROMOCIONADO 7-oct (ronda core s426-B frente a origen-c2-B: 93,0 -> 95,6 %, 8 mejoras / 1 regresion ajena, del enrutador; HISTORY 0.30.1). Revert = False aqui y en el compose.
    jev_acompanante_manda: bool = True
    # Punto 4 (s4-26, 7-oct): la red de "mencion perdida" (palabra clave de una actividad + alguien mencionado) ya no
    # saca un acompañante de la nada: sin actividad principal la mencion es la del grupo, y con la principal sabida una
    # mencion GENERICA ("buceo") es contexto del producto principal (la regla que ya se aplicaba con un curso
    # nombrado). Preguntaba "¿Cuántos serían para buceo certificado?" en minicurso-islas-y-acompanante-lancha y
    # logistica-isla-fragata-regreso-otro-dia. PROMOCIONADO 7-oct (s426-B; HISTORY 0.30.1).
    red_menciones_con_principal: bool = True
    # Punto 4 (s4-26, 7-oct): con la reserva ya cerrada (tarjeta con precio y link enviada) y sin cambios en este turno,
    # una pregunta ("¿cuánto dura?") se contesta SOLA; antes se le pegaba detras la tarjeta entera otra vez
    # (manual-duracion-curso: no-lista-precios / sin-repreguntas). PROMOCIONADO 7-oct (s426-B; HISTORY 0.30.1).
    cierre_sin_repetir: bool = True
    # Punto 4 (s4-26, 7-oct): una CONDICION del cliente ("si tu hotel tiene acceso por lancha") no pasa a HECHO en el
    # turno siguiente sin que nadie lo diga (logistica-isla-fragata-regreso-otro-dia: "como te alojas en un hotel con
    # acceso por lancha, como el Fragata, la recogida esta incluida"). prompts/info.py RAG_CONDICIONES_*. Escalon 0 en
    # PRE (7-oct, codigo local, 3 reps): la condicion se mantiene 3/3 (antes se daba por cumplida 2/2). PROMOCIONADO 7-oct
    # (s426-B) pero PARCIAL: en la mini-ronda s426-extra-B volvio a darla por cumplida (en total 3/4). Es una regla de
    # prompt: ayuda, no garantiza.
    rag_condiciones_abiertas: bool = True
    # Punto 4 (s4-26, 7-oct): el contexto del RAG llama "el plan que esta armando" a lo que el cliente ya eligio, no
    # "su carrito": el cliente no ve ningun carrito y el modelo repetia la palabra ("el curso que tienes en tu carrito",
    # manual-duracion-curso, 3 de 6 en el escalon 0; el juez lo da por invento). PROMOCIONADO 7-oct (s426-B: ya no sale).
    rag_plan_elegido: bool = True
    # Punto 4 (s4-26, 7-oct): una pregunta mas de Jev en la misma llamada (`adds_person`): ¿el mensaje SUMA a una persona
    # nueva o habla de alguien ya contado? Si Jev esta seguro de que no es nueva (< 0,2), "él quiere hacer snorkel" se
    # mueve dentro del grupo sin preguntar "¿seguís siendo 2?" (acompanante-goteo). Si duda, se pregunta como hoy.
    # Banco ciego: 0/10 nuevas por debajo, 9/10 ya contadas. PROMOCIONADO 7-oct (mini-ronda s426-extra-B: goteo pasa).
    jev_persona_ya_contada: bool = True
    # s4-27 (8-oct): la ubicacion que el detector deduce de un HOTEL ("cocoliso" -> en las islas) se declara en
    # `detected_fields` como cualquier otro dato, asi que pasa por la puerta de Jev (u3-3/u3-4). Antes no se declaraba
    # y se colaba siempre: "¿me pasas el contacto del hotel Cocoliso?" (Jev: no afirma ubicacion) dejaba al cliente "ya
    # en las islas" (contacto-hoteles-cocoliso-san-pedro). PROMOCIONADO 8-oct: mini-ronda de los 10 dialogos visibles con
    # hotel, A/B en la misma franja: 79,7 -> 85,3 %, 2 -> 4/10 sin fallos (HISTORY 0.30.3). Revert = False aqui y en el compose.
    hotel_ubicacion_declarada: bool = True
    # s4-28 (8-oct): una pregunta mas de Jev en la misma llamada (`customer_place`: Cartagena / ya en las islas / no lo
    # dice). La regex sigue PROPONIENDO que el mensaje trae una ubicacion; QUE lugar es lo decide Jev cuando esta
    # seguro (>= 0,6). `place_by_role` lo decidia por la preposicion: "visitando Cartagena... coordinar inmersiones EN
    # Isla del Rosario" salia islas (precio-desde-islas-vs-cartagena). Banco ciego: Jev 12/12, regex 4/12, 0 seguras y
    # equivocadas. PROMOCIONADO 8-oct: mini-ronda A/B de los 11 dialogos visibles afectados 82,8 -> 85,2 % (HISTORY
    # 0.30.4). Cartagena solo la cambia Jev por las islas. Revert = False aqui y en el compose.
    jev_lugar_cliente: bool = True
    # s4-27 (7-oct, Gonzalo): si el cliente NOMBRA cuantas inmersiones ("el precio de las 2 inmersiones") y su origen
    # consta, el contexto del RAG dice que plan del catalogo es (`conversational_core._plan_nombrado`). Caso:
    # precio-desde-islas-vs-cartagena, el RAG negaba las 2 inmersiones desde las islas (124 USD) y ofrecia el paquete
    # de 3; rag_piezas con el historial real 0-1/3, con el plan en el contexto 3/3 (docs/robustness/s4-27/).
    # Escalon 0 en PRE (codigo local, 3 reps): t5 da los 124 USD 3/3 (hoy 0/3). Ronda core s427-B (7-oct) frente a
    # s426-B re-juzgada: 95,2 -> 96,0 %, 24 -> 26/32 sin fallos, 1 regresion ajena (descuento-online: el enrutador
    # duda, ningun mensaje nombra inmersiones), latencia igual. PROMOCIONADO: ENCENDIDO. Revert = False aqui y quitar
    # la linea del compose.
    rag_plan_nombrado: bool = True
    # 9-oct (Gonzalo, fallos del flujo de reserva): cada EDAD que da el mensaje cuenta como una persona para respaldar
    # el reparto del grupo, como una persona nombrada; y el detector lee tambien "age 17" en singular (no "minimum
    # age"). Caso: familia-mixta-precio-descuento-refresher ("2 adults (ages 42, 19) / 1 youth (age 17) / Snorkeling /
    # 1 Adult (Age 43) / 2 kids (Ages 14, 10)"): el reparto {buceo 3, snorkel 3} se tiraba por no tener un "3" escrito
    # y el bot preguntaba "¿cuantos serian para buceo certificado?". Escalon 0 en PRE: 3/3 guardan 6 personas (3 y 3);
    # en el golden visible el detector solo cambia en ese mensaje. Mini-ronda s428-A/B: mejora la buscada
    # (familia-mixta da el precio), ninguna regresion suya. PROMOCIONADO: ENCENDIDO.
    grupo_por_edades: bool = True
    # Latencia del RAG (28-sep): la respuesta contesta SOLO lo preguntado, en 2-4 frases, y ofrece ampliar (la
    # intro cálida se queda, en una frase). Escribir la respuesta crece con la longitud (220 caracteres 1,1 s,
    # 720 caracteres 2,8 s); la mediana era ~680. Decisión del owner. APAGADO hasta su A/B (prompts/info.py).
    # Escalón 0 (HISTORY 0.29.67): con tope de longitud comprime e inventa huecos; la variante suave del código no.
    rag_concise: bool = False
    # Esquema de la base curada que lee la busqueda (rag-2, `scripts/kb_v2.py`). Solo para medir una base nueva sin
    # tocar la que usa PRE (p. ej. RAG_KB_ESQUEMA=kb_v2_prueba con `rag_piezas --codigo-local`); en PRE es siempre "kb_v2".
    rag_kb_esquema: str = "kb_v2"
    # rag-3 (29-sep): si ya se sabe QUE servicio mira el cliente, su ficha entera (la misma que la de la base v2,
    # `catalog.service_fact_sheet`) va SIEMPRE al contexto, en vez de depender de que la busqueda la encuentre.
    # Motivo medido (`rag_piezas`, 2026-09-28-rag2-B2): con `selected_service` puesto, la ficha NO entraba en el
    # top-8 ante preguntas genericas -- "what time does the course finish on the first day?" con el Open Water
    # elegido, y la direccion del centro con el Curso Referido. El dato existe (el itinerario lleva la hora de
    # encuentro); el problema es de busqueda. Sustituye a la inyeccion parcial de incluye/no incluye, que se
    # quedaba corta. APAGADO hasta su A/B (rag_piezas + ronda core).
    rag_ficha_del_servicio: bool = False
    # rag-5 (1-oct): puerta de Jev para el extractor de notas. Gonzalo midio el 30-sep que de 26 notas nuevas solo 7
    # eran buenas y 15 eran la pregunta del cliente apuntada como hecho, o inventada; y que son las que hacen rehacer
    # la respuesta adelantada. Con el flag, Jev contesta en la llamada del enrutador "¿cuenta algo del cliente que
    # haya que apuntar?" y, si esta SEGURO de que no (p < 0,2), no se llama al extractor. Calibrado con
    # `scripts/sonda_notas.py`: 0/24 positivos perdidos (7 de ellos casos reales ciegos), 43/44 negativos parados.
    # Ronda rag5-C: extractor llamado en 9 de 77 turnos, 6 notas en 93 turnos, calidad igual. PROMOCIONADO 1-oct
    # (HISTORY 0.29.88). Revert = "false" aqui y en docker-compose.vps.yml.
    notas_puerta_jev: bool = True
    # rag-4 (29-sep): la regla del "no lo tengo" del prompt del RAG es TODO-O-NADA -- dice "si la respuesta no esta
    # en el contexto, dilo" y no dice nada de contestar la parte que SI esta, asi que ante una pregunta con varias
    # partes el modelo tira la respuesta entera aunque tenga la mitad. Medido (`rag_piezas`, 2026-09-28-rag2-B2): de
    # los fallos que quedan tras rag-2, 9 son de redaccion y TODOS con el dato ya en el contexto; en
    # `salida-confirmada` el bot suelta la plantilla LITERAL de esa regla teniendo delante "se opera todos los dias
    # salvo 25-dic y 1-ene" y "solo se suspende por mal tiempo".
    # DESCARTADO 29-sep con medida (HISTORY 0.29.77): sobre los 47 casos la cobertura BAJA de 89 % a 83 %, los
    # rechazos del juez suben de 2 a 8 y aparecen 1 contradiccion, 1 dato prohibido y 3 "no lo tengo". Decirle
    # "contesta lo que sabes" le hace AFIRMAR mas, el guard rechaza y tras regenerar dice "no lo tengo" MAS que
    # antes: lo contrario de lo que buscaba. Se deja aqui apagado para que no se reintente sin leer
    # docs/robustness/rag-3/README.md.
    rag_contesta_lo_que_sabe: bool = False

    # Paso 6 (27-sep): respuestas fijas y salida deterministas de S4. s4-14: si piden un telefono se
    # da el WhatsApp oficial (decision de Gadea; antes "no manejo un numero"); s4-15: "¿eres un bot?"
    # -> dice que es la asistente virtual; s4-16: la queja se pasa a staff con una disculpa. ENCENDIDO por defecto (= PRE, paso 10).
    s4_fixes: bool = True

    # --- Observabilidad: Langfuse (sustituye a LangSmith, cuota Developer
    # agotada; ver docs/robustness/progress-log.md "Tarea 8"). Sin claves, el
    # tracing queda apagado y `langfuse` ni se importa (3.14-safe). Claves por
    # entorno vía secrets de GitHub inyectados en .env.pre por el deploy. ---
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # --- Refactor multiagente sobre LangGraph (Fase 0.5, docs/multi-agent-
    # refactor-plan.md) --- strangler-fig kill switch: off en todos lados hasta
    # que el grafo real (Fase 1+) esté probado en PRE. Con el flag apagado el
    # módulo `src/orchestration` ni se importa — cero riesgo/overhead para el
    # camino actual (cascada del supervisor).
    agent_arch: bool = True

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

    # --- Robustness Fase 0 (docs/robustness/plan.md) ---
    # When True, every message also runs through the LLM gap-filler extractor
    # (src/agents/llm_extractor.py) in SHADOW mode: the result is logged for
    # comparison against the regex-based IntentDetector but never changes
    # behavior. Off by default everywhere — turned on only in the environment(s)
    # used to gather Fase 0 agreement data. Not a per-field cutover switch (that
    # comes later, per-domain, once eval-set thresholds are met — see the plan).
    llm_extraction_shadow_mode: bool = False
    # --- Robustness Fase 1 (docs/robustness/plan.md §4, dominio certificación) ---
    # When True, the LLM extractor's result for `is_certified`/`activity` is
    # actually APPLIED (not just logged) when the regex left them unresolved —
    # the first real per-domain cutover. Eval-set agreement measured at 100%
    # (docs/robustness/progress-log.md, 2026-07-21) before enabling this. Off
    # by default everywhere; the regex stays the primary/fast path regardless —
    # this only fills gaps, never overrides a regex-resolved value.
    llm_extraction_cutover_certification: bool = True
    # --- Robustness Fase 2 (docs/robustness/plan.md §4, dominio grupo/cantidad/edades) ---
    # When True, the LLM extractor's result for `group_size`/`group_allocation`/
    # `ages` is actually APPLIED (not just logged) when the regex left them
    # unresolved — the second per-domain cutover. Independent from the Fase 1
    # certification flag: each domain has its own kill switch (plan.md principle
    # #7). Off by default everywhere; the regex stays the primary/fast path —
    # this only fills gaps, never overrides a regex-resolved value.
    llm_extraction_cutover_group: bool = True
    # --- Robustness Fase 3 (docs/robustness/plan.md §4, dominio ubicación) ---
    # When True, the LLM extractor's result for `location`/`island`/`hotel` is
    # actually APPLIED (not just logged) when the regex left them unresolved —
    # the third per-domain cutover. `location` (cartagena|island) drives the
    # logistics/pricing routing and is the high-value field here (the LLM infers
    # it from neighborhoods/landmarks the regex can't enumerate, e.g.
    # "bocagrande"→cartagena); `island`/`hotel` are display/context only and
    # degrade gracefully. Independent kill switch (plan.md #7). Off by default
    # everywhere; the regex stays the primary/fast path — gaps only, never
    # overrides a regex-resolved value.
    llm_extraction_cutover_location: bool = True
    # --- Robustness Fase 8 (docs/robustness/review-2026-07-21.md H5, dominio
    # perfil/logística) ---
    # When True, the LLM extractor's result for `is_colombian`/`duration`/
    # `last_dive_over_2_years` is APPLIED when the regex left them unresolved.
    # `is_colombian` drives currency + the Colombian discount; `duration`
    # (single/multi day) and `last_dive_over_2_years` (refresher signal) tune the
    # package recommendation. The LLM infers these from phrasings the regex can't
    # enumerate ("soy paisa"→colombiano, "toda la semana"→multi_day, "hace como 4
    # años que no buceo"→>2y). Independent kill switch (plan.md #7). Off by
    # default everywhere; regex stays primary — gaps only, never overrides.
    llm_extraction_cutover_logistics: bool = True
    # --- Robustness Fase 9 (docs/multi-agent-refactor-plan.md, hallazgo en vivo
    # conversacion real "purple-sun-590", 2026-09-03) ---
    # A diferencia de los 4 dominios de arriba (que solo rellenan huecos), este
    # veto puede CORREGIR un `activity` que el regex SI resolvio -- solo cuando
    # `intent_detector.matched_activity_categories(message)` marca el mensaje
    # como ambiguo (2+ categorias disparadas a la vez). Ej.: "quiero el open
    # water, nunca he buceado" dispara minicourse Y padi_course; el regex gana
    # por ORDEN de comprobacion (if/elif), no por lo que el cliente pidio de
    # verdad -- y el cutover de certificacion de arriba no lo salva porque
    # 'nunca rellena un campo ya resuelto' es su regla explicita. Dos fases,
    # mismo patron shadow->cutover que los 4 dominios de arriba:
    llm_activity_veto_shadow_mode: bool = False  # mide sin aplicar (loguea discrepancias)
    # CUTOVER por defecto desde 2026-09-14 (antes solo en `.env.pre` del VPS).
    # Criterio para todo el mecanismo: un flag de CUTOVER que ya se midio y
    # decide respuestas vive en el CODIGO, no en un .env que no esta en el repo
    # -- si no, cualquier entorno nuevo (PRO, dev) arranca con el fallo que ya se
    # cerro. Los de SHADOW (solo loguean) siguen en el entorno. Medido: eval-set
    # `activity` 98% con el trigger de ambiguedad (progress-log 2026-09-12).
    llm_activity_veto_cutover: bool = True       # aplica de verdad (corrige activity/service_id)
    # --- Generalizacion del veto por-campo (docs/multi-agent-refactor-plan.md,
    # hallazgo en vivo conversacion real 913, 2026-09-10) ---
    # Mismo mecanismo que `llm_activity_veto_*` (ver `supervisor._VETO_FIELD_
    # SPECS`/`_maybe_veto_resolved_field_via_llm`), extendido a is_certified/
    # is_colombian/location por pedido explicito del usuario ("por bandera").
    # A diferencia de `activity` (evidencia real: conv. 913), estos 3 son
    # paridad PREVENTIVA -- sin bug en vivo que los motive todavia. Los 6
    # flags off por defecto en todas partes; sin ellos, cada campo es un
    # no-op inmediato dentro del bucle de `_understand()`, cero coste.
    llm_certification_veto_shadow_mode: bool = False
    llm_certification_veto_cutover: bool = False
    llm_nationality_veto_shadow_mode: bool = False
    llm_nationality_veto_cutover: bool = False
    llm_location_veto_shadow_mode: bool = False
    llm_location_veto_cutover: bool = False
    # --- Extension a group_size (docs/multi-agent-refactor-plan.md, hallazgo
    # en vivo bateria sintetica, 2026-09-10) ---
    # A diferencia de los 3 de arriba (huecos genericos, sin bug en vivo que
    # los motive), este SI tiene un caso real detectado: "mi pareja y
    # nuestros dos hijos" resuelve group_size=2 (el patron `pareja`->2 gana
    # y nunca suma a los hijos) -- el regex CONTESTA CON CONFIANZA y se
    # equivoca, exactamente el patron de fallo que este mecanismo existe
    # para cazar (fill_gaps no ayuda aqui: su regla es nunca tocar un campo
    # ya resuelto). Un intento de arreglarlo por regex (excluir "mi/tu/su
    # pareja") rompio un caso real validado por el owner
    # (test_owner_conversations_fase1.py::test_scenario3a_couple_group_size_two,
    # donde "con mi pareja" SI debe valer 2) -- revertido. Se deja en manos
    # de este mecanismo en su lugar.
    llm_group_size_veto_shadow_mode: bool = False
    # CUTOVER por defecto desde 2026-09-14 (mismo criterio que
    # `llm_activity_veto_cutover`). Medido en PRE con
    # scripts/battery_group_allocation_gate.py: sin este veto, TOTAL_MAL en 5 de
    # 33 escenarios ("en total 7: 4 certificados..." -> 4, "mi pareja y nuestros
    # dos hijos" -> 2); con el, 0 -- y los controles donde el regex acierta (incl.
    # el caso del owner "con mi pareja" = 2) intactos.
    llm_group_size_veto_cutover: bool = True

    # --- Veto de `group_allocation` (reparto INCOMPLETO pero visible) ---
    # Justificacion real (NO el 91% del eval-set: el unico caso que falla
    # alli es una alucinacion de `fill_gaps` leyendo el historial, y el veto
    # ni se disparia sobre el -- solo actua sobre campos que el REGEX
    # resolvio ESTE turno). El caso que SI motiva esto es otro:
    #   "somos 5: 3 certificados, 1 minicurso y 1 snorkel"
    #   -> group_size=5 (correcto) pero allocation={minicourse:1, snorkel:1}
    # porque "N certificados" sin verbo no matchea `activity_kw`. El total
    # esta bien y el reparto no suma el total: el regex vuelve a CONTESTAR
    # CON CONFIANZA y equivocarse, que es justo lo que este mecanismo caza.
    # Quedo asi tras arreglar que un reparto incompleto redujera ademas el
    # `group_size` declarado (ver progress-log 2026-09-10).
    #
    # Trigger PROPIO (`_group_allocation_should_verify`), no el generico:
    # solo cuando el reparto NO suma el `group_size` conocido. La leccion de
    # `activity` (trigger generico -> 89%->73%, revertido) vale igual aqui,
    # y ademas hace el coste practicamente cero: en los repartos que ya
    # cuadran no se gasta ni una peticion.
    # Off por defecto en todas partes.
    llm_group_allocation_veto_shadow_mode: bool = False
    # CUTOVER por defecto (2026-09-12), a diferencia del resto de campos del
    # mecanismo. No es una excepcion caprichosa: es el unico que se activa con
    # datos medidos de antemano en vez de "a ver que tal". Con el trigger propio
    # (solo dispara si el reparto no suma el total) y la invariante de
    # `enforce_group_allocation_consistency`, la bateria de conversacion da
    # 6/10 repartos correctos frente a 3/10, con 0 repartos parciales y 0
    # alucinaciones en los 10 escenarios de riesgo.
    llm_group_allocation_veto_cutover: bool = True

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
