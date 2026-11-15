from app.services.nasa_satellites_hub import DATASETS, _catalog_result, _unavailable_result


def test_unavailable_satellite_records_never_include_generated_metrics():
    assert len(DATASETS) >= 10
    for dataset_id in DATASETS:
        result = _unavailable_result(dataset_id, 20.5, 78.9, "provider_offline")
        assert result["source_status"] == "unavailable"
        assert result["metrics"] == {}
        assert result["simulation"] is False
        assert result["decision_eligible"] is False


def test_live_catalog_metadata_does_not_claim_pixel_measurements():
    result = _catalog_result(
        "smap",
        20.5,
        78.9,
        {"feed": {"entry": [{"time_start": "2026-11-15T00:00:00Z", "links": []}]}},
    )
    assert result["source_status"] == "catalog_metadata_only"
    assert result["metrics"] == {}
    assert result["quality"]["flag"] == "CATALOG_METADATA_ONLY"
    assert result["simulation"] is False
