"""Token-free NASA Earth observation discovery + resilient Kisan X feature hub.

NASA CMR discovery is public; many underlying granule downloads require a free
Earthdata Login. This service deliberately does not attempt authenticated
downloads. NASA POWER and the Daymet single-pixel service can return numeric
observations anonymously. Other products return public catalog metadata and a
clearly marked deterministic simulation until an approved open subset/asset
workflow is configured. Simulated values are NEVER decision eligible.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import logging
import random
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
DAYMET_URL = "https://daymet.ornl.gov/single-pixel/api/data"
CMR_GRANULES_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
LANDSAT_STAC_URL = "https://landsatlook.usgs.gov/stac-server/search"
NASA_GIBS_WMS_URL = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
REQUEST_TIMEOUT_SECONDS = 9.0
MAX_CONCURRENT_REQUESTS = 6
CACHE_TTL_SECONDS = 900
_cache: dict[tuple[str, float, float], tuple[float, dict[str, Any]]] = {}
_cache_lock = asyncio.Lock()
_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)


class FeatureQuery(BaseModel):
    feature: Literal["crop_rotation", "soil_health", "weather_alerts"]
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


DATASETS: dict[str, dict[str, Any]] = {
    "nasa_power": {
        "name": "NASA POWER Daily Point", "platform": "NASA POWER / MERRA-2 / CERES",
        "access": "open_numeric_api", "feature_tags": ["crop_rotation", "soil_health", "weather_alerts"],
        "fallback": "weather",
    },
    "smap": {
        "name": "SMAP L4 Surface and Root-Zone Soil Moisture", "platform": "SMAP",
        "short_name": "SPL4SMGP", "version": "008", "access": "public_cmr_discovery",
        "feature_tags": ["crop_rotation", "soil_health", "weather_alerts"], "fallback": "soil_moisture",
    },
    "gpm_imerg": {
        "name": "GPM IMERG Daily Precipitation", "platform": "GPM",
        "short_name": "GPM_3IMERGDF", "version": "07", "access": "public_cmr_discovery",
        "feature_tags": ["crop_rotation", "soil_health", "weather_alerts"], "fallback": "rainfall",
    },
    "modis_terra": {
        "name": "MODIS Terra MOD13Q1 Vegetation Indices", "platform": "Terra / MODIS",
        "short_name": "MOD13Q1", "version": "061", "access": "public_cmr_discovery",
        "feature_tags": ["crop_rotation", "soil_health", "weather_alerts"], "fallback": "ndvi",
    },
    "modis_aqua": {
        "name": "MODIS Aqua MYD13Q1 Vegetation Indices", "platform": "Aqua / MODIS",
        "short_name": "MYD13Q1", "version": "061", "access": "public_cmr_discovery",
        "feature_tags": ["crop_rotation", "soil_health", "weather_alerts"], "fallback": "ndvi",
    },
    "landsat_8": {
        "name": "Landsat 8 Collection 2 Level-2 Surface Reflectance", "platform": "Landsat 8 / OLI-TIRS",
        "access": "public_usgs_stac_metadata", "collection": "landsat-c2l2-sr",
        "feature_tags": ["crop_rotation", "soil_health"], "fallback": "landsat",
    },
    "landsat_9": {
        "name": "Landsat 9 Collection 2 Level-2 Surface Reflectance", "platform": "Landsat 9 / OLI-2-TIRS-2",
        "access": "public_usgs_stac_metadata", "collection": "landsat-c2l2-sr",
        "feature_tags": ["crop_rotation", "soil_health"], "fallback": "landsat",
    },
    "ecostress": {
        "name": "ECOSTRESS L2 Land Surface Temperature and Emissivity", "platform": "ISS / ECOSTRESS",
        "short_name": "ECO_L2T_LSTE", "version": "002", "access": "public_cmr_discovery",
        "feature_tags": ["crop_rotation", "soil_health", "weather_alerts"], "fallback": "thermal",
    },
    "grace": {
        "name": "GRACE / GRACE-FO JPL Mascon Terrestrial Water Storage", "platform": "GRACE / GRACE-FO",
        "short_name": "TELLUS_GRAC-GRFO_MASCON_CRI_GRID_RL06.3_V4", "version": "4",
        "access": "public_cmr_discovery", "feature_tags": ["crop_rotation", "soil_health", "weather_alerts"],
        "fallback": "water_storage",
    },
    "viirs_fire": {
        "name": "VIIRS 375 m Active Fire NRT", "platform": "Suomi-NPP / VIIRS",
        "short_name": "VNP14IMGTDL_NRT", "access": "public_cmr_discovery",
        "feature_tags": ["crop_rotation", "soil_health", "weather_alerts"], "fallback": "fire",
    },
    "nasadem_srtm": {
        "name": "NASADEM / SRTM Elevation", "platform": "SRTM / NASADEM",
        "short_name": "NASADEM_HGT", "version": "001", "access": "public_cmr_discovery",
        "feature_tags": ["crop_rotation", "soil_health", "weather_alerts"], "fallback": "terrain",
    },
    "daymet": {
        "name": "Daymet V4 Daily Surface Weather", "platform": "Daymet / ORNL DAAC",
        "access": "open_numeric_api_north_america", "feature_tags": ["crop_rotation", "soil_health", "weather_alerts"],
        "fallback": "weather",
    },
    "tempo": {
        "name": "TEMPO Level-3 Nitrogen Dioxide", "platform": "TEMPO",
        "short_name": "TEMPO_NO2_L3", "access": "public_cmr_discovery",
        "feature_tags": ["crop_rotation", "soil_health", "weather_alerts"], "fallback": "air_quality",
    },
}

FEATURE_DATASETS = {
    "crop_rotation": ["nasa_power", "smap", "gpm_imerg", "modis_terra", "modis_aqua", "landsat_8", "landsat_9", "ecostress", "grace", "daymet"],
    "soil_health": ["smap", "modis_terra", "modis_aqua", "landsat_8", "landsat_9", "ecostress", "grace", "nasadem_srtm", "daymet"],
    "weather_alerts": ["nasa_power", "smap", "gpm_imerg", "ecostress", "grace", "viirs_fire", "daymet", "tempo"],
}

FEATURE_MAP: dict[str, dict[str, list[str]]] = {
    "crop_rotation": {
        "seasonal_weather_context": ["nasa_power", "daymet"],
        "root_zone_wetness_context": ["smap"],
        "precipitation_context": ["gpm_imerg"],
        "canopy_vigor_context": ["modis_terra", "modis_aqua", "landsat_8", "landsat_9"],
        "thermal_stress_context": ["ecostress"],
        "regional_water_storage_context": ["grace"],
    },
    "soil_health": {
        "surface_rootzone_moisture_context": ["smap"],
        "vegetation_cover_context": ["modis_terra", "modis_aqua", "landsat_8", "landsat_9"],
        "surface_temperature_context": ["ecostress"],
        "regional_water_storage_context": ["grace"],
        "terrain_runoff_context": ["nasadem_srtm"],
        "weather_forcing_context": ["daymet"],
    },
    "weather_alerts": {
        "heat_wind_rain_observations": ["nasa_power", "daymet"],
        "precipitation_monitoring": ["gpm_imerg"],
        "rootzone_wetness_monitoring": ["smap"],
        "surface_heat_monitoring": ["ecostress"],
        "active_fire_monitoring": ["viirs_fire"],
        "air_quality_context": ["tempo"],
        "regional_water_storage_context": ["grace"],
    },
}

LIMITATIONS = [
    "Only NASA POWER and in-coverage Daymet responses provide live numeric weather values in this token-free implementation.",
    "CMR/STAC results are discovery metadata, not extracted pixel measurements. A free Earthdata Login is normally needed to download many granules.",
    "All mock/fallback metrics are deterministic synthetic examples, not observations; they must never trigger decisions or farmer alerts.",
    "NASA POWER and gridded satellites are environmental context, not farm sensors or soil tests.",
    "Daymet coverage is North America only; India and other out-of-domain points return labeled fallback data.",
    "GRACE is a coarse regional/monthly water-storage signal and cannot measure a farm well or aquifer.",
    "GPM and MODIS revisit/latency, Landsat clouds/revisit, and ECOSTRESS overpass timing can leave no recent usable observation.",
    "TEMPO covers North America; outside-coverage points return catalog status and synthetic fallback only.",
]


class Coordinate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class SyncAllResponse(BaseModel):
    generated_at: datetime
    latitude: float
    longitude: float
    datasets_requested: int
    datasets_live_numeric: int
    datasets_catalog_only: int
    datasets_simulated: int
    feature_mappings: dict[str, dict[str, list[str]]]
    datasets: list[dict[str, Any]]
    limitations: list[str]


router = APIRouter(prefix="/api/satellites", tags=["NASA satellite hub"])


def _mock_metrics(dataset_id: str, latitude: float, longitude: float) -> dict[str, Any]:
    """Return stable demo-shaped metrics; caller must preserve simulation labels."""
    seed_text = f"{dataset_id}|{latitude:.4f}|{longitude:.4f}|{date.today().isoformat()}"
    seed = int(hashlib.sha256(seed_text.encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    kind = DATASETS[dataset_id]["fallback"]
    if kind == "weather":
        return {"temperature_c": round(rng.uniform(18, 36), 2), "rainfall_mm_day": round(rng.uniform(0, 24), 2),
                "relative_humidity_pct": round(rng.uniform(25, 90), 1), "wind_speed_m_s": round(rng.uniform(0, 12), 2),
                "shortwave_mj_m2_day": round(rng.uniform(8, 28), 2)}
    if kind == "soil_moisture":
        return {"surface_soil_moisture_m3_m3": round(rng.uniform(0.04, 0.42), 3),
                "rootzone_soil_moisture_m3_m3": round(rng.uniform(0.06, 0.40), 3),
                "wetness_index_0_1": round(rng.uniform(0, 1), 3)}
    if kind == "rainfall":
        return {"precipitation_mm_day": round(rng.uniform(0, 35), 2), "precipitation_anomaly_pct": round(rng.uniform(-80, 160), 1)}
    if kind in {"ndvi", "landsat"}:
        return {"ndvi": round(rng.uniform(0.05, 0.86), 3), "canopy_health_index_0_1": round(rng.uniform(0, 1), 3)}
    if kind == "thermal":
        return {"land_surface_temperature_c": round(rng.uniform(18, 52), 2), "evaporative_stress_index_0_1": round(rng.uniform(0, 1), 3)}
    if kind == "water_storage":
        return {"terrestrial_water_storage_anomaly_cm": round(rng.uniform(-25, 25), 2)}
    if kind == "fire":
        return {"active_fire_detections": rng.choice([0, 0, 0, 1, 2]), "fire_radiative_power_mw": round(rng.uniform(0, 12), 2)}
    if kind == "terrain":
        return {"elevation_m": round(rng.uniform(0, 2600), 1), "slope_deg": round(rng.uniform(0, 35), 2),
                "runoff_risk_index_0_1": round(rng.uniform(0, 1), 3)}
    return {"tropospheric_no2_mol_m2": round(rng.uniform(0, 0.0002), 8), "ozone_stress_context": "synthetic_only"}


def _simulated_result(dataset_id: str, latitude: float, longitude: float, reason: str) -> dict[str, Any]:
    spec = DATASETS[dataset_id]
    return {
        "dataset_id": dataset_id,
        "dataset_name": spec["name"],
        "platform": spec["platform"],
        "source_status": "simulated_fallback",
        "observation_time": None,
        "spatial_resolution": None,
        "metrics": _mock_metrics(dataset_id, latitude, longitude),
        "quality": {"flag": "SIMULATED_NOT_OBSERVED", "reason": reason},
        "simulation": True,
        "decision_eligible": False,
        "catalog": None,
        "source_url": None,
        "limitations": ["Synthetic fallback only. Do not present as measured data or use to generate a recommendation."],
    }


def _empty_result(dataset_id: str, latitude: float, longitude: float, reason: str) -> dict[str, Any]:
    # Kept separate to make invalid provider responses as safe as offline fallback.
    return _simulated_result(dataset_id, latitude, longitude, reason)


def _cache_key(dataset_id: str, latitude: float, longitude: float) -> tuple[str, float, float]:
    return dataset_id, round(latitude, 3), round(longitude, 3)


async def _cache_get(key: tuple[str, float, float]) -> dict[str, Any] | None:
    async with _cache_lock:
        cached = _cache.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
            return dict(cached[1])
        _cache.pop(key, None)
        return None


async def _cache_put(key: tuple[str, float, float], result: dict[str, Any]) -> None:
    async with _cache_lock:
        _cache[key] = (time.monotonic(), dict(result))
        if len(_cache) > 4096:
            oldest = min(_cache, key=lambda item: _cache[item][0])
            _cache.pop(oldest, None)


async def _request_json(client: httpx.AsyncClient, url: str, *, params: dict[str, Any] | None = None,
                        json_body: dict[str, Any] | None = None) -> Any:
    async with _semaphore:
        response = await client.post(url, json=json_body) if json_body is not None else await client.get(url, params=params)
    response.raise_for_status()
    return response.json()


def _power_values(payload: dict[str, Any]) -> dict[str, Any]:
    params = ((payload.get("properties") or {}).get("parameter") or {})
    if not params:
        raise ValueError("NASA POWER returned no parameter series")
    dates = sorted(set.intersection(*(set(series) for series in params.values() if isinstance(series, dict))))
    if not dates:
        raise ValueError("NASA POWER returned no common daily values")
    def valid(name: str) -> list[float]:
        values = []
        for day in dates:
            try:
                value = float((params.get(name) or {})[day])
                if value > -900:
                    values.append(value)
            except (KeyError, TypeError, ValueError):
                continue
        return values
    rain = valid("PRECTOTCORR")
    tmean = valid("T2M")
    tmax = valid("T2M_MAX")
    humidity = valid("RH2M")
    wind = valid("WS10M")
    solar = valid("ALLSKY_SFC_SW_DWN")
    recent_rain = []
    for day in dates[-7:]:
        try:
            value = float((params.get("PRECTOTCORR") or {})[day])
            if value > -900:
                recent_rain.append(value)
        except (KeyError, TypeError, ValueError):
            pass
    hot_days = sum(value >= 35.0 for value in tmax[-7:])
    metrics = {
        "mean_temperature_c": round(sum(tmean) / len(tmean), 2) if tmean else None,
        "max_temperature_c": round(max(tmax), 2) if tmax else None,
        "rainfall_total_mm_last_7d": round(sum(recent_rain), 2) if recent_rain else None,
        "relative_humidity_mean_pct": round(sum(humidity) / len(humidity), 1) if humidity else None,
        "wind_speed_mean_m_s": round(sum(wind) / len(wind), 2) if wind else None,
        "shortwave_mean_mj_m2_day": round(sum(solar) / len(solar), 2) if solar else None,
        "days_tmax_at_or_above_35c_last_7d": hot_days,
    }
    return {"metrics": metrics, "observation_time": dates[-1], "days_returned": len(dates),
            "provider_header": payload.get("header", {})}


async def _fetch_power(client: httpx.AsyncClient, lat: float, lon: float) -> dict[str, Any]:
    dataset_id = "nasa_power"
    key = _cache_key(dataset_id, lat, lon)
    cached = await _cache_get(key)
    if cached:
        return cached
    today = datetime.now(timezone.utc).date()
    # The 7-day lag reduces failures from near-real-time product latency.
    end = today - timedelta(days=2)
    start = end - timedelta(days=14)
    query = {"parameters": "T2M,T2M_MAX,PRECTOTCORR,RH2M,WS10M,ALLSKY_SFC_SW_DWN",
             "community": "AG", "longitude": lon, "latitude": lat,
             "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"),
             "format": "JSON", "time-standard": "UTC"}
    try:
        payload = await _request_json(client, NASA_POWER_URL, params=query)
        parsed = _power_values(payload)
        result = {"dataset_id": dataset_id, "dataset_name": DATASETS[dataset_id]["name"],
                  "platform": DATASETS[dataset_id]["platform"], "source_status": "live_numeric",
                  "observation_time": parsed["observation_time"], "spatial_resolution": "parameter-specific NASA POWER grid",
                  "metrics": parsed["metrics"], "quality": {"flag": "provider_values", "days_returned": parsed["days_returned"]},
                  "simulation": False, "decision_eligible": False,
                  "catalog": {"provider_header": parsed["provider_header"]}, "source_url": NASA_POWER_URL,
                  "limitations": ["Gridded environmental context; not a farm sensor or forecast."]}
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.info("NASA POWER unavailable; returning labeled fallback (%s)", type(exc).__name__)
        result = _empty_result(dataset_id, lat, lon, "provider_timeout_or_invalid_response")
    await _cache_put(key, result)
    return result


def _cmr_query_url(dataset_id: str, lat: float, lon: float) -> tuple[str, dict[str, Any]]:
    spec = DATASETS[dataset_id]
    end = datetime.now(timezone.utc).date()
    lookback = 180 if dataset_id == "grace" else 60 if dataset_id.startswith("modis") else 30
    start = end - timedelta(days=lookback)
    params: dict[str, Any] = {"short_name": spec["short_name"], "point": f"{lon:.5f},{lat:.5f}",
                              "temporal": f"{start.isoformat()}T00:00:00Z,{end.isoformat()}T23:59:59Z",
                              "page_size": 5, "sort_key": "-start_date"}
    if spec.get("version"):
        params["version"] = spec["version"]
    return CMR_GRANULES_URL, params


def _catalog_result(dataset_id: str, lat: float, lon: float, payload: dict[str, Any]) -> dict[str, Any]:
    entries = ((payload.get("feed") or {}).get("entry") or [])
    if not entries:
        return _simulated_result(dataset_id, lat, lon, "no_recent_catalog_granule_at_coordinate")
    first = entries[0]
    links = first.get("links") or []
    browse = next((link.get("href") for link in links
                   if link.get("rel") in {"http://esipfed.org/ns/fedsearch/1.1/browse", "browse"}
                   or "browse" in (link.get("title") or "").lower()), None)
    spec = DATASETS[dataset_id]
    return {"dataset_id": dataset_id, "dataset_name": spec["name"], "platform": spec["platform"],
            "source_status": "catalog_metadata_only", "observation_time": first.get("time_start"),
            "spatial_resolution": None, "metrics": _mock_metrics(dataset_id, lat, lon),
            "quality": {"flag": "CATALOG_FOUND_METRICS_SIMULATED", "granules_in_page": len(entries)},
            "simulation": True, "decision_eligible": False,
            "catalog": {"short_name": spec["short_name"], "version": first.get("collection_version_id"),
                        "granule_id": first.get("producer_granule_id") or first.get("title"),
                        "browse_url": browse, "data_access": "CMR discovery is public; granule download may require free Earthdata Login."},
            "source_url": CMR_GRANULES_URL,
            "limitations": ["Catalog metadata is live; feature metric values remain synthetic until an approved pixel-subset/data-access path is configured."]}


async def _fetch_cmr(client: httpx.AsyncClient, dataset_id: str, lat: float, lon: float) -> dict[str, Any]:
    key = _cache_key(dataset_id, lat, lon)
    cached = await _cache_get(key)
    if cached:
        return cached
    url, params = _cmr_query_url(dataset_id, lat, lon)
    try:
        payload = await _request_json(client, url, params=params)
        if not isinstance(payload, dict):
            raise ValueError("CMR payload was not an object")
        result = _catalog_result(dataset_id, lat, lon, payload)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.info("CMR unavailable for %s; returning labeled fallback (%s)", dataset_id, type(exc).__name__)
        result = _empty_result(dataset_id, lat, lon, "cmr_timeout_or_invalid_response")
    await _cache_put(key, result)
    return result


async def _fetch_landsat(client: httpx.AsyncClient, dataset_id: str, lat: float, lon: float) -> dict[str, Any]:
    key = _cache_key(dataset_id, lat, lon)
    cached = await _cache_get(key)
    if cached:
        return cached
    start = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat().replace("+00:00", "Z")
    body = {"collections": [DATASETS[dataset_id]["collection"]], "intersects": {"type": "Point", "coordinates": [lon, lat]},
            "datetime": f"{start}/..", "limit": 5, "sortby": [{"field": "properties.datetime", "direction": "desc"}]}
    try:
        payload = await _request_json(client, LANDSAT_STAC_URL, json_body=body)
        features = payload.get("features") or []
        if not features:
            result = _simulated_result(dataset_id, lat, lon, "no_recent_stac_scene_at_coordinate")
        else:
            item = features[0]
            properties = item.get("properties") or {}
            assets = item.get("assets") or {}
            thumb = next((asset.get("href") for asset in assets.values() if asset.get("roles") and "thumbnail" in asset["roles"]), None)
            result = {"dataset_id": dataset_id, "dataset_name": DATASETS[dataset_id]["name"], "platform": DATASETS[dataset_id]["platform"],
                      "source_status": "catalog_metadata_only", "observation_time": properties.get("datetime"),
                      "spatial_resolution": properties.get("gsd"), "metrics": _mock_metrics(dataset_id, lat, lon),
                      "quality": {"flag": "STAC_METADATA_ONLY", "cloud_cover_pct": properties.get("eo:cloud_cover")},
                      "simulation": True, "decision_eligible": False,
                      "catalog": {"collection": DATASETS[dataset_id]["collection"], "item_id": item.get("id"), "thumbnail_url": thumb,
                                  "cloud_cover_pct": properties.get("eo:cloud_cover"), "data_access": "Public STAC discovery; asset access/terms are controlled by USGS."},
                      "source_url": LANDSAT_STAC_URL,
                      "limitations": ["Landsat 8/9 are NASA-USGS missions; STAC metadata is live, but NDVI values here are simulated, not derived from surface reflectance."]}
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.info("Landsat STAC unavailable; returning labeled fallback (%s)", type(exc).__name__)
        result = _empty_result(dataset_id, lat, lon, "stac_timeout_or_invalid_response")
    await _cache_put(key, result)
    return result


def _parse_daymet_csv(text: str) -> list[dict[str, str]]:
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    header_index = next((index for index, line in enumerate(lines) if "year" in line.lower() and "yday" in line.lower()), None)
    if header_index is None:
        raise ValueError("Daymet response has no CSV header")
    return list(csv.DictReader(lines[header_index:]))


async def _fetch_daymet_impl(client: httpx.AsyncClient, lat: float, lon: float) -> dict[str, Any]:
    dataset_id = "daymet"
    key = _cache_key(dataset_id, lat, lon)
    cached = await _cache_get(key)
    if cached:
        return cached
    if not (14.5 <= lat <= 52.0 and -131.0 <= lon <= -53.0):
        result = _empty_result(dataset_id, lat, lon, "outside_daymet_north_america_coverage")
        result["source_status"] = "outside_coverage_simulated_fallback"
        await _cache_put(key, result)
        return result
    year = datetime.now(timezone.utc).year - 1
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    query = {"lat": lat, "lon": lon, "vars": "tmax,tmin,prcp,srad,vp", "start": start.isoformat(),
             "end": end.isoformat(), "format": "csv"}
    try:
        async with _semaphore:
            response = await client.get(DAYMET_URL, params=query)
        response.raise_for_status()
        rows = _parse_daymet_csv(response.text)
        if not rows:
            raise ValueError("Daymet returned no rows")
        tail = rows[-30:]
        def avg(column: str) -> float | None:
            vals = []
            for row in tail:
                try:
                    value = float(row[column])
                    if value > -900:
                        vals.append(value)
                except (KeyError, ValueError, TypeError):
                    continue
            return round(sum(vals) / len(vals), 2) if vals else None
        rain = []
        for row in tail:
            try:
                value = float(row["prcp"])
                if value >= 0:
                    rain.append(value)
            except (KeyError, ValueError, TypeError):
                pass
        result = {"dataset_id": dataset_id, "dataset_name": DATASETS[dataset_id]["name"],
                  "platform": DATASETS[dataset_id]["platform"], "source_status": "live_numeric",
                  "observation_time": f"{year}-12-31", "spatial_resolution": "1 km grid",
                  "metrics": {"mean_tmax_c_last_30d_of_year": avg("tmax"), "mean_tmin_c_last_30d_of_year": avg("tmin"),
                              "rainfall_total_mm_last_30d_of_year": round(sum(rain), 2) if rain else None,
                              "mean_shortwave_w_m2_last_30d_of_year": avg("srad"), "mean_vapor_pressure_pa_last_30d_of_year": avg("vp")},
                  "quality": {"flag": "provider_values", "daily_rows": len(rows)}, "simulation": False,
                  "decision_eligible": False, "catalog": {"latest_complete_year_requested": year},
                  "source_url": DAYMET_URL, "limitations": ["Daymet is North America only; these values describe the final 30 days of the latest complete calendar year and are not current weather or forecasts."]}
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.info("Daymet unavailable; returning labeled fallback (%s)", type(exc).__name__)
        result = _empty_result(dataset_id, lat, lon, "daymet_timeout_or_invalid_response")
    await _cache_put(key, result)
    return result


async def fetch_nasa_power(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    return await _fetch_power(client, latitude, longitude)


async def fetch_smap(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    return await _fetch_cmr(client, "smap", latitude, longitude)


async def fetch_gpm_imerg(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    return await _fetch_cmr(client, "gpm_imerg", latitude, longitude)


async def fetch_modis_terra(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    return await _fetch_cmr(client, "modis_terra", latitude, longitude)


async def fetch_modis_aqua(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    return await _fetch_cmr(client, "modis_aqua", latitude, longitude)


async def fetch_landsat_8(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    return await _fetch_landsat(client, "landsat_8", latitude, longitude)


async def fetch_landsat_9(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    return await _fetch_landsat(client, "landsat_9", latitude, longitude)


async def fetch_ecostress(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    return await _fetch_cmr(client, "ecostress", latitude, longitude)


async def fetch_grace(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    return await _fetch_cmr(client, "grace", latitude, longitude)


async def fetch_viirs(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    return await _fetch_cmr(client, "viirs_fire", latitude, longitude)


async def fetch_nasadem_srtm(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    return await _fetch_cmr(client, "nasadem_srtm", latitude, longitude)


async def fetch_daymet(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    return await _fetch_daymet_impl(client, latitude, longitude)


async def fetch_tempo(client: httpx.AsyncClient, latitude: float, longitude: float) -> dict[str, Any]:
    return await _fetch_cmr(client, "tempo", latitude, longitude)


FETCHERS = {
    "nasa_power": fetch_nasa_power, "smap": fetch_smap, "gpm_imerg": fetch_gpm_imerg,
    "modis_terra": fetch_modis_terra, "modis_aqua": fetch_modis_aqua,
    "landsat_8": fetch_landsat_8, "landsat_9": fetch_landsat_9,
    "ecostress": fetch_ecostress, "grace": fetch_grace, "viirs_fire": fetch_viirs,
    "nasadem_srtm": fetch_nasadem_srtm, "daymet": fetch_daymet, "tempo": fetch_tempo,
}


async def _fetch_one(client: httpx.AsyncClient, dataset_id: str, lat: float, lon: float) -> dict[str, Any]:
    try:
        return await FETCHERS[dataset_id](client, lat, lon)
    except Exception as exc:  # Last-resort isolation: one bad adapter never fails sync-all.
        logger.exception("Satellite adapter %s failed unexpectedly", dataset_id)
        return _empty_result(dataset_id, lat, lon, f"adapter_error:{type(exc).__name__}")


async def sync_datasets(latitude: float, longitude: float, dataset_ids: list[str] | None = None) -> dict[str, Any]:
    selected = dataset_ids or list(DATASETS)
    if any(item not in DATASETS for item in selected):
        unknown = sorted(set(selected) - set(DATASETS))
        raise HTTPException(status_code=422, detail=f"Unknown dataset IDs: {', '.join(unknown)}")
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True,
                                     headers={"User-Agent": "KisanX-NASA-Satellite-Hub/1.0"}) as client:
            values = await asyncio.gather(*[_fetch_one(client, item, latitude, longitude) for item in selected])
    except Exception as exc:
        # Includes client/session failures: fulfill the always-available fallback contract.
        logger.exception("Satellite hub request pool failed; returning mock set")
        values = [_empty_result(item, latitude, longitude, f"hub_error:{type(exc).__name__}") for item in selected]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latitude": latitude,
        "longitude": longitude,
        "datasets_requested": len(values),
        "datasets_live_numeric": sum(item["source_status"] == "live_numeric" for item in values),
        "datasets_catalog_only": sum(item["source_status"] == "catalog_metadata_only" for item in values),
        "datasets_simulated": sum(item["simulation"] for item in values),
        "feature_mappings": FEATURE_MAP,
        "datasets": values,
        "limitations": LIMITATIONS,
    }


@router.get("/sync-all", response_model=SyncAllResponse)
async def sync_all_satellites(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
):
    return await sync_datasets(latitude, longitude)


@router.post("/query-feature")
async def query_feature(payload: FeatureQuery):
    selected = FEATURE_DATASETS[payload.feature]
    response = await sync_datasets(payload.latitude, payload.longitude, selected)
    response["requested_feature"] = payload.feature
    response["feature_metric_groups"] = FEATURE_MAP[payload.feature]
    # A frontend/AI client can consume these refs while respecting the synthetic flag.
    response["metric_provenance"] = [
        {"dataset_id": item["dataset_id"], "source_status": item["source_status"],
         "simulation": item["simulation"], "decision_eligible": item["decision_eligible"],
         "metrics": item["metrics"]}
        for item in response["datasets"]
    ]
    return response


def public_data_endpoints() -> dict[str, str]:
    """Expose transparent endpoint links for frontend attribution/debug panels."""
    return {"nasa_power": NASA_POWER_URL, "daymet": DAYMET_URL, "cmr_discovery": CMR_GRANULES_URL,
            "landsat_stac": LANDSAT_STAC_URL, "nasa_gibs_visualization": NASA_GIBS_WMS_URL}
