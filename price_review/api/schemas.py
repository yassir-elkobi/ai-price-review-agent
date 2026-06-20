from pydantic import BaseModel


class ValidateRequest(BaseModel):
    query: str


class RulesRequest(BaseModel):
    rules: str
