from pydantic import BaseModel


class ValidateRequest(BaseModel):
    """Request body for POST /validate."""

    query: str


class RulesRequest(BaseModel):
    """Request body for POST /rules."""

    rules: str


class BookRequest(BaseModel):
    """Request body for POST /validate/book."""

    instrument_ids: list[str] | None = None


class SecurityToggleRequest(BaseModel):
    """Request body for POST /security."""

    enabled: bool
