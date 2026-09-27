"""Nearby station search over the source-independent provider boundary."""

import math
from dataclasses import dataclass

from fuelroute.domain.models import FuelPrice, SourceMetadata, Station
from fuelroute.providers.base import Freshness, FuelPriceProvider
from fuelroute.services.geography import _validate_coordinates, haversine_km


@dataclass(frozen=True, slots=True)
class NearbySearchRequest:
    latitude: float
    longitude: float
    product_id: str
    radius_km: float
    limit: int | None = None


@dataclass(frozen=True, slots=True)
class NearbyStation:
    station: Station
    price: FuelPrice
    distance_km: float


@dataclass(frozen=True, slots=True)
class NearbySearchResult:
    items: tuple[NearbyStation, ...]
    source: SourceMetadata
    freshness: Freshness | None


def search_nearby(
    provider: FuelPriceProvider, request: NearbySearchRequest
) -> NearbySearchResult:
    """Filter by product and inclusive radius, then sort and optionally truncate."""
    _validate_coordinates(request.latitude, request.longitude)
    if not isinstance(request.product_id, str) or not request.product_id.strip():
        raise ValueError("product_id must be a non-empty string")
    if not math.isfinite(request.radius_km) or request.radius_km <= 0:
        raise ValueError("radius_km must be finite and positive")
    if request.limit is not None and (
        isinstance(request.limit, bool)
        or not isinstance(request.limit, int)
        or request.limit <= 0
    ):
        raise ValueError("limit must be a positive integer or None")

    batch = provider.get_stations()
    matches: list[NearbyStation] = []
    for station in batch.value.stations:
        price = next(
            (
                price
                for price in station.prices
                if price.product.id == request.product_id
            ),
            None,
        )
        if price is None:
            continue
        distance = haversine_km(
            request.latitude,
            request.longitude,
            station.latitude,
            station.longitude,
        )
        if distance <= request.radius_km:
            matches.append(NearbyStation(station, price, distance))
    matches.sort(key=lambda item: (item.distance_km, item.station.id))
    if request.limit is not None:
        matches = matches[: request.limit]
    return NearbySearchResult(tuple(matches), batch.value.source, batch.freshness)
