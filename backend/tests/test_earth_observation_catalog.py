def test_catalog_exposes_six_distinct_mission_sources(client):
    response = client.get("/api/v1/earth-observation/catalog")
    assert response.status_code == 200
    data = response.json()
    assert data["platform_count"] == 6
    assert {"Terra", "Aqua", "GPM", "SMAP", "Landsat", "Suomi-NPP"} == set(data["platforms"])
    layer_ids = {layer["id"] for layer in data["layers"]}
    assert {
        "modis_terra_truecolor",
        "modis_aqua_truecolor",
        "imerg_precipitation",
        "smap_surface",
        "smap_rootzone",
        "landsat_weld_ndvi",
        "viirs_snpp_thermal_anomalies",
    } <= layer_ids


def test_main_page_and_assets_are_served_by_fastapi(client):
    page = client.get("/")
    script = client.get("/assets/app.js")
    app_config = client.get("/assets/app-config.js")
    payments = client.get("/assets/payments.js")
    worker = client.get("/sw.js")
    assert page.status_code == 200
    assert 'id="farmMap"' in page.text
    assert 'id="krishiqLauncher"' in page.text
    assert script.status_code == 200
    assert "async function sendChat()" in script.text
    assert app_config.status_code == 200
    assert "KISANX_API_BASE" in app_config.text
    assert payments.status_code == 200
    assert "window.KISANX_API_BASE" in payments.text
    assert worker.status_code == 200


def test_nasa_power_requires_an_explicit_location(client):
    response = client.get("/api/v1/nasa/power")
    assert response.status_code == 422


def test_nasa_power_rejects_out_of_range_location(client):
    response = client.get("/api/v1/nasa/power?lat=91&lon=79")
    assert response.status_code == 422

