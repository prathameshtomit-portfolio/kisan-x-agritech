from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.farm import Farm
from app.schemas.farm import FarmCreate, FarmRead, FarmUpdate
from app.services.farm_service import create_farm, get_farm_or_404, missing_inputs, update_farm

router = APIRouter(prefix="/farms", tags=["farms"])


def _farm_read(farm) -> FarmRead:
    payload = {
        "farm_id": farm.farm_id,
        "name": farm.name,
        "latitude": farm.latitude,
        "longitude": farm.longitude,
        "region": farm.region,
        "season": farm.season,
        "area_value": farm.area_value,
        "area_unit": farm.area_unit,
        "crop_history": farm.crop_history or [],
        "irrigation": farm.irrigation,
        "soil_fields": farm.soil_fields or {},
        "priorities": farm.priorities or [],
        "geometry_geojson": farm.geometry_geojson,
        "created_at": farm.created_at,
        "updated_at": farm.updated_at,
        "missing_inputs": missing_inputs(farm),
    }
    return FarmRead.model_validate(payload)


@router.post("", response_model=FarmRead, status_code=status.HTTP_201_CREATED)
def create_farm_endpoint(payload: FarmCreate, db: Session = Depends(get_db)):
    return _farm_read(create_farm(db, payload))


@router.get("", response_model=list[FarmRead])
def list_farms_endpoint(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List farm profiles for app dashboards, newest first."""
    farms = db.scalars(
        select(Farm).order_by(Farm.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return [_farm_read(farm) for farm in farms]


@router.get("/{farm_id}", response_model=FarmRead)
def get_farm_endpoint(farm_id: str, db: Session = Depends(get_db)):
    return _farm_read(get_farm_or_404(db, farm_id))


@router.patch("/{farm_id}", response_model=FarmRead)
def update_farm_endpoint(farm_id: str, payload: FarmUpdate, db: Session = Depends(get_db)):
    farm = get_farm_or_404(db, farm_id)
    return _farm_read(update_farm(db, farm, payload))
