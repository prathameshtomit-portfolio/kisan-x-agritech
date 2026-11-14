from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from app.schemas.rotation import RotationCandidate
from app.services.catalog_service import EvidenceCatalogue
from app.services.rotation_engine import compare_rotations

SCENARIO_RULE_TYPES = {
    "rainfall_change_pct": "rainfall_change_pct_operator",
    "sowing_delay_days": "sowing_delay_days_operator",
    "water_availability_change_pct": "water_availability_change_pct_operator",
    "input_cost_change_pct": "input_cost_change_pct_operator",
    "sale_price_change_pct": "sale_price_change_pct_operator",
    "irrigation": "irrigation_in",
    "soil_fields": "soil_field_operator",
}


def _scenario_rule_metadata(field: str, farm: Any, catalogue: EvidenceCatalogue, subfield: str | None = None) -> dict[str, Any]:
    expected_type = SCENARIO_RULE_TYPES[field]
    known_source_ids = {
        source.source_id
        for source in catalogue.crop_catalogue.sources + catalogue.rule_catalogue.sources
    }
    rules = [
        rule for rule in catalogue.rule_catalogue.rules
        if rule.condition.get("type") == expected_type
        and (not rule.scope_regions or farm.region in rule.scope_regions)
        and (not rule.scope_seasons or farm.season in rule.scope_seasons)
        and (field != "soil_fields" or rule.condition.get("field") == subfield)
        and rule.confidence != "unreviewed"
        and bool(rule.evidence_ids)
        and set(rule.evidence_ids).issubset(known_source_ids)
    ]
    return {
        "reviewed_rule_ids": [rule.rule_id for rule in rules],
        "decision_effect": "may_affect_evaluation" if rules else "recorded_only_no_matching_reviewed_rule",
    }


def run_scenario(
    farm: Any,
    candidates: list[RotationCandidate],
    scenario_inputs: dict[str, Any],
    catalogue: EvidenceCatalogue,
    priorities: list[str] | None = None,
    priority_weights: dict[str, float] | None = None,
):
    baseline = compare_rotations(farm, candidates, catalogue, priorities, priority_weights)

    farm_values = {
        "farm_id": farm.farm_id,
        "region": farm.region,
        "season": farm.season,
        "irrigation": farm.irrigation,
        "soil_fields": deepcopy(farm.soil_fields or {}),
        "crop_history": list(farm.crop_history or []),
        "priorities": list(farm.priorities or []),
    }
    changed_inputs: dict[str, Any] = {}
    if "irrigation" in scenario_inputs and scenario_inputs["irrigation"] is not None:
        changed_inputs["irrigation"] = {
            "baseline": farm.irrigation,
            "scenario": scenario_inputs["irrigation"],
            "type": "hypothetical farmer assumption",
            **_scenario_rule_metadata("irrigation", farm, catalogue),
        }
        farm_values["irrigation"] = scenario_inputs["irrigation"]
    if "soil_fields" in scenario_inputs and scenario_inputs["soil_fields"] is not None:
        for key, value in scenario_inputs["soil_fields"].items():
            changed_inputs[f"soil_fields.{key}"] = {
                "baseline": (farm.soil_fields or {}).get(key),
                "scenario": value,
                "type": "hypothetical farmer assumption",
                **_scenario_rule_metadata("soil_fields", farm, catalogue, key),
            }
            farm_values["soil_fields"][key] = value
    scenario_context = {}
    for field in SCENARIO_RULE_TYPES:
        value = scenario_inputs.get(field)
        if field in {"irrigation", "soil_fields"} or value is None:
            continue
        scenario_context[field] = value
        assumption_type = (
            "hypothetical stress-test assumption; not a forecast"
            if field in {"rainfall_change_pct", "sowing_delay_days", "water_availability_change_pct"}
            else "hypothetical cost/market shock; not a financial forecast"
        )
        changed_inputs[field] = {
            "baseline": 0,
            "scenario": value,
            "type": assumption_type,
            **_scenario_rule_metadata(field, farm, catalogue),
        }

    scenario_farm = SimpleNamespace(**farm_values)
    scenario_result = compare_rotations(
        scenario_farm,
        candidates,
        catalogue,
        priorities,
        priority_weights,
        scenario=scenario_context,
    )
    return baseline, scenario_result, changed_inputs, datetime.now(timezone.utc).isoformat()
