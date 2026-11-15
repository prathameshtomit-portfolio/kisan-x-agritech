from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.report import ReportRead
from app.services.report_service import get_report_or_404

router = APIRouter(prefix="/reports", tags=["decision reports"])


@router.get("/{report_id}", response_model=ReportRead)
def get_report_endpoint(report_id: str, db: Session = Depends(get_db)):
    report = get_report_or_404(db, report_id)
    return ReportRead.model_validate(report)
