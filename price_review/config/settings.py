from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CLAUDE_MODEL = "claude-sonnet-5"


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "CLAUDE_API_KEY"),
    )
    llm_model: str = DEFAULT_CLAUDE_MODEL
    port: int = 7860

    # Qdrant Cloud (decision history RAG); falls back to in-memory when unset.
    qdrant_url: str | None = None
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "decision_history"

    # Neo4j Aura (sector GraphRAG); falls back to a local fixture when unset.
    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: SecretStr | None = None

    # Prompt-injection guard, toggleable at runtime.
    security_enabled: bool = True

    @staticmethod
    def _key_present(key: SecretStr | None) -> bool:
        if key is None:
            return False
        return bool(key.get_secret_value().strip())

    @property
    def has_llm_key(self) -> bool:
        return self._key_present(self.anthropic_api_key)

    @property
    def has_qdrant_cloud(self) -> bool:
        return bool(self.qdrant_url and self.qdrant_url.strip())

    @property
    def has_neo4j(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_uri.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
