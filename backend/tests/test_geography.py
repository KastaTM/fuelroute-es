"""Deterministic checks for spherical straight-line distance."""

import math

import pytest

from fuelroute.services.geography import EARTH_RADIUS_KM, haversine_km


def test_same_coordinate_is_zero() -> None:
    assert haversine_km(40.4, -3.7, 40.4, -3.7) == 0


def test_one_equatorial_degree_matches_independent_arc_length() -> None:
    # One degree is pi/180 radians; using the documented radius gives ~111.19508 km.
    assert EARTH_RADIUS_KM == 6371.0088
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.19508, abs=0.00001)


def test_symmetry_and_negative_longitudes() -> None:
    westward = haversine_km(0, -5, 0, -4)
    assert westward == pytest.approx(111.19508, abs=0.00001)
    assert westward == haversine_km(0, -4, 0, -5)
    assert haversine_km(40.4, -3.7, 41.4, -4.7) == pytest.approx(
        haversine_km(41.4, -4.7, 40.4, -3.7)
    )


@pytest.mark.parametrize(
    "coordinates",
    [(91, 0, 0, 0), (0, -181, 0, 0), (0, 0, math.nan, 0)],
)
def test_invalid_coordinates_are_rejected(
    coordinates: tuple[float, float, float, float],
) -> None:
    with pytest.raises(ValueError):
        haversine_km(*coordinates)
