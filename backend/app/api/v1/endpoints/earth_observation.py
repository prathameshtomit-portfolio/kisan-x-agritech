"""Public NASA GIBS browse layers and Copernicus scene discovery for the map UI."""
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(tags=["Earth observation map"])
POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


def _validate_geometry(geometry: dict[str, Any]) -> None:
    """Reject malformed or unreasonable GeoJSON before sending it to a provider."""
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if kind not in {"Polygon", "MultiPolygon"} or not isinstance(coordinates, list):
        raise HTTPException(status_code=422, detail="Provide a GeoJSON Polygon or MultiPolygon boundary.")
    polygons = [coordinates] if kind == "Polygon" else coordinates
    if not polygons or len(polygons) > 100:
        raise HTTPException(status_code=422, detail="Boundary must contain between 1 and 100 polygons.")
    point_count = 0
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise HTTPException(status_code=422, detail="Each polygon must contain an exterior ring.")
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4:
                raise HTTPException(status_code=422, detail="Each polygon ring needs at least four coordinates.")
            if ring[0] != ring[-1]:
                raise HTTPException(status_code=422, detail="Each polygon ring must be closed (first and last coordinates must match).")
            for point in ring:
                if (not isinstance(point, (list, tuple)) or len(point) < 2
                        or not isinstance(point[0], (int, float)) or isinstance(point[0], bool)
                        or not isinstance(point[1], (int, float)) or isinstance(point[1], bool)
                        or not (-180 <= point[0] <= 180) or not (-90 <= point[1] <= 90)):
                    raise HTTPException(status_code=422, detail="Boundary coordinates must be valid longitude/latitude pairs.")
                point_count += 1
                if point_count > 20_000:
                    raise HTTPException(status_code=422, detail="Boundary is too detailed. Simplify it to 20,000 coordinates or fewer.")

LAYERS = [
    {"id":"modis_terra_truecolor","title":"NASA MODIS Terra true colour","provider":"NASA MODIS Terra","layer":"MODIS_Terra_CorrectedReflectance_TrueColor","format":"image/jpeg","period":"Daily","resolution":"250 m class imagery","units":"RGB reflectance visualisation","summary":"Corrected-reflectance imagery for landscape and seasonal context.","limitation":"MODIS pixels are much larger than many small farms. This is visual context, not parcel-level crop scoring.","use":"Visual context","temporal":"Daily visualisation","kind":"visualisation"},
    {"id":"modis_aqua_truecolor","title":"NASA MODIS Aqua true colour","provider":"NASA MODIS Aqua","layer":"MODIS_Aqua_CorrectedReflectance_TrueColor","format":"image/jpeg","period":"Daily","resolution":"250 m class imagery","units":"RGB reflectance visualisation","summary":"Aqua afternoon-pass corrected-reflectance imagery for landscape and seasonal context.","limitation":"MODIS pixels are much larger than many small farms. This is visual context, not parcel-level crop scoring; Aqua is a separate platform from Terra.","use":"Visual context","temporal":"Daily visualisation","kind":"visualisation"},
    {"id":"imerg_precipitation","title":"NASA GPM IMERG precipitation rate","provider":"NASA GPM IMERG","layer":"IMERG_Precipitation_Rate","format":"image/png","period":"Daily","resolution":"about 10 km grid","units":"mm/hour rate visualisation","summary":"Satellite-based precipitation-rate context.","limitation":"A gridded estimate is not a farm rain gauge.","use":"Regional rainfall context","temporal":"Daily browse visualisation","kind":"visualisation"},
    {"id":"smap_surface","title":"NASA SMAP surface soil moisture","provider":"NASA SMAP L4","layer":"SMAP_L4_Analyzed_Surface_Soil_Moisture","format":"image/png","period":"Daily","resolution":"9 km grid","units":"m³/m³ visualisation","summary":"Model-assisted surface soil-moisture estimate informed by SMAP observations.","limitation":"The coarse footprint cannot resolve moisture in an individual small parcel.","use":"Regional moisture context","temporal":"Daily analysis visualisation","kind":"visualisation"},
    {"id":"smap_rootzone","title":"NASA SMAP root-zone soil moisture","provider":"NASA SMAP L4","layer":"SMAP_L4_Analyzed_Root_Zone_Soil_Moisture","format":"image/png","period":"Daily","resolution":"9 km grid","units":"m³/m³ model-derived estimate","summary":"Model-derived root-zone moisture context.","limitation":"This is not a direct root-zone sensor reading. Confirm soil water locally.","use":"Regional root-zone context","temporal":"Daily analysis visualisation","kind":"visualisation"},
    {"id":"landsat_weld_ndvi","title":"Landsat WELD monthly NDVI","provider":"NASA GIBS / Landsat WELD","layer":"Landsat_WELD_NDVI_Global_Monthly","format":"image/png","period":"Monthly","resolution":"Landsat-derived 30 m class product","units":"NDVI visualisation","summary":"Monthly Landsat-derived vegetation-index visualisation.","limitation":"Monthly composite, not a field NDVI measurement. Clouds, mixed pixels and crop stage affect interpretation.","use":"Historical vegetation context","temporal":"Monthly composite","kind":"visualisation"},
    {"id":"viirs_snpp_thermal_anomalies","title":"NASA/NOAA Suomi-NPP VIIRS thermal anomalies","provider":"NASA GIBS / Suomi-NPP VIIRS","layer":"VIIRS_SNPP_Thermal_Anomalies_375m_All","format":"image/png","period":"Daily","resolution":"375 m thermal anomaly product","units":"Thermal anomaly browse visualisation","summary":"Browse view of active thermal anomalies that can support regional fire awareness.","limitation":"An anomaly is not proof of crop-residue burning on a specific farm. Check the date, confidence, and authoritative FIRMS record before acting.","use":"Regional fire awareness","temporal":"Near-real-time browse visualisation","kind":"visualisation"},
]


