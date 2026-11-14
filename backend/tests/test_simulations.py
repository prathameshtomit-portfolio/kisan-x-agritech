from types import SimpleNamespace

from app.schemas.rotation import RotationCandidate
from app.services.catalog_service import EvidenceCatalogue
from app.services.simulation_service import run_scenario


def test_scenario_keeps_baseline_and_records_only_changes():
    farm = SimpleNamespace(
        farm_id="farm-1",
        region=None,
        season=None,
        irrigation="reliable",
        soil_fields={"pH": None},
        crop_history=[],
        priorities=[],
    )
    candidates = [RotationCandidate(rotation_id="r1", label="Example", sequence=["a", "b"])]
    baseline, scenario, changes, _ = run_scenario(
        farm,
        candidates,
        {"irrigation": "limited", "rainfall_change_pct": -15},
        EvidenceCatalogue(),
    )
    assert farm.irrigation == "reliable"  # source farm was not mutated
    assert "irrigation" in changes
    assert "rainfall_change_pct" in changes
    assert baseline.rotations[0].eligibility == "uncertain"
    assert scenario.rotations[0].eligibility == "uncertain"


def test_extended_scenarios_are_recorded_without_inventing_financial_outcomes():
    farm = SimpleNamespace(
        farm_id="farm-1",
        region="Nagpur",
        season="kharif",
        irrigation="rainfed",
        soil_fields={},
        crop_history=[],
        priorities=[],
    )
    candidates = [RotationCandidate(rotation_id="r1", label="Option", sequence=["a", "b"])]
    baseline, scenario, changes, _ = run_scenario(
        farm,
        candidates,
        {
            "sowing_delay_days": 14,
            "water_availability_change_pct": -50,
            "input_cost_change_pct": 20,
            "sale_price_change_pct": -10,
        },
        EvidenceCatalogue(),
    )

    assert baseline.rotations[0].eligibility == "uncertain"
    assert scenario.rotations[0].eligibility == "uncertain"
    assert changes["sowing_delay_days"]["scenario"] == 14
    assert changes["sowing_delay_days"]["decision_effect"] == "recorded_only_no_matching_reviewed_rule"
    assert changes["input_cost_change_pct"]["type"].startswith("hypothetical cost/market shock")
    assert changes["sale_price_change_pct"]["decision_effect"] == "recorded_only_no_matching_reviewed_rule"
