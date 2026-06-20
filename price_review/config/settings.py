from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    google_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    )
    llm_model: str = DEFAULT_GEMINI_MODEL
    optional_finnhub_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPTIONAL_FINNHUB_API_KEY",
    )
    market_context_cache_ttl_seconds: int = 900
    port: int = 7860

    @staticmethod
    def _key_present(key: SecretStr | None) -> bool:
        if key is None:
            return False
        return bool(key.get_secret_value().strip())

    @property
    def has_llm_key(self) -> bool:
        return self._key_present(self.google_api_key)

    @property
    def optional_finnhub_enabled(self) -> bool:
        return self._key_present(self.optional_finnhub_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
