from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.rotation import RotationCompareRequest, RotationCompareResponse
from app.services.catalog_service import load_catalogue
from app.services.farm_service import get_farm_or_404
from app.services.report_service import create_report
from app.services.rotation_engine import compare_rotations

router = APIRouter(prefix="/rotations", tags=["rotation decision support"])


@router.post("/compare", response_model=RotationCompareResponse)
def compare_rotations_endpoint(payload: RotationCompareRequest, db: Session = Depends(get_db)):
    farm = get_farm_or_404(db, payload.farm_id)
    catalogue = load_catalogue()
    result = compare_rotations(
        farm,
        payload.candidates,
        catalogue,
        priorities=payload.priorities,
        priority_weights=payload.priority_weights,
    )
    if payload.save_report:
        report = create_report(
            db,
            farm.farm_id,
            "rotation_comparison",
            catalogue.version,
            result.model_dump(mode="json"),
        )
        result.report_id = report.report_id
    return result
