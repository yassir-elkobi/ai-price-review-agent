from langchain_core.language_models.chat_models import BaseChatModel

from price_review.config import DEFAULT_GEMINI_MODEL, Settings, get_settings

GEMINI_KEY_URL = "https://aistudio.google.com/apikey"


def build_llm(settings: Settings | None = None) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    settings = settings or get_settings()
    model = settings.llm_model or DEFAULT_GEMINI_MODEL

    if not settings.has_llm_key or settings.google_api_key is None:
        raise RuntimeError(f"GOOGLE_API_KEY is missing. Create a key at {GEMINI_KEY_URL}.")

    return ChatGoogleGenerativeAI(
        model=model,
        temperature=0,
        max_retries=2,
        google_api_key=settings.google_api_key.get_secret_value(),
    )


def format_llm_error(exc: Exception) -> str:
    msg = str(exc)
    upper = msg.upper()

    if "RESOURCE_EXHAUSTED" in upper or "429" in msg:
        if "limit: 0" in msg or "LIMIT: 0" in upper:
            return "Gemini quota is 0 for this model. Check AI Studio usage or retry later."
        return "Gemini rate limit (429). Wait and retry."

    if "401" in msg or "UNAUTHENTICATED" in upper or "API KEY" in upper:
        return f"Invalid or missing GOOGLE_API_KEY ({GEMINI_KEY_URL})."

    return msg
