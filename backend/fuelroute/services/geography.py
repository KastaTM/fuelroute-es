"""Pure geographic calculations using a spherical Earth approximation."""

import math

EARTH_RADIUS_KM = 6371.0088  # IUGG mean Earth radius, in kilometers.


def _validate_coordinates(latitude: float, longitude: float) -> None:
    if not math.isfinite(latitude) or not -90 <= latitude <= 90:
        raise ValueError("latitude must be finite and between -90 and 90 degrees")
    if not math.isfinite(longitude) or not -180 <= longitude <= 180:
        raise ValueError("longitude must be finite and between -180 and 180 degrees")


def haversine_km(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return great-circle distance in km for finite, in-range degree coordinates.

    Uses the IUGG mean Earth radius of 6371.0088 km; this is a straight-line
    spherical approximation, not a road distance. Results are not rounded.
    """
    _validate_coordinates(latitude_a, longitude_a)
    _validate_coordinates(latitude_b, longitude_b)
    lat_a, lon_a, lat_b, lon_b = map(
        math.radians, (latitude_a, longitude_a, latitude_b, longitude_b)
    )
    delta_lat = lat_b - lat_a
    delta_lon = lon_b - lon_a
    arc = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, max(0.0, arc))))
