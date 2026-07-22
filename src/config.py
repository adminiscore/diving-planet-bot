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
    openai_model: str = "gpt-4o"
    # Model for the narrow, structured LLM gap-filler extractor
    # (src/agents/llm_extractor.py, robustness Fases 1-3). Kept SEPARATE from
    # openai_model (used by the action orchestrator): the extraction is a small
    # forced-tool-call task where a cheaper/faster model suffices. Measured on
    # docs/robustness/eval-set.json (64 cases): gpt-4o-mini = 98.4% vs gpt-4o =
    # 99.2% — the only difference is 1 extra `missed` (it abstains on a hard
    # implicit-count case rather than misfilling), so its failure mode is safe
    # (degrades to "regex-only / ask", never to a wrong value). ~15-30x cheaper
    # and faster per call. Revert to "gpt-4o" here if ever needed. See
    # docs/robustness/progress-log.md (Fase 4).
    extraction_model: str = "gpt-4o-mini"
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

    # --- LangSmith ---
    langsmith_api_key: str = ""
    langsmith_project: str = "diving-planet-bot"
    langchain_tracing_v2: bool = True

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

    # --- Conversation memory (Fase A, docs/memory-context-improvement-plan.md) ---
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

    # --- Núcleo conversacional (docs/conversational-refactor-plan.md) ---
    # When True, free-text messages are driven by the slot-filling conversational
    # core (src/agents/conversational_core.py: comprender → resolver → responder)
    # instead of the button-menu MIXED_* state machine. The cart stays as the
    # internal data model; the menus stop being the driver. Off by default
    # everywhere — enabled per environment (PRE first) behind this flag, fully
    # reversible without a code rollback (plan: migración incremental por
    # vertical). The extractor cutover flags above keep their own kill switches;
    # the core calls the gap-filler directly as its slot engine.
    conversational_core: bool = False

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def languages(self) -> list[str]:
        return [lang.strip() for lang in self.supported_languages.split(",")]


settings = Settings()
