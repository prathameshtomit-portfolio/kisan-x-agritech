def create_farm(client):
    response = client.post(
        "/api/v1/farms",
        json={"name": "Test farm", "latitude": 21.1, "longitude": 79.1},
    )
    assert response.status_code == 201
    return response.json()["farm_id"]


def test_rotation_compare_saves_report(client):
    farm_id = create_farm(client)
    response = client.post(
        "/api/v1/rotations/compare",
        json={
            "farm_id": farm_id,
            "candidates": [
                {"rotation_id": "r1", "label": "Option 1", "sequence": ["crop-a", "crop-b"]}
            ],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["evidence_status"] == "insufficient"
    assert payload["report_id"]
    saved = client.get(f"/api/v1/reports/{payload['report_id']}")
    assert saved.status_code == 200
    assert saved.json()["report_type"] == "rotation_comparison"


def test_simulation_returns_baseline_and_scenario(client):
    farm_id = create_farm(client)
    response = client.post(
        "/api/v1/simulations",
        json={
            "farm_id": farm_id,
            "candidates": [
                {"rotation_id": "r1", "label": "Option 1", "sequence": ["crop-a", "crop-b"]}
            ],
            "scenario": {"rainfall_change_pct": -20},
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["report_id"]
    assert payload["baseline"]["rotations"][0]["eligibility"] == "uncertain"
    assert payload["scenario_result"]["rotations"][0]["eligibility"] == "uncertain"
    assert payload["changed_inputs"]["rainfall_change_pct"]["scenario"] == -20


def test_simulation_report_snapshot_is_retrievable(client):
    farm_id = create_farm(client)
    response = client.post(
        "/api/v1/simulations",
        json={
            "farm_id": farm_id,
            "candidates": [
                {"rotation_id": "r1", "label": "Option 1", "sequence": ["crop-a", "crop-b"]}
            ],
            "scenario": {"rainfall_change_pct": -10},
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    saved = client.get(f"/api/v1/reports/{payload['report_id']}")
    assert saved.status_code == 200
    assert saved.json()["payload"]["report_id"] == payload["report_id"]
