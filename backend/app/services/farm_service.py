from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.farm import Farm
from app.schemas.farm import FarmCreate, FarmUpdate


MISSING_FIELD_LABELS = {
    "region": "pilot region",
    "season": "cropping season",
    "area_value": "farm area",
    "irrigation": "irrigation context",
    "soil_fields": "local soil information",
    "crop_history": "crop history",
}


def missing_inputs(farm: Farm) -> list[str]:
    missing = []
    for field in ("region", "season", "area_value", "irrigation"):
        if getattr(farm, field) in (None, ""):
            missing.append(field)
    if not farm.soil_fields:
        missing.append("soil_fields")
    if not farm.crop_history:
        missing.append("crop_history")
    return missing


def create_farm(db: Session, data: FarmCreate) -> Farm:
    farm = Farm(**data.model_dump())
    db.add(farm)
    db.commit()
    db.refresh(farm)
    return farm


def get_farm_or_404(db: Session, farm_id: str) -> Farm:
    farm = db.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(status_code=404, detail=f"Farm '{farm_id}' was not found.")
    return farm


def update_farm(db: Session, farm: Farm, data: FarmUpdate) -> Farm:
    changes: dict[str, Any] = data.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to update.")
    for field, value in changes.items():
        setattr(farm, field, value)
    db.add(farm)
    db.commit()
    db.refresh(farm)
    return farm
