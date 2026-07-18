from langchain_core.language_models.chat_models import BaseChatModel

from price_review.config import DEFAULT_CLAUDE_MODEL, Settings, get_settings

CLAUDE_KEY_URL = "https://console.anthropic.com/settings/keys"


def build_llm(settings: Settings | None = None) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    settings = settings or get_settings()
    model = settings.llm_model or DEFAULT_CLAUDE_MODEL

    if not settings.has_llm_key or settings.anthropic_api_key is None:
        raise RuntimeError(f"ANTHROPIC_API_KEY is missing. Create a key at {CLAUDE_KEY_URL}.")

    return ChatAnthropic(
        model=model,
        max_retries=2,
        api_key=settings.anthropic_api_key.get_secret_value(),
    )


def format_llm_error(exc: Exception) -> str:
    msg = str(exc)
    upper = msg.upper()

    if "RATE_LIMIT" in upper or "429" in msg:
        return "Claude rate limit (429). Wait and retry."

    if "OVERLOADED" in upper or "529" in msg:
        return "Claude API is overloaded (529). Retry shortly."

    if "401" in msg or "UNAUTHORIZED" in upper or "AUTHENTICATION" in upper or "API KEY" in upper:
        return f"Invalid or missing ANTHROPIC_API_KEY ({CLAUDE_KEY_URL})."

    if "CREDIT" in upper or "BILLING" in upper or "402" in msg:
        return "Anthropic account has insufficient credits. Check billing at console.anthropic.com."

    return msg
