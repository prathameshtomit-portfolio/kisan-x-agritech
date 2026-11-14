from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.report import DecisionReport


def create_report(db: Session, farm_id: str, report_type: str, rulebook_version: str | None, payload: dict) -> DecisionReport:
    report = DecisionReport(
        farm_id=farm_id,
        report_type=report_type,
        rulebook_version=rulebook_version,
        payload=payload,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def get_report_or_404(db: Session, report_id: str) -> DecisionReport:
    report = db.get(DecisionReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' was not found.")
    return report
