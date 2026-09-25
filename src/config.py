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
    # OJO: este default NO es el de PRE. PRE fija OPENAI_MODEL=gpt-4o-mini en .env.pre;
    # un entorno que no lo fije mide con gpt-4o, o sea otro bot. Mapa de modelos:
    # README.md, "LLM models". Hoy lo usan condense_query, el juez de grounding, el
    # detector de idioma, el resumen y la respuesta del RAG si RAG_ANSWER_MODEL esta vacio.
    openai_model: str = "gpt-4o"
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
    # string (default) means "use `openai_model`", i.e. zero behavior change
    # until explicitly set. Hallazgo en vivo (2026-09-03): gpt-4o-mini
    # ignora la regla de "certificado-pero-inactivo" (ver
    # docs/multi-agent-refactor-plan.md §7) pese a tenerla correctamente
    # inyectada en el contexto, en ~1/3 de las repeticiones -- un techo real
    # de fiabilidad del modelo, no un bug de codigo. gpt-5-mini/o-series NO
    # sirven aqui sin cambios de codigo adicionales (no soportan
    # `temperature`, usan `reasoning_effort`); cualquier modelo puesto aqui
    # debe seguir aceptando `temperature`/`max_tokens` como hoy (gpt-4.1-mini,
    # gpt-4o, etc.).
    rag_answer_model: str = ""
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
    notes_in_parallel: bool = False

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
    # serie: su resumen necesita el valor recién extraído. APAGADO por defecto.
    ack_in_parallel: bool = False

    # u3-4 (24-sep): "contesta y sigue". Un mensaje que trae una pregunta (regex, "?" o
    # Jev >= 0,7 en la MISMA llamada del router) ya no se trata como pregunta O como dato:
    # el RAG la contesta en paralelo, la extracción sigue su camino normal y la respuesta
    # lleva las dos cosas (primero la respuesta, luego lo que toque de la reserva). Ver
    # docs/robustness/u3-4-diseno.md. APAGADO por defecto.
    answer_and_continue: bool = False

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
    agent_arch: bool = False

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
    llm_extraction_cutover_certification: bool = False
    # --- Robustness Fase 2 (docs/robustness/plan.md §4, dominio grupo/cantidad/edades) ---
    # When True, the LLM extractor's result for `group_size`/`group_allocation`/
    # `ages` is actually APPLIED (not just logged) when the regex left them
    # unresolved — the second per-domain cutover. Independent from the Fase 1
    # certification flag: each domain has its own kill switch (plan.md principle
    # #7). Off by default everywhere; the regex stays the primary/fast path —
    # this only fills gaps, never overrides a regex-resolved value.
    llm_extraction_cutover_group: bool = False
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
    llm_extraction_cutover_location: bool = False
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
    llm_extraction_cutover_logistics: bool = False
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
