from app.services.nasa_power import NASA_POWER_Client, PARAMETER_MAP


def test_nasa_power_normalizer_preserves_missing_values():
    payload = {
        "header": {"title": "test"},
        "properties": {
            "parameter": {
                "T2M": {"20250101": 25.5, "20250102": -999.0},
                "PRECTOTCORR": {"20250101": 2.3},
            },
            "parameter_information": {},
        },
    }
    records = NASA_POWER_Client._normalize(payload, 21.1, 79.1)
    assert len(records) == 3
    t2m_missing = next(item for item in records if item.raw_parameter == "T2M" and item.observed_at.isoformat() == "2025-01-02")
    assert t2m_missing.value is None
    assert t2m_missing.quality_flag == "missing"
    precip = next(item for item in records if item.raw_parameter == "PRECTOTCORR")
    assert precip.unit == "mm/day"


def test_nasa_power_normalizer_preserves_all_six_member_one_variables_and_resolution():
    payload = {
        "header": {"title": "test"},
        "properties": {
            "parameter": {
                "T2M": {"20250101": 25.5},
                "T2M_MAX": {"20250101": 31.2},
                "T2M_MIN": {"20250101": 18.3},
                "PRECTOTCORR": {"20250101": 2.3},
                "RH2M": {"20250101": 68.0},
                "ALLSKY_SFC_SW_DWN": {"20250101": 15.4},
            },
            "parameter_information": {},
        },
    }
    records = NASA_POWER_Client._normalize(payload, 21.1458, 79.0882)

    assert len(records) == 6
    assert {record.raw_parameter for record in records} == set(PARAMETER_MAP)
    assert {record.time_standard for record in records} == {"UTC"}
    assert {record.coverage_fraction for record in records} == {1.0}
    solar = next(item for item in records if item.raw_parameter == "ALLSKY_SFC_SW_DWN")
    assert solar.unit == "MJ/m²/day"
    assert solar.spatial_resolution == "1° (~100 km)"
    rain = next(item for item in records if item.raw_parameter == "PRECTOTCORR")
    assert "MERRA-2" in rain.product
