import math
import calendar
from collections import defaultdict
from datetime import date, timedelta
from statistics import NormalDist, mean, median, stdev

from app.schemas.climate import (
    AnnualClimateSummary,
    ClimateAudit,
    ClimateDay,
    ClimateSummary,
    DryGapSummary,
    MonthlyClimateSummary,
    TrendScreen,
    ClimateSource,
)
from app.services.reference_power import ReferencePowerDataset

MONSOON_MONTHS = {6, 7, 8, 9}
DEFAULT_DRY_GAP_THRESHOLDS = (0.1, 1.0, 2.5)


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None and math.isfinite(value) else None


def _longest_run(days: list[ClimateDay], threshold: float) -> tuple[int, date | None, date | None]:
    longest = current = 0
    longest_start = current_start = None
    longest_end = None
    previous_date = None
    for day in days:
        rain = day.values.get("PRECTOTCORR")
        if rain is not None and rain < threshold and (previous_date is None or day.observed_at == previous_date + timedelta(days=1)):
            if current == 0:
                current_start = day.observed_at
            current += 1
            if current > longest:
                longest = current
                longest_start = current_start
                longest_end = day.observed_at
        else:
            current = 0
            current_start = None
        previous_date = day.observed_at
    return longest, longest_start, longest_end


def _dry_gap_screens(by_year: dict[int, list[ClimateDay]], thresholds: tuple[float, ...]) -> list[DryGapSummary]:
    complete_seasons: dict[int, list[ClimateDay]] = {}
    for year, days in by_year.items():
        season = [day for day in days if day.observed_at.month in MONSOON_MONTHS]
        if len(season) == 122:
            complete_seasons[year] = season
    results = []
    for threshold in thresholds:
        low_counts: list[int] = []
        run_lengths: list[int] = []
        best = (0, None, None, None)
        for year, season in sorted(complete_seasons.items()):
            low_counts.append(sum(1 for day in season if day.values["PRECTOTCORR"] is not None and day.values["PRECTOTCORR"] < threshold))
            run, run_start, run_end = _longest_run(season, threshold)
            run_lengths.append(run)
            if run > best[0]:
                best = (run, run_start, run_end, year)
        results.append(
            DryGapSummary(
                low_rain_threshold_mm_day=threshold,
                seasons_analyzed=len(complete_seasons),
                mean_low_rain_days_per_june_september=_round(mean(low_counts)) if low_counts else None,
                mean_longest_run_days_per_season=_round(mean(run_lengths)) if run_lengths else None,
                longest_run_days=best[0] or None,
                longest_run_start=best[1],
                longest_run_end=best[2],
                longest_run_year=best[3],
                interpretation="Historical gridded low-rain screen only; not a meteorological drought or crop-stress diagnosis.",
            )
        )
    return results


def _trend_screen(series_name: str, unit: str, observations: list[tuple[int, float]],
                  *, lag_one: float | None = None) -> TrendScreen:
    if len(observations) < 3:
        return TrendScreen(
            series=series_name,
            unit=unit,
            annual_values=len(observations),
            theil_sen_slope_per_decade=None,
            nominal_95_percent_slope_interval_per_decade=None,
            kendall_tau=None,
            kendall_p_unadjusted=None,
            lag_1_autocorrelation=_round(lag_one, 3),
            interpretation="Too few annual values for an exploratory trend screen.",
        )
    observations = sorted(observations)
    years = [item[0] for item in observations]
    values = [item[1] for item in observations]
    slopes = [(values[j] - values[i]) / (years[j] - years[i]) * 10 for i in range(len(values) - 1) for j in range(i + 1, len(values))]
    sen_slope = median(slopes)
    n = len(values)
    concordance = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            delta = values[j] - values[i]
            concordance += (delta > 0) - (delta < 0)
    tie_counts = defaultdict(int)
    for value in values:
        tie_counts[value] += 1
    tie_term = sum(count * (count - 1) * (2 * count + 5) for count in tie_counts.values())
    variance_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18
    tau = concordance / (n * (n - 1) / 2)
    if variance_s > 0:
        z = (abs(concordance) - 1) / math.sqrt(variance_s)
        p_value = math.erfc(max(0.0, z) / math.sqrt(2))
    else:
        p_value = 1.0
    normal_975 = NormalDist().inv_cdf(0.975)
    ci_span = normal_975 * math.sqrt(variance_s)
    low_index = max(0, min(len(slopes) - 1, math.floor((len(slopes) - ci_span) / 2)))
    high_index = max(0, min(len(slopes) - 1, math.ceil((len(slopes) + ci_span) / 2) - 1))
    ordered_slopes = sorted(slopes)
    return TrendScreen(
        series=series_name,
        unit=unit,
        annual_values=n,
        theil_sen_slope_per_decade=_round(sen_slope, 3),
        nominal_95_percent_slope_interval_per_decade=[_round(ordered_slopes[low_index], 3), _round(ordered_slopes[high_index], 3)],
        kendall_tau=_round(tau, 3),
        kendall_p_unadjusted=_round(p_value, 4),
        lag_1_autocorrelation=_round(lag_one, 3),
        interpretation="Exploratory 2001-2025 style screen; p-value and nominal interval are unadjusted for serial dependence, multiple testing, breakpoints, or climate attribution.",
    )


