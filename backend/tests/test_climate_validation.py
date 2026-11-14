from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.climate import ClimateComparisonRequest
from app.services.climate_validation import compare_climate_series


def _series(source_id, source_type, unit, values):
    return {
        "source_id": source_id,
        "source_label": source_id,
        "source_type": source_type,
        "unit": unit,
        "time_standard": "UTC",
        "values": values,
    }


def _points(values):
    start = date(2025, 6, 1)
    return [
        {"observed_at": (start + timedelta(days=index)).isoformat(), "value": value}
        for index, value in enumerate(values)
    ]


def test_comparison_pairs_valid_dates_and_never_converts_missing_to_zero():
    payload = {
        "estimated": _series("POWER", "gridded_estimate", "mm/day", _points([1, 0, 2, 3])),
        "comparison": _series("station", "station_observation", "mm/day", _points([0, 1, None, 4])),
        "wet_day_threshold_mm_day": 1,
    }
    result = compare_climate_series(ClimateComparisonRequest.model_validate(payload))

    assert result.comparison_type == "station_comparison_candidate"
    assert result.expected_overlap_days == 4
    assert result.paired_days == 3
    assert result.coverage_fraction == 0.75
    assert result.missing_estimated_days == 0
    assert result.missing_comparison_days == 1
    assert result.metrics.mean_bias_estimated_minus_comparison == -1 / 3
    assert result.metrics.mean_absolute_error == 1
    assert result.wet_day_counts.model_dump() == {
        "threshold": 1,
        "hits": 1,
        "misses": 1,
        "false_alarms": 1,
        "correct_negatives": 0,
    }


def test_comparison_rejects_different_units_and_time_standards():
    payload = {
        "estimated": _series("POWER", "gridded_estimate", "mm/day", _points([1, 2])),
        "comparison": _series("station", "station_observation", "mm", _points([1, 2])),
    }
    with pytest.raises(ValidationError):
        ClimateComparisonRequest.model_validate(payload)
    payload["comparison"]["unit"] = "mm/day"
    payload["comparison"]["time_standard"] = "LST"
    with pytest.raises(ValidationError):
        ClimateComparisonRequest.model_validate(payload)


def test_wet_day_threshold_is_rejected_for_temperature():
    payload = {
        "estimated": _series("POWER", "gridded_estimate", "degC", _points([10, 12])),
        "comparison": _series("station", "station_observation", "degC", _points([9, 13])),
        "wet_day_threshold_mm_day": 1,
    }
    with pytest.raises(ValidationError):
        ClimateComparisonRequest.model_validate(payload)


def test_comparison_rejects_duplicate_daily_dates():
    points = _points([1, 2])
    points[1]["observed_at"] = points[0]["observed_at"]
    payload = {
        "estimated": _series("POWER", "gridded_estimate", "mm/day", points),
        "comparison": _series("IMERG", "gridded_estimate", "mm/day", _points([1, 2])),
    }
    with pytest.raises(ValidationError):
        ClimateComparisonRequest.model_validate(payload)


def test_comparison_rejects_nonoverlapping_series():
    first = _points([1, 2])
    second = _points([1, 2])
    for point in second:
        point["observed_at"] = (date.fromisoformat(point["observed_at"]) + timedelta(days=30)).isoformat()
    payload = {
        "estimated": _series("POWER", "gridded_estimate", "mm/day", first),
        "comparison": _series("IMERG", "gridded_estimate", "mm/day", second),
    }
    request = ClimateComparisonRequest.model_validate(payload)
    with pytest.raises(HTTPException) as exc_info:
        compare_climate_series(request)
    assert exc_info.value.status_code == 422
