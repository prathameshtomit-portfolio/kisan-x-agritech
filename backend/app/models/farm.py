from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, Float, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Farm(Base):
    __tablename__ = "farms"

    farm_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    region: Mapped[str | None] = mapped_column(String(160), nullable=True)
    season: Mapped[str | None] = mapped_column(String(100), nullable=True)
    area_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_unit: Mapped[str] = mapped_column(String(20), default="hectare", nullable=False)
    crop_history: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    irrigation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    soil_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    priorities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    geometry_geojson: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
