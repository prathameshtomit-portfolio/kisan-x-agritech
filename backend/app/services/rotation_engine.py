from datetime import datetime, timezone
from typing import Any

from app.schemas.rotation import (
    PreferenceFit,
    RotationCandidate,
    RotationCompareResponse,
    RotationOptionResult,
)
from app.services.catalog_service import EvidenceCatalogue, RotationRule

SOFTWARE_VERSION = "0.1.0"


def _scope_applies(rule: RotationRule, farm: Any) -> bool:
    if rule.scope_regions and (not getattr(farm, "region", None) or farm.region not in rule.scope_regions):
        return False
    if rule.scope_seasons and (not getattr(farm, "season", None) or farm.season not in rule.scope_seasons):
        return False
    return True


def _condition_matches(condition: dict[str, Any], farm: Any, sequence: list[str], scenario: dict[str, Any] | None):
    """Return (matched, known). Unknown input is distinct from a false condition."""
    kind = condition.get("type")
    if kind in {"contains_crop", "required_crop"}:
        crop_id = condition.get("crop_id")
        return (crop_id in sequence, bool(crop_id))
    if kind in {"forbidden_crop"}:
        crop_id = condition.get("crop_id")
        return (crop_id in sequence, bool(crop_id))
    if kind == "forbidden_adjacent_pair":
        first, second = condition.get("first_crop_id"), condition.get("second_crop_id")
        if not first or not second:
            return False, False
        return (any(a == first and b == second for a, b in zip(sequence, sequence[1:])), True)
    if kind == "soil_field_operator":
        field = condition.get("field")
        expected = condition.get("value")
        actual = (getattr(farm, "soil_fields", None) or {}).get(field)
        if actual is None or expected is None:
            return False, False
        try:
            a, b = float(actual), float(expected)
        except (TypeError, ValueError):
            a, b = str(actual), str(expected)
        op = condition.get("operator", "eq")
        operators = {
            "eq": lambda: a == b,
            "neq": lambda: a != b,
            "lt": lambda: a < b,
            "lte": lambda: a <= b,
            "gt": lambda: a > b,
            "gte": lambda: a >= b,
        }
        if op not in operators:
            return False, False
        try:
            return bool(operators[op]()), True
        except TypeError:
            return False, False
    if kind == "irrigation_in":
        allowed = condition.get("values") or []
        actual = getattr(farm, "irrigation", None)
        return (actual in allowed, actual is not None and bool(allowed))
    if kind == "rainfall_change_pct_operator":
        scenario = scenario or {}
        actual = scenario.get("rainfall_change_pct")
        expected = condition.get("value")
        if actual is None or expected is None:
            return False, False
        op = condition.get("operator", "lt")
        operators = {
            "eq": lambda: actual == expected,
            "neq": lambda: actual != expected,
            "lt": lambda: actual < expected,
            "lte": lambda: actual <= expected,
            "gt": lambda: actual > expected,
            "gte": lambda: actual >= expected,
        }
        if op not in operators:
            return False, False
        return bool(operators[op]()), True
    scenario_fields = {
        "sowing_delay_days_operator": "sowing_delay_days",
        "water_availability_change_pct_operator": "water_availability_change_pct",
        "input_cost_change_pct_operator": "input_cost_change_pct",
        "sale_price_change_pct_operator": "sale_price_change_pct",
    }
    if kind in scenario_fields:
        scenario = scenario or {}
        actual = scenario.get(scenario_fields[kind])
        expected = condition.get("value")
        if actual is None or expected is None:
            return False, False
        op = condition.get("operator", "lt")
        operators = {
            "eq": lambda: actual == expected,
            "neq": lambda: actual != expected,
            "lt": lambda: actual < expected,
            "lte": lambda: actual <= expected,
            "gt": lambda: actual > expected,
            "gte": lambda: actual >= expected,
        }
        if op not in operators:
            return False, False
        return bool(operators[op]()), True
    return False, False


