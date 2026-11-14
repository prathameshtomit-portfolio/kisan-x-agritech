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
