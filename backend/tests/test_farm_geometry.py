import pytest

from app.services.farm_geometry import validate_and_measure_area_hectares


def square(west=79.3, south=21.3, size=0.01):
    return [[west, south], [west + size, south], [west + size, south + size],
            [west, south + size], [west, south]]


def test_spherical_area_is_calculated_for_small_farm_boundary():
    area = validate_and_measure_area_hectares({"type": "Polygon", "coordinates": [square()]})
    assert 100 < area < 130


def test_interior_ring_is_subtracted_from_farm_area():
    outer = square()
    hole = square(west=79.302, south=21.302, size=0.002)
    area_with_hole = validate_and_measure_area_hectares(
        {"type": "Polygon", "coordinates": [outer, hole]}
    )
    assert area_with_hole < validate_and_measure_area_hectares(
        {"type": "Polygon", "coordinates": [outer]}
    )


def test_multipolygon_area_sums_each_component():
    first, second = square(), square(west=79.32)
    multi_area = validate_and_measure_area_hectares(
        {"type": "MultiPolygon", "coordinates": [[first], [second]]}
    )
    single_area = validate_and_measure_area_hectares({"type": "Polygon", "coordinates": [first]})
    assert multi_area == pytest.approx(single_area * 2, rel=1e-9)


def test_self_crossing_ring_is_rejected():
    crossing = [[79.3, 21.3], [79.32, 21.32], [79.3, 21.32], [79.31, 21.3], [79.3, 21.3]]
    with pytest.raises(ValueError):
        validate_and_measure_area_hectares({"type": "Polygon", "coordinates": [crossing]})


def test_antimeridian_boundary_has_small_finite_area():
    crossing = [[179.99, 10], [-179.99, 10], [-179.99, 10.01], [179.99, 10.01], [179.99, 10]]
    area = validate_and_measure_area_hectares({"type": "Polygon", "coordinates": [crossing]})
    assert 100 < area < 300