def _evaluate_option(farm: Any, candidate: RotationCandidate, catalogue: EvidenceCatalogue,
                     scenario: dict[str, Any] | None, priorities: list[str]) -> RotationOptionResult:
    crop_map = {item.crop_id: item for item in catalogue.crop_catalogue.crops}
    known_source_ids = {item.source_id for item in catalogue.crop_catalogue.sources + catalogue.rule_catalogue.sources}
    warnings: list[str] = []
    rules_triggered: list[str] = []
    evidence_ids: set[str] = set()
    preference_fit: list[PreferenceFit] = []
    hard_failures: list[str] = []
    unresolved = False

    if not catalogue.crop_catalogue.crops:
        warnings.append("The crop-profile catalogue is empty; Member 2's reviewed crop profiles are required.")
        unresolved = True

    for crop_id in candidate.sequence:
        profile = crop_map.get(crop_id)
        if profile is None:
            warnings.append(f"No sourced crop profile is loaded for '{crop_id}'.")
            unresolved = True
            continue
        evidence_ids.update(profile.source_ids)
        if not profile.regions:
            warnings.append(f"Region scope is not defined for crop '{crop_id}'.")
            unresolved = True
        elif farm.region and farm.region not in profile.regions:
            hard_failures.append(f"Crop '{profile.crop_name}' is not documented for region '{farm.region}'.")
        if not profile.seasons:
            warnings.append(f"Season scope is not defined for crop '{crop_id}'.")
            unresolved = True
        elif farm.season and farm.season not in profile.seasons:
            hard_failures.append(f"Crop '{profile.crop_name}' is not documented for season '{farm.season}'.")
        for required_field in profile.required_soil_fields:
            if (getattr(farm, "soil_fields", None) or {}).get(required_field) is None:
                warnings.append(f"Required local soil input '{required_field}' is unknown.")
                unresolved = True
        if not profile.source_ids:
            warnings.append(f"Crop '{profile.crop_name}' has no linked evidence IDs.")
            unresolved = True
        elif any(source_id not in known_source_ids for source_id in profile.source_ids):
            warnings.append(f"One or more evidence IDs for crop '{profile.crop_name}' are absent from the source register.")
            unresolved = True
        if profile.confidence == "unreviewed":
            warnings.append(f"Crop '{profile.crop_name}' is marked unreviewed.")
            unresolved = True

    applicable_rules = [rule for rule in catalogue.rule_catalogue.rules if _scope_applies(rule, farm)]
    if catalogue.rule_catalogue.rules and not applicable_rules:
        warnings.append("No rotation rules are scoped to this farm's region and season.")
        unresolved = True
    elif len(applicable_rules) < len(catalogue.rule_catalogue.rules):
        warnings.append("Some rotation rules were not applied because their region/season scope does not match this farm.")
        unresolved = True
    if not catalogue.rule_catalogue.rules:
        warnings.append("No rotation rules are loaded; Member 2's evidence-backed rulebook is required.")
        unresolved = True

    for rule in applicable_rules:
        matched, known = _condition_matches(rule.condition, farm, candidate.sequence, scenario)
        if not known:
            if rule.kind == "hard_constraint":
                warnings.append(f"Rule {rule.rule_id} could not be evaluated because an input is unknown or unsupported.")
                unresolved = True
            continue
        rules_triggered.append(rule.rule_id)
        evidence_ids.update(rule.evidence_ids)
        if not rule.evidence_ids:
            warnings.append(f"Rule {rule.rule_id} has no linked source evidence.")
            unresolved = True
        elif any(source_id not in known_source_ids for source_id in rule.evidence_ids):
            warnings.append(f"One or more evidence IDs for rule {rule.rule_id} are absent from the source register.")
            unresolved = True
        if rule.confidence == "unreviewed":
            warnings.append(f"Rule {rule.rule_id} is marked unreviewed.")
            unresolved = True
        if rule.kind == "hard_constraint":
            default_effect = "exclude_if_not_match" if rule.condition.get("type") == "required_crop" else "exclude_if_match"
            effect = rule.effect or default_effect
            failed = matched if effect == "exclude_if_match" else not matched
            if failed:
                hard_failures.append(f"{rule.title} (rule {rule.rule_id}).")
        elif rule.kind == "preference":
            if rule.factor:
                if matched:
                    impact = "supports"
                elif rule.score_when_not_match is not None:
                    impact = "trade_off"
                else:
                    impact = "unknown"
                preference_fit.append(
                    PreferenceFit(
                        factor=rule.factor,
                        impact=impact,
                        explanation=rule.description,
                        rule_id=rule.rule_id,
                        evidence_ids=rule.evidence_ids,
                    )
                )

    if hard_failures:
        eligibility = "ineligible"
        warnings.extend(hard_failures)
    elif unresolved:
        eligibility = "uncertain"
    else:
        eligibility = "eligible"

    confidence_parts = []
    if eligibility == "eligible":
        confidence_parts.append("The loaded crop profiles and applicable rules support an eligibility check.")
    elif eligibility == "ineligible":
        confidence_parts.append("One or more documented hard constraints were triggered.")
    else:
        confidence_parts.append("Evidence or required inputs are incomplete; no confident suitability claim is made.")

    return RotationOptionResult(
        rotation_id=candidate.rotation_id,
        label=candidate.label,
        sequence=candidate.sequence,
        eligibility=eligibility,
        rank=None,
        score=None,
        priority_fit=preference_fit,
        warnings=warnings,
        rules_triggered=sorted(set(rules_triggered)),
        evidence_ids=sorted(evidence_ids),
        assumptions=candidate.assumptions,
        confidence_note=" ".join(confidence_parts),
    )


