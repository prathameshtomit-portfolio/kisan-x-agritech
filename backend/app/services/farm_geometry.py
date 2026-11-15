"""Validation and approximate area calculation for farmer-drawn GeoJSON fields."""
from __future__ import annotations

import math
from typing import Any

EARTH_RADIUS_METERS = 6_371_008.8
MAX_POLYGONS = 100
MAX_RING_VERTICES = 1_000
MAX_TOTAL_VERTICES = 4_000


def _project_ring(ring: list[list[float]], origin_lon: float, mean_lat: float) -> list[tuple[float, float]]:
    cosine = math.cos(math.radians(mean_lat))
    projected = []
    for lon, lat in ring[:-1]:
        delta_lon = (lon - origin_lon + 180.0) % 360.0 - 180.0
        projected.append((math.radians(delta_lon) * cosine, math.radians(lat)))
    return projected


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
    epsilon = 1e-12
    return (abs(_orientation(a, b, p)) <= epsilon
            and min(a[0], b[0]) - epsilon <= p[0] <= max(a[0], b[0]) + epsilon
            and min(a[1], b[1]) - epsilon <= p[1] <= max(a[1], b[1]) + epsilon)


def _segments_intersect(a: tuple[float, float], b: tuple[float, float],
                        c: tuple[float, float], d: tuple[float, float]) -> bool:
    ab_c, ab_d = _orientation(a, b, c), _orientation(a, b, d)
    cd_a, cd_b = _orientation(c, d, a), _orientation(c, d, b)
    if ((ab_c > 0 > ab_d or ab_d > 0 > ab_c)
            and (cd_a > 0 > cd_b or cd_b > 0 > cd_a)):
        return True
    return (_on_segment(a, b, c) or _on_segment(a, b, d)
            or _on_segment(c, d, a) or _on_segment(c, d, b))


def _rings_intersect(first: list[tuple[float, float]], second: list[tuple[float, float]]) -> bool:
    for i, a in enumerate(first):
        b = first[(i + 1) % len(first)]
        for j, c in enumerate(second):
            d = second[(j + 1) % len(second)]
            if _segments_intersect(a, b, c, d):
                return True
    return False


def _ring_self_intersects(ring: list[tuple[float, float]]) -> bool:
    size = len(ring)
    for i in range(size):
        a, b = ring[i], ring[(i + 1) % size]
        for j in range(i + 1, size):
            if j == i + 1 or (i == 0 and j == size - 1):
                continue
            if _segments_intersect(a, b, ring[j], ring[(j + 1) % size]):
                return True
    return False


def _point_in_ring(point: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    previous = ring[-1]
    for current in ring:
        if _on_segment(previous, current, point):
            return False
        if (current[1] > y) != (previous[1] > y):
            crossing_x = (previous[0] - current[0]) * (y - current[1]) / (previous[1] - current[1]) + current[0]
            if x < crossing_x:
                inside = not inside
        previous = current
    return inside


def _ring_area_m2(ring: list[list[float]]) -> float:
    """Spherical ring area; suitable for farm-area estimates, not cadastral surveys."""
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(ring, ring[1:]):
        delta_lon = math.radians((lon2 - lon1 + 180.0) % 360.0 - 180.0)
        total += delta_lon * (2.0 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2)))
    return abs(total * EARTH_RADIUS_METERS * EARTH_RADIUS_METERS / 2.0)


def validate_and_measure_area_hectares(geometry: dict[str, Any]) -> float:
    """Validate a Polygon/MultiPolygon and return its spherical area in hectares."""
    if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Field boundary must be a GeoJSON Polygon or MultiPolygon.")
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list):
        raise ValueError("Field boundary coordinates must be an array.")
    polygons = [coordinates] if geometry["type"] == "Polygon" else coordinates
    if not polygons or len(polygons) > MAX_POLYGONS:
        raise ValueError(f"Field boundary must contain between 1 and {MAX_POLYGONS} polygons.")

    total_vertices = 0
    total_area = 0.0
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError("Each polygon must include an exterior ring.")
        rings: list[list[list[float]]] = []
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4:
                raise ValueError("Each boundary ring needs at least four coordinate pairs.")
            if len(ring) - 1 > MAX_RING_VERTICES:
                raise ValueError(f"Each boundary ring is limited to {MAX_RING_VERTICES} vertices.")
            total_vertices += len(ring) - 1
            if total_vertices > MAX_TOTAL_VERTICES:
                raise ValueError(f"Field boundary is limited to {MAX_TOTAL_VERTICES} vertices.")
            normalized: list[list[float]] = []
            for point in ring:
                if (not isinstance(point, (list, tuple)) or len(point) < 2
                        or not isinstance(point[0], (int, float)) or isinstance(point[0], bool)
                        or not isinstance(point[1], (int, float)) or isinstance(point[1], bool)):
                    raise ValueError("Boundary points must be finite longitude/latitude pairs in valid ranges.")
                try:
                    lon, lat = float(point[0]), float(point[1])
                except (OverflowError, ValueError) as exc:
                    raise ValueError("Boundary points must be finite longitude/latitude pairs in valid ranges.") from exc
                if not math.isfinite(lon) or not math.isfinite(lat) or not -180 <= lon <= 180 or not -90 <= lat <= 90:
                    raise ValueError("Boundary points must be finite longitude/latitude pairs in valid ranges.")
                normalized.append([lon, lat])
            if normalized[0] != normalized[-1]:
                raise ValueError("Each boundary ring must be closed (first and last coordinates must match).")
            if any(a == b for a, b in zip(normalized, normalized[1:])):
                raise ValueError("Boundary rings cannot contain duplicate consecutive points.")
            if _ring_area_m2(normalized) <= 0.01:
                raise ValueError("Field boundary must enclose a non-zero area.")
            rings.append(normalized)

        origin_lon = rings[0][0][0]
        mean_lat = sum(point[1] for point in rings[0][:-1]) / (len(rings[0]) - 1)
        projected = [_project_ring(ring, origin_lon, mean_lat) for ring in rings]
        for ring_points in projected:
            if _ring_self_intersects(ring_points):
                raise ValueError("Field boundary rings cannot cross or overlap themselves.")
        exterior = projected[0]
        area = _ring_area_m2(rings[0])
        for index, hole in enumerate(projected[1:], start=1):
            if not _point_in_ring(hole[0], exterior) or _rings_intersect(exterior, hole):
                raise ValueError("Each interior ring must lie fully inside the exterior boundary.")
            for prior_hole in projected[1:index]:
                if (_rings_intersect(prior_hole, hole)
                        or _point_in_ring(hole[0], prior_hole)
                        or _point_in_ring(prior_hole[0], hole)):
                    raise ValueError("Interior rings cannot overlap each other.")
            area -= _ring_area_m2(rings[index])
        if area <= 0:
            raise ValueError("Interior rings cannot remove the entire field boundary area.")
        total_area += area

    return total_area / 10_000.0
