from datetime import date, datetime
from typing import Any

from pydantic import Field

from app.schemas.common import APIModel


class ObservationRecord(APIModel):
    source_id: str
    provider: str
    product: str
    source_version: str | None = None
    variable: str
    raw_parameter: str
    value: float | None
    unit: str
    observed_at: date
    latitude: float
    longitude: float
    spatial_scale: str
    spatial_resolution: str = "Parameter-specific; see source product metadata."
    temporal_scale: str
    time_standard: str = "UTC"
    coverage_fraction: float | None = Field(default=None, ge=0, le=1)
    observation_type: str
    quality_flag: str
    retrieved_at: datetime
    source_url: str
    limitations: list[str]
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class ObservationResponse(APIModel):
    farm_id: str
    period_start: date
    period_end: date
    retrieval_status: str
    observations: list[ObservationRecord]
    missing_values: int
    source_notes: list[str]
