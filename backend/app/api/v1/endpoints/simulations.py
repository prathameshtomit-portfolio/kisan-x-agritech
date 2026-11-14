from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.simulation import SimulationRequest, SimulationResponse
from app.services.catalog_service import load_catalogue
from app.services.farm_service import get_farm_or_404
from app.services.report_service import create_report
from app.services.simulation_service import run_scenario

router = APIRouter(prefix="/simulations", tags=["what-if simulations"])


@router.post("", response_model=SimulationResponse)
def run_simulation_endpoint(payload: SimulationRequest, db: Session = Depends(get_db)):
    farm = get_farm_or_404(db, payload.farm_id)
    catalogue = load_catalogue()
    baseline, scenario_result, changed_inputs, generated_at = run_scenario(
        farm,
        payload.candidates,
        payload.scenario.model_dump(exclude_none=True),
        catalogue,
        priorities=payload.priorities,
        priority_weights=payload.priority_weights,
    )
    response = SimulationResponse(
        report_id="pending",
        farm_id=farm.farm_id,
        generated_at=generated_at,
        scenario_label="Hypothetical scenario — not a forecast",
        changed_inputs=changed_inputs,
        baseline=baseline,
        scenario_result=scenario_result,
        interpretation=(
            "The same candidate rotations were re-evaluated after changing only the inputs listed in changed_inputs. "
            "A scenario can affect eligibility or preference only when a scope-matched, reviewed rule consumes that input. "
            "Results remain limited by the loaded agronomy evidence and known farm inputs."
        ),
        limitations=[
            "Rainfall change is a user-entered stress-test assumption, not a weather forecast.",
            "The scenario does not predict yield, profit, or future weather.",
            "Cost and sale-price shocks are recorded assumptions; no financial outcome is calculated without reviewed crop-specific cost/price data and a documented model.",
            "Unknown baseline soil values remain unknown unless the scenario explicitly overrides that field.",
        ],
    )
    report = create_report(
        db,
        farm.farm_id,
        "what_if_simulation",
        catalogue.version,
        response.model_dump(mode="json"),
    )
    response.report_id = report.report_id
    response.baseline.report_id = None
    response.scenario_result.report_id = None
    report.payload = response.model_dump(mode="json")
    db.add(report)
    db.commit()
    return response
