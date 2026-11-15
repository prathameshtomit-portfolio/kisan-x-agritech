def test_create_read_update_farm(client):
    create = client.post(
        "/api/v1/farms",
        json={
            "name": "Test farm",
            "latitude": 21.1458,
            "longitude": 79.0882,
            "region": "Nagpur",
            "season": "kharif",
            "soil_fields": {"pH": None},
            "irrigation": "unknown",
        },
    )
    assert create.status_code == 201, create.text
    farm = create.json()
    assert farm["missing_inputs"]
    assert farm["soil_fields"]["pH"] is None

    farm_id = farm["farm_id"]
    read = client.get(f"/api/v1/farms/{farm_id}")
    assert read.status_code == 200
    assert read.json()["name"] == "Test farm"

    update = client.patch(f"/api/v1/farms/{farm_id}", json={"irrigation": "limited"})
    assert update.status_code == 200
    assert update.json()["irrigation"] == "limited"


def test_invalid_coordinates_rejected(client):
    response = client.post(
        "/api/v1/farms",
        json={"name": "Bad", "latitude": 120, "longitude": 80},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_polygon_area_is_validated_and_calculated_by_backend(client):
    response = client.post(
        "/api/v1/farms",
        json={
            "name": "Mapped farm",
            "latitude": 21.35,
            "longitude": 79.35,
            "area_value": 9999,
            "area_unit": "hectare",
            "geometry_geojson": {
                "type": "Polygon",
                "coordinates": [[[79.3, 21.3], [79.31, 21.3], [79.31, 21.31], [79.3, 21.31], [79.3, 21.3]]],
            },
        },
    )
    assert response.status_code == 201, response.text
    farm = response.json()
    assert 100 < farm["area_value"] < 130
    assert farm["area_value"] != 9999
    assert farm["area_unit"] == "hectare"


def test_self_intersecting_field_boundary_is_rejected(client):
    response = client.post(
        "/api/v1/farms",
        json={
            "name": "Invalid boundary",
            "latitude": 21.35,
            "longitude": 79.35,
            "geometry_geojson": {
                "type": "Polygon",
                "coordinates": [[[79.3, 21.3], [79.31, 21.31], [79.3, 21.31], [79.31, 21.3], [79.3, 21.3]]],
            },
        },
    )
    assert response.status_code == 422
    assert "boundary" in response.json()["error"]["message"].lower()
