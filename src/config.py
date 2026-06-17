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
    openai_embedding_model: str = "text-embedding-3-small"
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
    chatwoot_api_token: str = ""
    chatwoot_account_id: int = 1
    chatwoot_inbox_id: int = 1
    chatwoot_owner_agent_id: int = 0  # 0 = auto-assign disabled

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- App ---
    app_env: str = "development"
    app_port: int = 8000
    app_log_level: str = "INFO"
    default_language: str = "es"
    supported_languages: str = "es,en"

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def languages(self) -> list[str]:
        return [lang.strip() for lang in self.supported_languages.split(",")]


settings = Settings()
