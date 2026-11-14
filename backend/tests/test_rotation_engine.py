from types import SimpleNamespace

from app.schemas.rotation import RotationCandidate
from app.services.catalog_service import CropCatalogue, CropProfile, EvidenceCatalogue, RotationRule, RuleCatalogue, SourceReference
from app.services.rotation_engine import compare_rotations


def make_farm():
    return SimpleNamespace(
        farm_id="test-farm",
        region="Test Region",
        season="kharif",
        irrigation="rainfed",
        soil_fields={"pH": 6.5},
        crop_history=["crop_a"],
        priorities=["water_demand"],
    )


def test_empty_catalogue_returns_uncertain_not_advice():
    catalogue = EvidenceCatalogue()
    result = compare_rotations(
        make_farm(),
        [RotationCandidate(rotation_id="r1", label="Option 1", sequence=["crop_a", "crop_b"])],
        catalogue,
    )
    assert result.evidence_status == "insufficient"
    assert result.rotations[0].eligibility == "uncertain"
    assert result.rotations[0].rank is None


def test_hard_constraint_applied_before_preferences():
    crops = CropCatalogue(
        version="test-crops-1",
        crops=[
            CropProfile(crop_id="crop_a", crop_name="Crop A", regions=["Test Region"], seasons=["kharif"], source_ids=["SRC-A"], confidence="high"),
            CropProfile(crop_id="crop_b", crop_name="Crop B", regions=["Test Region"], seasons=["kharif"], source_ids=["SRC-B"], confidence="high"),
        ],
        sources=[],
    )
    rules = RuleCatalogue(
        version="test-rules-1",
        scoring_enabled=False,
        rules=[
            RotationRule(
                rule_id="RULE-TEST-1",
                title="Synthetic forbidden pair test",
                kind="hard_constraint",
                description="Synthetic test rule only.",
                condition={"type": "forbidden_adjacent_pair", "first_crop_id": "crop_a", "second_crop_id": "crop_b"},
                effect="exclude_if_match",
                evidence_ids=["SRC-TEST"],
                confidence="high",
            )
        ],
        sources=[],
    )
    catalogue = EvidenceCatalogue(crop_catalogue=crops, rule_catalogue=rules)
    result = compare_rotations(
        make_farm(),
        [RotationCandidate(rotation_id="r1", label="Test pair", sequence=["crop_a", "crop_b"])],
        catalogue,
    )
    assert result.rotations[0].eligibility == "ineligible"
    assert "RULE-TEST-1" in result.rotations[0].rules_triggered
    assert result.rotations[0].rank is None


def test_sowing_delay_rule_is_evaluated_only_from_explicit_scenario_input():
    source = SourceReference(source_id="SRC-A", organization="Test source", title="Synthetic test evidence")
    crops = CropCatalogue(
        version="test-crops-1",
        crops=[
            CropProfile(crop_id=crop_id, crop_name=crop_id.upper(), regions=["Test Region"], seasons=["kharif"], source_ids=["SRC-A"], confidence="high")
            for crop_id in ("crop_a", "crop_b")
        ],
        sources=[source],
    )
    rules = RuleCatalogue(
        version="test-rules-1",
        scoring_enabled=False,
        rules=[
            RotationRule(
                rule_id="RULE-DELAY-1",
                title="Reviewed delayed-sowing constraint",
                kind="hard_constraint",
                description="Synthetic test rule only.",
                condition={"type": "sowing_delay_days_operator", "operator": "gt", "value": 7},
                effect="exclude_if_match",
                evidence_ids=["SRC-A"],
                confidence="high",
            )
        ],
        sources=[source],
    )
    candidate = [RotationCandidate(rotation_id="r1", label="Plan", sequence=["crop_a", "crop_b"])]
    catalogue = EvidenceCatalogue(crop_catalogue=crops, rule_catalogue=rules)

    without_scenario = compare_rotations(make_farm(), candidate, catalogue)
    with_scenario = compare_rotations(make_farm(), candidate, catalogue, scenario={"sowing_delay_days": 14})

    assert without_scenario.rotations[0].eligibility == "uncertain"
    assert with_scenario.rotations[0].eligibility == "ineligible"
    assert "RULE-DELAY-1" in with_scenario.rotations[0].rules_triggered
