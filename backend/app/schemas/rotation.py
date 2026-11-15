from typing import Any, Literal

from pydantic import Field

from app.schemas.common import APIModel


class RotationCandidate(APIModel):
    rotation_id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    sequence: list[str] = Field(min_length=2, max_length=12)
    assumptions: list[str] = Field(default_factory=list)


class RotationCompareRequest(APIModel):
    farm_id: str
    candidates: list[RotationCandidate] = Field(min_length=1, max_length=10)
    priorities: list[str] | None = None
    priority_weights: dict[str, float] | None = None
    save_report: bool = True


class PreferenceFit(APIModel):
    factor: str
    impact: Literal["supports", "trade_off", "unknown"]
    explanation: str
    rule_id: str
    evidence_ids: list[str]


class RotationOptionResult(APIModel):
    rotation_id: str
    label: str
    sequence: list[str]
    eligibility: Literal["eligible", "ineligible", "uncertain"]
    rank: int | None = None
    score: float | None = None
    priority_fit: list[PreferenceFit] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rules_triggered: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence_note: str


class RotationCompareResponse(APIModel):
    report_id: str | None = None
    farm_id: str
    generated_at: str
    evidence_status: Literal["sufficient", "partial", "insufficient"]
    ranking_method: str | None
    rotations: list[RotationOptionResult]
    missing_inputs: list[str]
    limitations: list[str]
    rulebook_version: str
    software_version: str
