from datetime import datetime
from typing import Any

from pydantic import ConfigDict

from app.schemas.common import APIModel


class ReportRead(APIModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    report_id: str
    farm_id: str
    report_type: str
    rulebook_version: str | None
    created_at: datetime
    payload: dict[str, Any]
