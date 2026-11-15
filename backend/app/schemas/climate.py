from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.common import APIModel


class ClimateSource(APIModel):
    source_id: str
    label: str
    provider: str
    source_product: dict[str, str]
    latitude: float
    longitude: float
    elevation_m: float | None = None
    period_start: date
    period_end: date
    time_standard: Literal["UTC", "LST"]
    spatial_resolution: dict[str, str]
    variables: dict[str, dict[str, str]]
    retrieved_at: datetime | None = None
    raw_file_sha256: str | None = None


class ClimateAudit(APIModel):
    status: Literal["passed", "failed"]
    expected_daily_rows: int
    actual_daily_rows: int
    unique_dates: int
    duplicate_dates: list[date]
    missing_dates: list[date]
    unexpected_dates: list[date]
    null_counts: dict[str, int]
    sentinel_counts: dict[str, int]
    range_violations: dict[str, int]
    value_ranges: dict[str, dict[str, float | str | None]]
    first_date: date | None
    last_date: date | None
    checks: dict[str, bool]


class ClimateDay(APIModel):
    observed_at: date
    values: dict[str, float | None]
    quality_flags: dict[str, Literal["provider_value_returned", "missing"]]


class AnnualClimateSummary(APIModel):
    year: int
    precipitation_total_mm: float | None
    mean_temperature_c: float | None
    valid_rainfall_days: int
    expected_days: int
    coverage_fraction: float


class MonthlyClimateSummary(APIModel):
    month: int = Field(ge=1, le=12)
    mean_monthly_precipitation_mm: float | None
    mean_temperature_c: float | None
    mean_relative_humidity_pct: float | None
    mean_shortwave_mj_m2_day: float | None
    valid_years: int


class DryGapSummary(APIModel):
    low_rain_threshold_mm_day: float
    seasons_analyzed: int
    mean_low_rain_days_per_june_september: float | None
    mean_longest_run_days_per_season: float | None
    longest_run_days: int | None
    longest_run_start: date | None
    longest_run_end: date | None
    longest_run_year: int | None
    interpretation: str


class TrendScreen(APIModel):
    series: str
    unit: str
    annual_values: int
    theil_sen_slope_per_decade: float | None
    nominal_95_percent_slope_interval_per_decade: list[float] | None
    kendall_tau: float | None
    kendall_p_unadjusted: float | None
    lag_1_autocorrelation: float | None
    interpretation: str


class ClimateSummary(APIModel):
    source: ClimateSource
    analysis_period_start: date
    analysis_period_end: date
    audit: ClimateAudit
    annual: list[AnnualClimateSummary]
    monthly_climatology: list[MonthlyClimateSummary]
    monsoon: dict[str, float | int | str | None]
    dry_gap_screens: list[DryGapSummary]
    trend_screens: list[TrendScreen]
    validation_status: dict[str, str]
    limitations: list[str]


class ReferenceClimateDailyResponse(APIModel):
    source: ClimateSource
    audit: ClimateAudit
    period_start: date
    period_end: date
    observations: list[ClimateDay]
    limitations: list[str]


class ClimateSeriesPoint(APIModel):
    observed_at: date
    value: float | None
    quality_flag: str = "provider_value_returned"

    @field_validator("value")
    @classmethod
    def finite_value(cls, value: float | None) -> float | None:
        if value is not None and (value != value or value in (float("inf"), float("-inf"))):
            raise ValueError("Series values must be finite numbers or null.")
        return value


class ClimateSeriesInput(APIModel):
    source_id: str = Field(min_length=1, max_length=120)
    source_label: str = Field(min_length=1, max_length=200)
    source_type: Literal["gridded_estimate", "station_observation"]
    unit: str = Field(min_length=1, max_length=40)
    time_standard: Literal["UTC", "LST"]
    values: list[ClimateSeriesPoint] = Field(min_length=2, max_length=20000)

    @model_validator(mode="after")
    def unique_dates(self):
        dates = [point.observed_at for point in self.values]
        if len(dates) != len(set(dates)):
            raise ValueError("A series may contain only one value per date.")
        return self


class ClimateComparisonRequest(APIModel):
    estimated: ClimateSeriesInput
    comparison: ClimateSeriesInput
    wet_day_threshold_mm_day: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def compatible_series(self):
        if self.estimated.unit.casefold() != self.comparison.unit.casefold():
            raise ValueError("Both series must use the same unit before comparison.")
        if self.estimated.time_standard != self.comparison.time_standard:
            raise ValueError("Align both series to the same daily time standard before comparison.")
        if self.wet_day_threshold_mm_day is not None and self.estimated.unit.casefold() not in {"mm/day", "mm day-1"}:
            raise ValueError("A wet-day threshold can only be used with precipitation series in mm/day.")
        return self


class ClimateComparisonMetrics(APIModel):
    mean_bias_estimated_minus_comparison: float
    mean_absolute_error: float
    root_mean_square_error: float
    pearson_r: float | None
    spearman_rho: float | None


class RainOccurrenceCounts(APIModel):
    threshold: float
    hits: int
    misses: int
    false_alarms: int
    correct_negatives: int


class ClimateComparisonResponse(APIModel):
    comparison_type: Literal["cross_product_check", "station_comparison_candidate"]
    estimated_source_id: str
    estimated_source_label: str
    comparison_source_id: str
    comparison_source_label: str
    unit: str
    time_standard: Literal["UTC", "LST"]
    overlap_start: date
    overlap_end: date
    expected_overlap_days: int
    paired_days: int
    coverage_fraction: float
    missing_estimated_days: int
    missing_comparison_days: int
    metrics: ClimateComparisonMetrics
    wet_day_counts: RainOccurrenceCounts | None
    limitations: list[str]
