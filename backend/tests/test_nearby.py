"""Offline nearby-search contract tests using small normalized stations."""

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from fuelroute.domain.models import (
    FuelPrice,
    FuelProduct,
    Municipality,
    Province,
    SourceMetadata,
    Station,
    StationBatch,
)
from fuelroute.providers.base import (
    CacheState,
    Freshness,
    ProviderResult,
    ProviderTimeoutError,
)
from fuelroute.services.geography import EARTH_RADIUS_KM
from fuelroute.services.nearby import NearbySearchRequest, search_nearby

ONE = FuelProduct("1", "First product")
ZERO_ONE = FuelProduct("01", "Leading-zero product")
TWO = FuelProduct("2", "Second product")
SOURCE = SourceMetadata(None, "source timestamp", None)
FRESHNESS = Freshness(
    datetime(2026, 9, 27, tzinfo=UTC), timedelta(minutes=3), CacheState.HIT
)


def station(
    station_id: str,
    longitude: float,
    *prices: FuelPrice,
    latitude: float = 0,
) -> Station:
    return Station(
        id=station_id,
        brand=None,
        address=None,
        locality=None,
        municipality=None,
        province=None,
        municipality_id=None,
        province_id=None,
        postal_code=None,
        latitude=latitude,
        longitude=longitude,
        schedule=None,
        prices=prices,
    )


class FakeProvider:
    def __init__(self, stations: tuple[Station, ...]) -> None:
        self.batch = StationBatch(stations, SOURCE)
        self.calls = 0

    def get_stations(self) -> ProviderResult[StationBatch]:
        self.calls += 1
        return ProviderResult(self.batch, FRESHNESS)

    def get_products(self) -> ProviderResult[tuple[FuelProduct, ...]]:
        raise AssertionError("unexpected provider operation")

    def get_provinces(self) -> ProviderResult[tuple[Province, ...]]:
        raise AssertionError("unexpected provider operation")

    def get_municipalities(
        self, province_id: str | None = None
    ) -> ProviderResult[tuple[Municipality, ...]]:
        raise AssertionError("unexpected provider operation")

    def get_stations_for_municipality_product(
        self, municipality_id: str, product: FuelProduct
    ) -> ProviderResult[StationBatch]:
        raise AssertionError("unexpected provider operation")


def request(
    *, product_id: str = "1", radius_km: float = 300, limit: int | None = None
) -> NearbySearchRequest:
    return NearbySearchRequest(0, 0, product_id, radius_km, limit)


def test_inside_outside_and_exact_inclusive_boundary() -> None:
    price = FuelPrice(ONE, Decimal("1.5"))
    # Equatorial one-degree arc: radius * pi/180, independent of haversine_km().
    boundary_km = EARTH_RADIUS_KM * math.pi / 180
    provider = FakeProvider(
        (
            station("outside", 2, price),
            station("boundary", 1, price),
            station("inside", 0.5, price),
        )
    )
    result = search_nearby(provider, request(radius_km=boundary_km))
    assert [item.station.id for item in result.items] == ["inside", "boundary"]
    assert result.items[1].distance_km <= boundary_km
    assert provider.calls == 1


def test_selects_only_requested_price_and_preserves_textual_id() -> None:
    first = FuelPrice(ONE, Decimal("1.1"))
    selected = FuelPrice(ZERO_ONE, Decimal("1.2"))
    second = FuelPrice(TWO, Decimal("1.3"))
    provider = FakeProvider((station("multi", -1, first, selected, second),))
    result = search_nearby(provider, request(product_id="01"))
    assert len(result.items) == 1
    assert result.items[0].price is selected
    assert result.items[0].station is provider.batch.stations[0]
    assert search_nearby(provider, request(product_id="1")).items[0].price is first
    assert search_nearby(provider, request(product_id="2")).items[0].price is second


def test_missing_product_and_no_candidates_return_empty_success() -> None:
    provider = FakeProvider((station("a", 0, FuelPrice(TWO, Decimal("1"))),))
    result = search_nearby(provider, request(radius_km=1))
    assert result.items == ()
    assert result.source is SOURCE
    assert result.freshness is FRESHNESS
    assert search_nearby(FakeProvider(()), request()).items == ()


def test_distance_order_tie_break_and_limit_after_sort() -> None:
    price = FuelPrice(ONE, Decimal("1.5"))
    provider = FakeProvider(
        (
            station("far", 2, price),
            station("z", -1, price),
            station("a", 1, price),
            station("nearest", 0.25, price),
        )
    )
    all_items = search_nearby(provider, request()).items
    assert [item.station.id for item in all_items] == ["nearest", "a", "z", "far"]
    assert all_items[1].distance_km == all_items[2].distance_km
    limited = search_nearby(provider, request(limit=2))
    assert [item.station.id for item in limited.items] == ["nearest", "a"]


def test_negative_western_coordinates_and_input_immutability() -> None:
    price = FuelPrice(ONE, Decimal("1.5"))
    western = station("west", -5.3, price, latitude=35.9)
    provider = FakeProvider((western,))
    original_batch = provider.batch
    result = search_nearby(provider, NearbySearchRequest(35.9, -5.4, "1", 20, None))
    assert len(result.items) == 1
    assert 0 < result.items[0].distance_km < 20
    assert result.items[0].station is western
    assert result.items[0].price is price
    assert provider.batch is original_batch
    assert western.prices == (price,)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_limit_rejected_before_provider_call(limit: int | float) -> None:
    provider = FakeProvider(())
    with pytest.raises(ValueError, match="limit"):
        search_nearby(provider, request(limit=limit))  # type: ignore[arg-type]
    assert provider.calls == 0


@pytest.mark.parametrize(
    "bad_request",
    [
        NearbySearchRequest(91, 0, "1", 1),
        NearbySearchRequest(0, -181, "1", 1),
        NearbySearchRequest(0, 0, "", 1),
        NearbySearchRequest(0, 0, "   ", 1),
        NearbySearchRequest(0, 0, "1", -1),
        NearbySearchRequest(0, 0, "1", 0),
        NearbySearchRequest(0, 0, "1", math.inf),
    ],
)
def test_invalid_request_rejected_before_provider_call(
    bad_request: NearbySearchRequest,
) -> None:
    provider = FakeProvider(())
    with pytest.raises(ValueError):
        search_nearby(provider, bad_request)
    assert provider.calls == 0


def test_provider_error_propagates_unchanged() -> None:
    error = ProviderTimeoutError("stations", "offline")

    class FailingProvider(FakeProvider):
        def get_stations(self) -> ProviderResult[StationBatch]:
            raise error

    with pytest.raises(ProviderTimeoutError) as captured:
        search_nearby(FailingProvider(()), request())
    assert captured.value is error
