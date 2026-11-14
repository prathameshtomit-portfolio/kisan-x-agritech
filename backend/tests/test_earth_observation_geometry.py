import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.earth_observation import _validate_geometry


def polygon(ring=None):
    return {"type": "Polygon", "coordinates": [ring or [[79.3, 21.3], [79.4, 21.3], [79.4, 21.4], [79.3, 21.3]]]}


def test_accepts_closed_polygon_with_valid_coordinates():
    _validate_geometry(polygon())


def test_rejects_unclosed_polygon_ring():
    with pytest.raises(HTTPException) as error:
        _validate_geometry(polygon([[79.3, 21.3], [79.4, 21.3], [79.4, 21.4], [79.3, 21.4]]))
    assert "closed" in error.value.detail


@pytest.mark.parametrize("point", [[181, 21.3], [79.3, 91], ["west", 21.3], [79.3]])
def test_rejects_invalid_coordinates(point):
    with pytest.raises(HTTPException) as error:
        _validate_geometry(polygon([point, [79.4, 21.3], [79.4, 21.4], point]))
    assert "coordinates" in error.value.detail


def test_rejects_point_geometry():
    with pytest.raises(HTTPException) as error:
        _validate_geometry({"type": "Point", "coordinates": [79.3, 21.3]})
    assert "Polygon or MultiPolygon" in error.value.detail
