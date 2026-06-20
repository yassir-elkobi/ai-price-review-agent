import pytest

from price_review.agent.llm import build_llm, format_llm_error
from price_review.config import DEFAULT_GEMINI_MODEL, Settings, get_settings


class TestGeminiSettings:
    def test_default_model_is_gemini_25_flash(self, monkeypatch):
        monkeypatch.delenv("LLM_MODEL", raising=False)
        get_settings.cache_clear()
        assert get_settings().llm_model == DEFAULT_GEMINI_MODEL
        get_settings.cache_clear()

    def test_build_llm_raises_without_key(self):
        with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
            build_llm(Settings(google_api_key=None))


class TestFormatLlmError:
    def test_rate_limit(self):
        assert "rate limit" in format_llm_error(Exception("429 Too Many Requests")).lower()

    def test_passthrough_generic(self):
        assert format_llm_error(Exception("Something else broke")) == "Something else broke"
