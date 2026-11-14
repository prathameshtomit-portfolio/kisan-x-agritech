from typing import Any

from pydantic import Field, model_validator

from app.schemas.common import APIModel
from app.schemas.rotation import RotationCandidate, RotationCompareResponse


class ScenarioInputs(APIModel):
    irrigation: str | None = Field(default=None, max_length=100)
    rainfall_change_pct: float | None = Field(default=None, ge=-100, le=100)
    sowing_delay_days: int | None = Field(default=None, ge=0, le=120)
    water_availability_change_pct: float | None = Field(default=None, ge=-100, le=100)
    input_cost_change_pct: float | None = Field(default=None, ge=-100, le=500)
    sale_price_change_pct: float | None = Field(default=None, ge=-100, le=500)
    soil_fields: dict[str, Any] | None = None

    @model_validator(mode="after")
    def at_least_one_override(self):
        if all(value is None for value in (
            self.irrigation,
            self.rainfall_change_pct,
            self.sowing_delay_days,
            self.water_availability_change_pct,
            self.input_cost_change_pct,
            self.sale_price_change_pct,
            self.soil_fields,
        )):
            raise ValueError("Provide at least one hypothetical scenario input.")
        return self


class SimulationRequest(APIModel):
    farm_id: str
    candidates: list[RotationCandidate] = Field(min_length=1, max_length=10)
    scenario: ScenarioInputs
    priorities: list[str] | None = None
    priority_weights: dict[str, float] | None = None


class SimulationResponse(APIModel):
    report_id: str
    farm_id: str
    generated_at: str
    scenario_label: str
    changed_inputs: dict[str, Any]
    baseline: RotationCompareResponse
    scenario_result: RotationCompareResponse
    interpretation: str
    limitations: list[str]
