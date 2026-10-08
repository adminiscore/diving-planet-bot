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
    openai_model: str = "gpt-4o-mini"
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
    extraction_model: str = "gpt-4o-mini"
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
    openai_transcription_model: str = "gpt-4o-mini-transcribe"
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

    # Paso 5 (RAG, l1-6 + l1-7, 27-sep): (a) el catalogo entero como hechos en el contexto del RAG
    # en vez de los atajos de precio por regex, que contestaban preguntas que no eran de precio;
    # (b) juez de grounding que solo rechaza DATOS DEL NEGOCIO sin respaldo (saludos, cortesia y
    # "no lo tengo" iban al fallback), con el modelo de la respuesta; (c) la pregunta de
    # disponibilidad la contesta el RAG entera en vez de un texto fijo que se comia el resto del
    # mensaje. Ronda A: 37 respuestas acabaron en "no lo tengo a la mano". ENCENDIDO por defecto (= PRE, paso 10).
    rag_v2: bool = True
    # Juez de grounding v3 (28-sep): enumera cada dato del negocio de la respuesta y lo marca SÍ/NO frente
    # al contexto; el veredicto lo calcula el codigo con esas marcas. Con gpt-4.1: banco
    # `scripts/sonda_juez_grounding.py` 30/30 estable (v2 con gpt-4.1-mini: 21/30, dejaba pasar "llevamos
    # 30 años", "debes haber completado la teoría", "hay barcos hundidos"); +0,25 s de mediana. ENCENDIDO por defecto (= PRE, paso 10).
    # 28-sep (HISTORY 0.29.66): v3 con gpt-4.1-mini 48/70 y gpt-4o-mini 37/70 frente a 70/70, y NO más rápidos: se queda gpt-4.1.
    grounding_v3: bool = True
    grounding_v3_model: str = "gpt-4.1"
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
    rag_respaldo_modelo: str = "gpt-4.1-mini"
    rag_respaldo_segundos: float = 3.0
    # 8-oct (prueba de DeepSeek): un modelo con prefijo de proveedor ("deepseek/deepseek-v4.1-flash") sale por
    # OpenRouter (`llm_client.parametros_openrouter`), solo por estos proveedores (separados por comas, por latencia,
    # sin retención de datos). "deepseek" = la API oficial (servidores en China: solo para pruebas sin datos de
    # clientes); "baseten,fireworks/us,coreweave" = EE. UU. Vacío = cualquiera, por latencia.
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_proveedores: str = "baseten,fireworks/us,coreweave"
    # OpenRouter solo deja usar la API oficial de DeepSeek si se acepta que ENTRENEN con los datos (su politica "Paid
    # model training"). Apagado = nunca. Solo para pruebas con datos anonimizados; nunca con clientes reales.
    openrouter_permitir_entrenamiento: bool = False
    # J2 (1-oct): segunda opinion de Jev sobre las frases que el juez marca NO (src/agents/juez_segunda_opinion.py).
    # Solo cuando el juez rechaza; si Jev esta seguro de que ninguna afirma nada del negocio, la respuesta pasa.
    # rag_piezas 1-oct (96 respuestas por lado): cobertura 88 -> 90 %, contradicciones 3 -> 1, misma latencia. Calibrado
    # (scripts/sonda_juez_jev.py): 0 afirmaciones del negocio colan de 102.
    # PROMOCIONADO 1-oct (Gonzalo, ronda core 2026-10-01-juez-B, HISTORY 0.29.90): rescata 1, mantiene 3, y el rescate
    # leido a mano no cuela ningun invento (era "te lo confirma un asesor"). Por construccion nunca empeora nada: solo
    # convierte un rechazo en aprobado, y solo si Jev esta seguro. Umbral 0,2: en la ronda dejo SIN rescatar "para
    # proceder con la cancelacion, te paso con un asesor" (p=0,25) y eso costo una regresion — primer dato real para
    # el umbral, pero un caso no basta para subirlo. Revert = False aqui y en el compose.
    juez_segunda_opinion: bool = True
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
    # Paso 9 (l2-2, 28-sep): el catalogo va al final del prompt del SISTEMA (fijo por idioma) y el primero en
    # el contexto del juez, para que el prompt caching de OpenAI lo reutilice entre conversaciones (antes iba
    # en el mensaje del usuario, detras del historial: nunca se cacheaba). ENCENDIDO por defecto (= PRE, paso 10).
    rag_prompt_cache: bool = True
    # Latencia del RAG (28-sep): la respuesta contesta SOLO lo preguntado, en 2-4 frases, y ofrece ampliar (la
    # intro cálida se queda, en una frase). Escribir la respuesta crece con la longitud (220 caracteres 1,1 s,
    # 720 caracteres 2,8 s); la mediana era ~680. Decisión del owner. APAGADO hasta su A/B (prompts/info.py).
    # Escalón 0 (HISTORY 0.29.67): con tope de longitud comprime e inventa huecos; la variante suave del código no.
    rag_concise: bool = False
    # 28-sep: si el juez (o un guard) rechaza la respuesta, la segunda muestra recibe QUÉ se rechazó para quitarlo
    # y conservar el resto; antes se repetía la misma petición y el modelo repetía el invento (12 de 32 turnos del
    # paso 8 acababan así en "no lo tengo"). El juez sigue juzgando la segunda. PROMOCIONADO 28-sep (HISTORY 0.29.68):
    # escalón 0 12 -> 2 "no lo tengo"; core regen-A 93,0 % -> regen-B2 93,3 %, sin regresiones del flag.
    rag_regen_feedback: bool = True
    # rag-2 (29-sep, fase RAG de Plan Coral): la busqueda lee la base curada del esquema `kb_v2` (una ficha por
    # servicio y origen, FAQs sin telefono ni listas de precios, politicas con sus formas de preguntarlas;
    # `scripts/kb_v2.py`). Apagado = `public.kb_documents` de siempre. PROMOCIONADO 29-sep (HISTORY 0.29.72): core
    # rag2-A 92,5 % -> rag2-B 94,3 %, sin regresiones atribuibles. Marcha atras: apagarlo (aqui y en el compose).
    rag_kb_v2: bool = True
    # Esquema de la base v2 que lee la busqueda con `rag_kb_v2`. Solo para medir una base nueva sin tocar la que usa
    # PRE (p. ej. RAG_KB_ESQUEMA=kb_v2_prueba con `rag_piezas --codigo-local`); en PRE es siempre "kb_v2".
    rag_kb_esquema: str = "kb_v2"
    # rag-3 (29-sep): si ya se sabe QUE servicio mira el cliente, su ficha entera (la misma que la de la base v2,
    # `catalog.service_fact_sheet`) va SIEMPRE al contexto, en vez de depender de que la busqueda la encuentre.
    # Motivo medido (`rag_piezas`, 2026-09-28-rag2-B2): con `selected_service` puesto, la ficha NO entraba en el
    # top-8 ante preguntas genericas -- "what time does the course finish on the first day?" con el Open Water
    # elegido, y la direccion del centro con el Curso Referido. El dato existe (el itinerario lleva la hora de
    # encuentro); el problema es de busqueda. Sustituye a la inyeccion parcial de incluye/no incluye, que se
    # quedaba corta. APAGADO hasta su A/B (rag_piezas + ronda core).
    rag_ficha_del_servicio: bool = False
    # rag-3 (30-sep, Gadea): con el origen del cliente en el estado (Cartagena / ya en las islas), la busqueda baja
    # las fichas del OTRO origen. Offline (47 preguntas visibles): quita las 10 fichas del origen equivocado que se
    # colaban en el top-8 sin perder ningun dato. El origen llega del estado (`state.location`), no de leer el
    # resumen: la deteccion por frases solo funcionaba en espanol. PROMOCIONADO 30-sep (HISTORY 0.29.85).
    rag_busqueda_origen: bool = True
    # 1-oct (analisis del juez, docs/robustness/juez/README.md): se busca tambien con la pregunta tal cual y se unen
    # los dos rankings por posicion. La reescritura se comia el tema en 7 de 54 rechazos del juez ("how do i pay" ->
    # "How do I pay for the Fun Dives?"). ENCENDIDO para la medida (rag_piezas y ronda core).
    # SIN DECIDIR tras la ronda core 2026-10-01-juez-B (HISTORY 0.29.90), a proposito: esa ronda cambia a la vez esto,
    # J2 y los datos nuevos del 1-oct, asi que no aisla su efecto; y rag_piezas no lo ve (mide preguntas sueltas, y la
    # reescritura depende del historial). Unico indicio a favor: el formulario medico del refresher pasa a cumplir, que
    # era un fallo de busqueda conocido. Coste: +33 % de busquedas por turno (0,98 -> 1,30), baratas. Para decidir hace
    # falta una ronda core con SOLO este interruptor cambiado.
    # 2-oct (Alvaro, paso 4): ronda aislada 2026-10-02-busqueda-simple (APAGADO, todo lo demas igual) frente a
    # 2026-10-01-privacidad-B (encendido): criterios 94,3 % encendido / 93,4 % apagado (ruido), RAG p50 3,36 / 3,29 s
    # (igual: las dos busquedas van a la vez), busquedas por turno 1,39 / 1,00. Encendido, 11 de 38 respuestas
    # reciben 1-4 piezas mas; la que se nota es "how do i pay" (el pago por transferencia si falla el online, el caso
    # que lo motivo). Ninguna regresion de la ronda apagada viene de la busqueda. PROMOCIONADO 2-oct (HISTORY
    # 0.29.94). Revert = False aqui y en el compose.
    rag_busqueda_doble: bool = True
    # rag-5 (30-sep): el RAG arranca a la vez que el enrutador (Jev) en vez de despues, y se aprovecha solo si su
    # contexto es exactamente el de la llamada de siempre (si no, se rehace). Estimado: -0,7 s por pregunta, ~+20 %
    # de coste (los RAG que se descartan en turnos sin pregunta). Medido (rag5-A/B, HISTORY 0.29.86): -1,2 s cuando
    # se aprovecha, pero solo en el 29 % de los turnos RAG; calidad igual. Con la puerta de notas, el primer mensaje y
    # el buceo adaptado (ronda rag5-C, HISTORY 0.29.88): aprovechado 36 de 40, RAG p50 5,37 -> 3,44 s, 23/32.
    # PROMOCIONADO 1-oct. Revert = "false" aqui y en docker-compose.vps.yml.
    rag_adelantado: bool = True
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
