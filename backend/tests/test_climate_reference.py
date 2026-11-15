from datetime import date

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.climate import nagpur_reference_daily, nagpur_reference_summary, nagpur_reference_validation
from app.services.climate_analysis import summarize_reference
from app.services.reference_power import get_reference_power


def test_supplied_power_csv_passes_structural_and_range_audits():
    dataset = get_reference_power()

    assert dataset.audit.status == "passed"
    assert dataset.audit.expected_daily_rows == 9131
    assert dataset.audit.actual_daily_rows == 9131
    assert dataset.audit.unique_dates == 9131
    assert dataset.audit.duplicate_dates == []
    assert dataset.audit.missing_dates == []
    assert dataset.audit.null_counts == {key: 0 for key in dataset.audit.null_counts}
    assert all(dataset.audit.checks.values())
    assert dataset.audit.value_ranges["T2M"]["mean"] == 26.83
    assert dataset.audit.value_ranges["PRECTOTCORR"]["minimum"] == 0
    assert dataset.audit.value_ranges["ALLSKY_SFC_SW_DWN"]["unit"] == "MJ/m²/day"


def test_reference_rainfall_and_dry_gap_screens_match_member_one_metrics():
    summary = summarize_reference(get_reference_power())

    assert summary.monsoon["mean_annual_precipitation_mm"] == 1280.61
    assert summary.monsoon["mean_june_september_precipitation_mm"] == 1133.37
    assert summary.monsoon["monsoon_share_of_mean_annual_pct"] == 88.5
    assert summary.monsoon["wettest_calendar_month"] == 7
    assert summary.monsoon["wettest_month_mean_total_mm"] == 400.65
    assert [item.mean_low_rain_days_per_june_september for item in summary.dry_gap_screens] == [16.16, 37.64, 54.84]
    assert summary.dry_gap_screens[1].longest_run_start == date(2023, 6, 1)
    assert summary.dry_gap_screens[1].longest_run_end == date(2023, 6, 21)
    assert "not a meteorological drought" in summary.dry_gap_screens[1].interpretation


def test_partial_year_is_not_reported_as_an_annual_total():
    summary = summarize_reference(get_reference_power(), date(2023, 6, 1), date(2023, 9, 30))

    assert summary.annual[0].precipitation_total_mm is None
    assert summary.trend_screens[0].annual_values == 0
    assert summary.dry_gap_screens[1].longest_run_days == 21


def test_reference_climate_routes_expose_source_quality_and_summary():
    summary = nagpur_reference_summary(None, None, None)
    daily = nagpur_reference_daily(date(2023, 6, 1), date(2023, 6, 3))
    validation = nagpur_reference_validation()

    assert summary.source.label.startswith("Nagpur city-centre proxy")
    assert summary.source.time_standard == "UTC"
    assert summary.audit.status == "passed"
    assert summary.validation_status["power_vs_local_station"] == "PENDING_STATION_DATA"
    assert len(daily.observations) == 3
    assert daily.observations[0].values["ALLSKY_SFC_SW_DWN"] is not None
    assert validation["validation_status"]["power_vs_gpm_imerg"] == "PENDING_IMERG_EXPORT"
    assert len(summary.model_dump_json()) > 1000


def test_reference_daily_route_rejects_large_windows():
    with pytest.raises(HTTPException) as exc_info:
        nagpur_reference_daily(date(2001, 1, 1), date(2002, 1, 2))
    assert exc_info.value.status_code == 422
