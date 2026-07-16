from typing import Literal

from pydantic import BaseModel, Field

Difficulty = Literal["easy", "medium", "hard", "extreme"]
Decision = Literal["APPROVED", "REJECTED", "ESCALATE"]


class ExpectedOutcome(BaseModel):
    """Expected verdict for one instrument within a scenario."""

    instrument_id: str
    decision: Decision
    rule_ref: int = Field(ge=1, le=5)


class Scenario(BaseModel):
    """One live-demo scenario: a query plus its expected outcomes."""

    id: str
    title: str
    title_fr: str
    difficulty: Difficulty
    query: str
    instrument_ids: list[str] = Field(default_factory=list)
    expected_outcomes: list[ExpectedOutcome] = Field(default_factory=list)
    teaching_note: str
    teaching_note_fr: str
    featured: bool = False
    live_flip_hint: str | None = None
    live_flip_hint_fr: str | None = None


class ScenarioCatalog(BaseModel):
    """Full set of scenarios loaded from data/scenarios.json."""

    scenarios: list[Scenario]