def _lag_one_autocorrelation(values: list[float]) -> float | None:
    if len(values) < 3:
        return None
    center = mean(values)
    denominator = sum((value - center) ** 2 for value in values)
    if denominator == 0:
        return None
    return sum((values[index] - center) * (values[index - 1] - center) for index in range(1, len(values))) / denominator


def summarize_reference(dataset: ReferencePowerDataset, start_date: date | None = None,
                        end_date: date | None = None,
                        dry_gap_thresholds: tuple[float, ...] = DEFAULT_DRY_GAP_THRESHOLDS) -> ClimateSummary:
    start = start_date or dataset.source.period_start
    end = end_date or dataset.source.period_end
    if end < start:
        raise ValueError("end_date must be on or after start_date")
    if start < dataset.source.period_start or end > dataset.source.period_end:
        raise ValueError("Requested dates fall outside the reference dataset period.")
    if any(threshold < 0 or not math.isfinite(threshold) for threshold in dry_gap_thresholds):
        raise ValueError("Dry-gap thresholds must be finite, non-negative millimetres per day.")
    selected = [day for day in dataset.days if start <= day.observed_at <= end]
    by_year: dict[int, list[ClimateDay]] = defaultdict(list)
    for day in selected:
        by_year[day.observed_at.year].append(day)

    annual_rows = []
    annual_rain: list[tuple[int, float]] = []
    annual_temp: list[tuple[int, float]] = []
    monsoon_rain: list[tuple[int, float]] = []
    monsoon_totals: list[float] = []
    for year, days in sorted(by_year.items()):
        rains = [day.values["PRECTOTCORR"] for day in days if day.values["PRECTOTCORR"] is not None]
        temps = [day.values["T2M"] for day in days if day.values["T2M"] is not None]
        expected_days = sum(1 for offset in range((end - start).days + 1) if (start + timedelta(days=offset)).year == year)
        annual_rows.append(AnnualClimateSummary(
            year=year,
            precipitation_total_mm=None,
            mean_temperature_c=None,
            valid_rainfall_days=len(rains),
            expected_days=expected_days,
            coverage_fraction=_round(len(rains) / expected_days, 4) if expected_days else 0.0,
        ))
        full_year = expected_days == (366 if calendar.isleap(year) else 365)
        annual_sum = sum(rains) if full_year and len(rains) == expected_days else None
        annual_mean_temp = mean(temps) if full_year and len(temps) == expected_days else None
        if annual_sum is not None:
            annual_rain.append((year, annual_sum))
        if annual_mean_temp is not None:
            annual_temp.append((year, annual_mean_temp))
        if annual_sum is not None or annual_mean_temp is not None:
            annual_rows[-1] = AnnualClimateSummary(
                year=year,
                precipitation_total_mm=_round(annual_sum),
                mean_temperature_c=_round(annual_mean_temp),
                valid_rainfall_days=len(rains),
                expected_days=expected_days,
                coverage_fraction=_round(len(rains) / expected_days, 4) if expected_days else 0.0,
            )
        monsoon_days = [day for day in days if day.observed_at.month in MONSOON_MONTHS]
        monsoon_expected = sum(1 for offset in range((end - start).days + 1) if (start + timedelta(days=offset)).year == year and (start + timedelta(days=offset)).month in MONSOON_MONTHS)
        monsoon_values = [day.values["PRECTOTCORR"] for day in monsoon_days if day.values["PRECTOTCORR"] is not None]
        if monsoon_expected and len(monsoon_values) == monsoon_expected:
            monsoon_total = sum(monsoon_values)
            monsoon_rain.append((year, monsoon_total))
            monsoon_totals.append(monsoon_total)

    monthly_rows = []
    for month in range(1, 13):
        monthly_rain_totals, month_temps, month_rh, month_solar = [], [], [], []
        for days in by_year.values():
            month_days = [day for day in days if day.observed_at.month == month]
            if not month_days:
                continue
            rain_values = [day.values["PRECTOTCORR"] for day in month_days if day.values["PRECTOTCORR"] is not None]
            expected_month_days = calendar.monthrange(year, month)[1]
            if len(month_days) == expected_month_days and len(rain_values) == expected_month_days:
                monthly_rain_totals.append(sum(rain_values))
            if len(month_days) != expected_month_days:
                continue
            for field, target in (("T2M", month_temps), ("RH2M", month_rh), ("ALLSKY_SFC_SW_DWN", month_solar)):
                values = [day.values[field] for day in month_days if day.values[field] is not None]
                if values:
                    target.append(mean(values))
        monthly_rows.append(MonthlyClimateSummary(
            month=month,
            mean_monthly_precipitation_mm=_round(mean(monthly_rain_totals)) if monthly_rain_totals else None,
            mean_temperature_c=_round(mean(month_temps)) if month_temps else None,
            mean_relative_humidity_pct=_round(mean(month_rh)) if month_rh else None,
            mean_shortwave_mj_m2_day=_round(mean(month_solar)) if month_solar else None,
            valid_years=len(monthly_rain_totals),
        ))

    average_annual_rain = mean([value for _, value in annual_rain]) if annual_rain else None
    average_monsoon_rain = mean(monsoon_totals) if monsoon_totals else None
    annual_sd = stdev([value for _, value in annual_rain]) if len(annual_rain) > 1 else None
    monsoon_sd = stdev(monsoon_totals) if len(monsoon_totals) > 1 else None
    monsoon_monthly_means = [row.mean_monthly_precipitation_mm for row in monthly_rows if row.month in MONSOON_MONTHS and row.mean_monthly_precipitation_mm is not None]
    wettest_month = max((row for row in monthly_rows if row.mean_monthly_precipitation_mm is not None), key=lambda row: row.mean_monthly_precipitation_mm, default=None)
    monsoon = {
        "complete_seasons": len(monsoon_totals),
        "mean_june_september_precipitation_mm": _round(average_monsoon_rain),
        "standard_deviation_mm_sample": _round(monsoon_sd),
        "coefficient_of_variation_pct": _round(monsoon_sd / average_monsoon_rain * 100) if monsoon_sd is not None and average_monsoon_rain else None,
        "mean_annual_precipitation_mm": _round(average_annual_rain),
        "annual_standard_deviation_mm_sample": _round(annual_sd),
        "annual_coefficient_of_variation_pct": _round(annual_sd / average_annual_rain * 100) if annual_sd is not None and average_annual_rain else None,
        "monsoon_share_of_mean_annual_pct": _round(average_monsoon_rain / average_annual_rain * 100) if average_monsoon_rain is not None and average_annual_rain else None,
        "wettest_calendar_month": wettest_month.month if wettest_month else None,
        "wettest_month_mean_total_mm": wettest_month.mean_monthly_precipitation_mm if wettest_month else None,
        "mean_monsoon_monthly_precipitation_mm": _round(mean(monsoon_monthly_means)) if monsoon_monthly_means else None,
    }
    annual_rain_values = [value for _, value in annual_rain]
    annual_monsoon_values = [value for _, value in monsoon_rain]
    annual_temp_values = [value for _, value in annual_temp]
    trends = [
        _trend_screen("annual_precipitation", "mm/year per decade", annual_rain, lag_one=_lag_one_autocorrelation(annual_rain_values)),
        _trend_screen("june_september_precipitation", "mm/season per decade", monsoon_rain, lag_one=_lag_one_autocorrelation(annual_monsoon_values)),
        _trend_screen("annual_mean_temperature", "°C per decade", annual_temp, lag_one=_lag_one_autocorrelation(annual_temp_values)),
    ]
    return ClimateSummary(
        source=dataset.source,
        analysis_period_start=start,
        analysis_period_end=end,
        audit=dataset.audit,
        annual=annual_rows,
        monthly_climatology=monthly_rows,
        monsoon=monsoon,
        dry_gap_screens=_dry_gap_screens(by_year, tuple(dry_gap_thresholds)),
        trend_screens=trends,
        validation_status={
            "structural_audit": dataset.audit.status.upper(),
            "power_vs_local_station": "PENDING_STATION_DATA",
            "power_vs_gpm_imerg": "PENDING_IMERG_EXPORT",
            "modis_vegetation_export": "PENDING_FARM_POLYGON_AND_EXPORT",
        },
        limitations=[
            "This NASA POWER point is a Nagpur city-centre proxy, not a farm-level measurement.",
            "MERRA-2 meteorology and CERES SYN1deg solar radiation retain different native spatial footprints.",
            "Rainfall thresholds are sensitivity screens, not drought, crop-stress, or irrigation diagnoses.",
            "Trend slopes, confidence intervals, and Kendall p-values are exploratory and unadjusted for autocorrelation, multiple testing, or attribution.",
            "IMERG, MODIS, and local-station outputs remain pending until source exports or station observations are supplied.",
        ],
    )
