from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.observation import ObservationResponse
from app.services.farm_service import get_farm_or_404
from app.services.nasa_power import NASADataError
from app.services.observation_service import get_farm_observations

router = APIRouter(prefix="/farms", tags=["NASA observations"])


@router.get("/{farm_id}/observations", response_model=ObservationResponse)
async def get_observations_endpoint(
    farm_id: str,
    start_date: date = Query(..., description="Start of the historical daily period (YYYY-MM-DD)"),
    end_date: date = Query(default_factory=date.today, description="End of the historical daily period (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    farm = get_farm_or_404(db, farm_id)
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")
    if (end_date - start_date).days > 3660:
        raise HTTPException(status_code=422, detail="The requested period cannot exceed 10 years.")
    try:
        return await get_farm_observations(farm, start_date, end_date)
    except NASADataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
