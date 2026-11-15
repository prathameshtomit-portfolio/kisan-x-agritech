from datetime import datetime
from typing import Any

from pydantic import Field, ConfigDict

from app.schemas.common import APIModel


class FarmCreate(APIModel):
    name: str = Field(min_length=1, max_length=160)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    region: str | None = Field(default=None, max_length=160)
    season: str | None = Field(default=None, max_length=100)
    area_value: float | None = Field(default=None, gt=0)
    area_unit: str = Field(default="hectare", pattern="^(hectare|acre|square_meter)$")
    crop_history: list[str] = Field(default_factory=list, max_length=30)
    irrigation: str | None = Field(default=None, max_length=100)
    soil_fields: dict[str, Any] = Field(default_factory=dict)
    priorities: list[str] = Field(default_factory=list, max_length=20)
    geometry_geojson: dict[str, Any] | None = None


class FarmUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    region: str | None = Field(default=None, max_length=160)
    season: str | None = Field(default=None, max_length=100)
    area_value: float | None = Field(default=None, gt=0)
    area_unit: str | None = Field(default=None, pattern="^(hectare|acre|square_meter)$")
    crop_history: list[str] | None = Field(default=None, max_length=30)
    irrigation: str | None = Field(default=None, max_length=100)
    soil_fields: dict[str, Any] | None = None
    priorities: list[str] | None = Field(default=None, max_length=20)
    geometry_geojson: dict[str, Any] | None = None


class FarmRead(APIModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    farm_id: str
    name: str
    latitude: float
    longitude: float
    region: str | None
    season: str | None
    area_value: float | None
    area_unit: str
    crop_history: list[str]
    irrigation: str | None
    soil_fields: dict[str, Any]
    priorities: list[str]
    geometry_geojson: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    missing_inputs: list[str]