@router.get("/earth-observation/catalog")
def earth_observation_catalog() -> dict[str, Any]:
    return {"provider":"NASA GIBS","service":"https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi","service_type":"OGC WMS 1.1.1","platforms":["Terra","Aqua","GPM","SMAP","Landsat","Suomi-NPP"],"platform_count":6,"layers":LAYERS,"important_note":"GIBS provides pre-rendered browse visualisations, not parcel-clipped numerical summaries. Terra, Aqua, GPM, SMAP, Landsat and Suomi-NPP are six distinct mission/platform sources represented here."}


@router.get("/nasa/power")
async def nasa_power_context(lat: float = Query(default=21.39575, ge=-90, le=90),
                             lon: float = Query(default=79.32575, ge=-180, le=180),
                             days: int = Query(default=30, ge=7, le=90)) -> dict[str, Any]:
    end = datetime.now(timezone.utc).date() - timedelta(days=3)
    start = end - timedelta(days=days)
    params = {"parameters":"T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M,WS10M","community":"AG",
              "longitude":lon,"latitude":lat,"start":start.strftime("%Y%m%d"),"end":end.strftime("%Y%m%d"),"format":"JSON","time-standard":"UTC"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(POWER_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="NASA POWER is temporarily unavailable; no substitute values were inserted.") from exc
    return {"provider":"NASA POWER","source_url":POWER_URL,"requested_period":{"start":start.isoformat(),"end":end.isoformat()},
            "coordinates":{"latitude":lat,"longitude":lon},"units":(data.get("header") or {}).get("parameters",{}),
            "parameters":((data.get("properties") or {}).get("parameter") or {}),
            "provenance":"NASA POWER daily gridded context, not an on-farm weather station or forecast.","raw_header":data.get("header",{})}


class SceneSearch(BaseModel):
    geometry: dict[str, Any]
    start_date: date
    end_date: date
    max_cloud_cover: int = Field(default=40, ge=0, le=100)
    limit: int = Field(default=15, ge=1, le=30)


@router.post("/earth-observation/sentinel-2/search")
async def search_sentinel_scenes(payload: SceneSearch) -> dict[str, Any]:
    geometry = payload.geometry
    _validate_geometry(geometry)
    if payload.end_date < payload.start_date or (payload.end_date-payload.start_date).days > 366:
        raise HTTPException(status_code=422, detail="Choose a valid date range of at most 366 days.")
    endpoint = "https://stac.dataspace.copernicus.eu/v1/search"
    body = {"collections":["sentinel-2-l2a"],"intersects":geometry,
            "datetime":f"{payload.start_date}T00:00:00Z/{payload.end_date}T23:59:59Z","limit":payload.limit,
            "query":{"eo:cloud_cover":{"lte":payload.max_cloud_cover}}}
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.post(endpoint, json=body, headers={"Accept":"application/geo+json, application/json"})
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Copernicus scene catalogue is temporarily unavailable.") from exc
    scenes = []
    for item in result.get("features", []):
        props = item.get("properties") or {}
        assets = item.get("assets") or {}
        cloud = props.get("eo:cloud_cover")
        scenes.append({"id":item.get("id"),"datetime":props.get("datetime"),"platform":props.get("platform") or "Sentinel-2",
                       "cloud_cover":cloud,"collection":item.get("collection") or "sentinel-2-l2a","asset_keys":list(assets),
                       "item_url":next((link.get("href") for link in item.get("links",[]) if link.get("rel")=="self"),None)})
    scenes.sort(key=lambda row:row.get("datetime") or "", reverse=True)
    return {"provider":"Copernicus Data Space Ecosystem","count":len(scenes),"scenes":scenes,"status":"catalogue_metadata_only",
            "note":"Scene metadata only. No bands are downloaded and no cloud masking, NDVI calculation or parcel statistics are performed."}
