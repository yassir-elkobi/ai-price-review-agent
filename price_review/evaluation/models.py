from typing import Literal

from pydantic import BaseModel

Status = Literal["pass", "amber", "fail"]


class ScenarioResult(BaseModel):
    """Outcome of replaying one scenario against the live agent."""

    id: str
    title: str
    difficulty: str
    status: Status
    decision_correct: bool
    completeness_ok: bool
    final_answer: str
    expected: list[dict]
    actual: list[dict]
    notes: str = ""


class EvaluationReport(BaseModel):
    """Aggregated score across all evaluated scenarios."""

    total: int
    passed: int
    failed: int
    score: float
    score_by_rule: dict[str, float]
    score_by_asset_class: dict[str, float]
    results: list[ScenarioResult]
