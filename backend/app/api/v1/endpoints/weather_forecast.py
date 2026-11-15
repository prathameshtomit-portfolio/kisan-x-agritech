"""Short-range weather forecasts from Open-Meteo's public forecast API."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["weather forecast"])
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


@router.get("/weather/forecast")
async def weather_forecast(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    days: int = Query(default=7, ge=1, le=7),
) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "forecast_days": days,
        "timezone": "auto",
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,wind_speed_10m,weather_code,is_day",
        "hourly": "temperature_2m,precipitation_probability,precipitation,relative_humidity_2m,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max",
    }
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            response = await client.get(OPEN_METEO_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Weather forecast provider is temporarily unavailable; no substitute forecast was inserted.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("daily"), dict):
        raise HTTPException(status_code=502, detail="Weather forecast provider returned an unexpected response.")
    return {
        "provider": "Open-Meteo",
        "source_url": OPEN_METEO_URL,
        "coordinates": {"latitude": lat, "longitude": lon},
        "timezone": data.get("timezone"),
        "current": data.get("current"),
        "hourly": data.get("hourly"),
        "daily": data.get("daily"),
        "units": {"current": data.get("current_units"), "hourly": data.get("hourly_units"), "daily": data.get("daily_units")},
        "provenance": "Short-range numerical weather forecast from Open-Meteo. Regional model output, not a farm weather station or official IMD warning.",
        "attribution": "Weather data by Open-Meteo.com",
    }