def compare_rotations(
    farm: Any,
    candidates: list[RotationCandidate],
    catalogue: EvidenceCatalogue,
    priorities: list[str] | None = None,
    priority_weights: dict[str, float] | None = None,
    scenario: dict[str, Any] | None = None,
) -> RotationCompareResponse:
    selected_priorities = priorities if priorities is not None else (getattr(farm, "priorities", None) or [])
    options = [
        _evaluate_option(farm, item, catalogue, scenario, selected_priorities)
        for item in candidates
    ]

    limitations = [
        "This is decision support, not a substitute for a local agronomist, soil laboratory, or extension officer.",
        "Satellite/environmental observations do not directly measure soil fertility or every parcel condition.",
        "No numeric ranking is produced unless a reviewed scoring rubric and explicit factor weights are supplied.",
        "Candidate sequences are compared as provided; the API does not invent missing crop rotations.",
    ]
    if len(candidates) < 3:
        limitations.append("Fewer than three candidate rotations were supplied; the demo target is three where evidence supports them.")

    missing_inputs = []
    for field in ("region", "season", "irrigation"):
        if getattr(farm, field, None) in (None, ""):
            missing_inputs.append(field)
    if not getattr(farm, "soil_fields", None):
        missing_inputs.append("soil_fields")
    if not getattr(farm, "crop_history", None):
        missing_inputs.append("crop_history")

    if all(item.eligibility == "eligible" for item in options):
        evidence_status = "sufficient"
    elif any(item.evidence_ids or item.rules_triggered for item in options):
        evidence_status = "partial"
    else:
        evidence_status = "insufficient"

    # Numeric ranking is deliberately opt-in. It requires weights from both a reviewed rulebook
    # (scoring_enabled) and this comparison request. The current Member 2 handoff files are blank.
    ranking_method = None
    if catalogue.rule_catalogue.scoring_enabled and priority_weights:
        requested = {key: value for key, value in priority_weights.items() if value > 0}
        factor_scores: dict[str, dict[str, float]] = {}
        for option in options:
            by_factor: dict[str, list[tuple[float, float]]] = {}
            for fit in option.priority_fit:
                matching_rules = [r for r in catalogue.rule_catalogue.rules if r.rule_id == fit.rule_id]
                if not matching_rules:
                    continue
                rule = matching_rules[0]
                if rule.score_when_match is None or rule.score_when_not_match is None or not rule.factor or not rule.weight:
                    continue
                score = rule.score_when_match if fit.impact == "supports" else rule.score_when_not_match
                by_factor.setdefault(rule.factor, []).append((score, rule.weight))
            factor_scores[option.rotation_id] = {
                factor: sum(score * weight for score, weight in vals) / sum(weight for _, weight in vals)
                for factor, vals in by_factor.items()
            }
        can_rank = bool(requested) and all(
            all(factor in factor_scores.get(option.rotation_id, {}) for factor in requested)
            for option in options if option.eligibility == "eligible"
        )
        eligible_options = [item for item in options if item.eligibility == "eligible"]
        if can_rank and eligible_options:
            total_weight = sum(requested.values())
            scores = {
                option.rotation_id: sum(
                    factor_scores[option.rotation_id][factor] * weight for factor, weight in requested.items()
                ) / total_weight
                for option in eligible_options
            }
            ranked = sorted(scores, key=scores.get, reverse=True)
            for item in options:
                if item.rotation_id in scores:
                    item.score = round(scores[item.rotation_id], 4)
                    item.rank = ranked.index(item.rotation_id) + 1
            ranking_method = "Weighted preference fit using rulebook scores and request-supplied factor weights."

    if ranking_method is None:
        limitations.append("Options are shown side-by-side; a numeric rank was not justified by the configured evidence/weights.")

    return RotationCompareResponse(
        farm_id=farm.farm_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        evidence_status=evidence_status,
        ranking_method=ranking_method,
        rotations=options,
        missing_inputs=missing_inputs,
        limitations=limitations,
        rulebook_version=catalogue.version,
        software_version=SOFTWARE_VERSION,
    )
