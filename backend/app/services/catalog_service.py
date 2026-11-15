import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import settings

logger = logging.getLogger(__name__)


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    organization: str
    title: str
    url: str | None = None
    publication_date: str | None = None
    region: str | None = None
    notes: str | None = None


class CropProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crop_id: str
    crop_name: str
    regions: list[str] = Field(default_factory=list)
    seasons: list[str] = Field(default_factory=list)
    duration_days_min: int | None = Field(default=None, ge=1)
    duration_days_max: int | None = Field(default=None, ge=1)
    water_demand_category: str | None = None
    preferred_soil: list[str] = Field(default_factory=list)
    soil_constraints: list[str] = Field(default_factory=list)
    required_soil_fields: list[str] = Field(default_factory=list)
    nutrient_notes: list[str] = Field(default_factory=list)
    rotation_traits: list[str] = Field(default_factory=list)
    known_risks: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "unreviewed"] = "unreviewed"
    unknown_fields: list[str] = Field(default_factory=list)


class RotationRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    title: str
    kind: Literal["hard_constraint", "preference"]
    description: str
    scope_regions: list[str] = Field(default_factory=list)
    scope_seasons: list[str] = Field(default_factory=list)
    condition: dict[str, Any]
    effect: Literal["exclude_if_match", "exclude_if_not_match"] | None = None
    factor: str | None = None
    weight: float | None = Field(default=None, gt=0)
    score_when_match: float | None = Field(default=None, ge=0, le=1)
    score_when_not_match: float | None = Field(default=None, ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low", "unreviewed"] = "unreviewed"


class CropCatalogue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "0.0.0-empty"
    crops: list[CropProfile] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)


class RuleCatalogue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "0.0.0-empty"
    scoring_enabled: bool = False
    rules: list[RotationRule] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)


@dataclass
class EvidenceCatalogue:
    crop_catalogue: CropCatalogue = field(default_factory=CropCatalogue)
    rule_catalogue: RuleCatalogue = field(default_factory=RuleCatalogue)

    @property
    def version(self) -> str:
        return f"crops:{self.crop_catalogue.version}|rules:{self.rule_catalogue.version}"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc


def load_catalogue(directory: Path | None = None) -> EvidenceCatalogue:
    base = directory or settings.crop_catalog_dir
    crop_path = base / "crop_profiles.json"
    rules_path = base / "rotation_rules.json"
    try:
        crops = CropCatalogue.model_validate(_load_json(crop_path))
        rules = RuleCatalogue.model_validate(_load_json(rules_path))
    except ValidationError as exc:
        raise RuntimeError(f"Evidence catalogue failed validation: {exc}") from exc
    return EvidenceCatalogue(crop_catalogue=crops, rule_catalogue=rules)
