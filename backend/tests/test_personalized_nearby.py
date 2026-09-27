"""Offline contract tests for post-geography personalization and ranking."""

import math
from dataclasses import FrozenInstanceError, replace
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
)
from fuelroute.services.economics import Reachability
from fuelroute.services.nearby import (
    NearbySearchRequest,
    NearbySearchResult,
    NearbyStation,
    search_nearby,
)
from fuelroute.services.personalized_nearby import (
    PersonalizedNearbyRequest,
    PersonalizedNearbyResult,
    PersonalizedSortBy,
    personalize_nearby,
)

PRODUCT = FuelProduct("01", "Selected fuel")
OTHER = FuelProduct("2", "Other fuel")
SOURCE = SourceMetadata(None, "observed", None)
FRESHNESS = Freshness(
    datetime(2026, 9, 27, tzinfo=UTC), timedelta(minutes=2), CacheState.HIT
)


def station(station_id: str, price: Decimal, *, longitude: float = 0) -> Station:
    return Station(
        station_id,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        0,
        longitude,
        None,
        (FuelPrice(PRODUCT, price),),
    )


def nearby(*specs: tuple[str, float, str]) -> NearbySearchResult:
    return NearbySearchResult(
        tuple(
            NearbyStation(
                item := station(station_id, Decimal(price)),
                item.prices[0],
                distance,
            )
            for station_id, distance, price in specs
        ),
        SOURCE,
        FRESHNESS,
    )


def ids(result: NearbySearchResult | PersonalizedNearbyResult) -> list[str]:
    return [item.station.id for item in result.items]


def test_unknown_autonomy_and_missing_economic_inputs_preserve_metadata() -> None:
    original = nearby(("a", 10, "1.50"), ("b", 20, "1.40"))
    ranked = personalize_nearby(original, PersonalizedNearbyRequest())
    assert ids(ranked) == ["a", "b"]
    assert ranked.source is SOURCE
    assert ranked.freshness is FRESHNESS
    assert ranked.items[0].station is original.items[0].station
    assert ranked.items[0].price is original.items[0].price
    assert ranked.items[0].price.price_eur_l == Decimal("1.50")
    for item in ranked.items:
        assert item.reachability_status is Reachability.UNKNOWN
        assert item.usable_autonomy_km is None
        assert item.estimated_refuel_cost is None
        assert item.estimated_travel_liters is None
        assert item.estimated_travel_cost is None
        assert item.estimated_effective_cost is None
    with pytest.raises(FrozenInstanceError):
        ranked.items[0].distance_km = 1  # type: ignore[misc]


def test_reachability_boundary_and_not_reachable_station_remains() -> None:
    original = nearby(("inside", 20, "1.50"), ("edge", 32, "1.50"), ("far", 33, "1.50"))
    ranked = personalize_nearby(original, PersonalizedNearbyRequest(autonomy_km=40))
    assert ids(ranked) == ["inside", "edge", "far"]
    assert [item.usable_autonomy_km for item in ranked.items] == [32, 32, 32]
    assert [item.reachability_status for item in ranked.items] == [
        Reachability.POSSIBLY_REACHABLE,
        Reachability.POSSIBLY_REACHABLE,
        Reachability.NOT_REACHABLE,
    ]


def test_custom_safety_reserve_is_applied() -> None:
    ranked = personalize_nearby(
        nearby(("edge", 30, "1.50"), ("beyond", 31, "1.50")),
        PersonalizedNearbyRequest(autonomy_km=40, safety_reserve_percent=25),
    )
    assert [item.usable_autonomy_km for item in ranked.items] == [30, 30]
    assert [item.reachability_status for item in ranked.items] == [
        Reachability.POSSIBLY_REACHABLE,
        Reachability.NOT_REACHABLE,
    ]


def test_all_costs_use_candidate_price_without_rounding() -> None:
    ranked = personalize_nearby(
        nearby(("a", 10, "1.50")),
        PersonalizedNearbyRequest(
            average_consumption_l_100km=Decimal("6"),
            liters_to_refuel=Decimal("40"),
        ),
    )
    item = ranked.items[0]
    assert item.estimated_travel_liters == Decimal("0.6")
    assert item.estimated_refuel_cost == Decimal("60.00")
    assert item.estimated_travel_cost == Decimal("0.900")
    assert item.estimated_effective_cost == Decimal("60.900")
    assert item.price.price_eur_l == Decimal("1.50")


def test_optional_costs_are_never_invented() -> None:
    original = nearby(("a", 10, "1.50"))
    liters_only = personalize_nearby(
        original, PersonalizedNearbyRequest(liters_to_refuel=Decimal("40"))
    ).items[0]
    assert liters_only.estimated_refuel_cost == Decimal("60.00")
    assert liters_only.estimated_travel_liters is None
    assert liters_only.estimated_travel_cost is None
    assert liters_only.estimated_effective_cost is None

    consumption_only = personalize_nearby(
        original,
        PersonalizedNearbyRequest(average_consumption_l_100km=Decimal("6")),
    ).items[0]
    assert consumption_only.estimated_refuel_cost is None
    assert consumption_only.estimated_travel_liters == Decimal("0.6")
    assert consumption_only.estimated_travel_cost == Decimal("0.900")
    assert consumption_only.estimated_effective_cost is None


def test_precision_uses_decimal_string_distance_and_candidate_price() -> None:
    item = personalize_nearby(
        nearby(("a", 0.1, "1.234")),
        PersonalizedNearbyRequest(
            average_consumption_l_100km=Decimal("1"),
            liters_to_refuel=Decimal("0.123"),
        ),
    ).items[0]
    assert item.estimated_travel_liters == Decimal("0.001")
    assert item.estimated_refuel_cost == Decimal("0.151782")
    assert item.estimated_travel_cost == Decimal("0.001234")
    assert item.estimated_effective_cost == Decimal("0.153016")


def test_distance_sort_matches_phase2_distance_then_station_id() -> None:
    ranked = personalize_nearby(
        nearby(
            ("far", 10, "1.00"),
            ("z", 5, "1.20"),
            ("a", 5, "1.30"),
            ("near", 1, "2.00"),
        ),
        PersonalizedNearbyRequest(),
    )
    assert ids(ranked) == ["near", "a", "z", "far"]


def test_price_sort_uses_distance_then_id_ties() -> None:
    ranked = personalize_nearby(
        nearby(
            ("near-expensive", 1, "2.00"),
            ("z", 10, "1.00"),
            ("a", 10, "1.00"),
            ("closer", 5, "1.00"),
        ),
        PersonalizedNearbyRequest(sort_by=PersonalizedSortBy.PRICE),
    )
    assert ids(ranked) == ["closer", "a", "z", "near-expensive"]


def test_effective_cost_can_reverse_price_order() -> None:
    ranked = personalize_nearby(
        nearby(
            ("expensive-near", 1, "1.50"),
            ("cheap-far", 100, "1.40"),
            ("best", 20, "1.45"),
        ),
        PersonalizedNearbyRequest(
            average_consumption_l_100km=Decimal("6"),
            liters_to_refuel=Decimal("40"),
            sort_by=PersonalizedSortBy.EFFECTIVE_COST,
        ),
    )
    assert ids(ranked) == ["best", "expensive-near", "cheap-far"]
    assert [item.estimated_effective_cost for item in ranked.items] == [
        Decimal("59.74"),
        Decimal("60.090"),
        Decimal("64.40"),
    ]


def test_effective_cost_ties_use_distance_then_id() -> None:
    ranked = personalize_nearby(
        nearby(("z", 1, "1"), ("a", 1, "1"), ("nearest", 0, "2")),
        PersonalizedNearbyRequest(
            average_consumption_l_100km=Decimal("100"),
            liters_to_refuel=Decimal("1"),
            sort_by=PersonalizedSortBy.EFFECTIVE_COST,
        ),
    )
    assert [item.estimated_effective_cost for item in ranked.items] == [
        Decimal("2"),
        Decimal("2"),
        Decimal("2"),
    ]
    assert ids(ranked) == ["nearest", "a", "z"]


@pytest.mark.parametrize(
    ("liters", "consumption"),
    [
        (None, None),
        (None, Decimal("6")),
        (Decimal("40"), None),
    ],
)
def test_effective_sort_rejects_missing_inputs_even_with_no_candidates(
    liters: Decimal | None, consumption: Decimal | None
) -> None:
    with pytest.raises(ValueError, match="effective_cost sort requires"):
        request = PersonalizedNearbyRequest(
            liters_to_refuel=liters,
            average_consumption_l_100km=consumption,
            sort_by=PersonalizedSortBy.EFFECTIVE_COST,
        )
        personalize_nearby(nearby(), request)


def test_limit_is_applied_after_price_and_effective_sort() -> None:
    original = nearby(
        ("A-near-expensive", 1, "1.50"),
        ("B-far-cheap", 20, "1.40"),
        ("C-middle", 30, "1.45"),
    )
    by_price = personalize_nearby(
        original, PersonalizedNearbyRequest(sort_by=PersonalizedSortBy.PRICE, limit=1)
    )
    by_effective = personalize_nearby(
        original,
        PersonalizedNearbyRequest(
            average_consumption_l_100km=Decimal("6"),
            liters_to_refuel=Decimal("40"),
            sort_by=PersonalizedSortBy.EFFECTIVE_COST,
            limit=1,
        ),
    )
    assert ids(by_price) == ["B-far-cheap"]
    assert ids(by_effective) == ["B-far-cheap"]
    assert by_effective.items[0].estimated_effective_cost == Decimal("57.68")
    assert len(original.items) == 3


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("average_consumption_l_100km", Decimal("0")),
        ("average_consumption_l_100km", Decimal("-1")),
        ("average_consumption_l_100km", Decimal("NaN")),
        ("average_consumption_l_100km", Decimal("Infinity")),
        ("average_consumption_l_100km", 6),
        ("liters_to_refuel", Decimal("0")),
        ("liters_to_refuel", Decimal("-1")),
        ("liters_to_refuel", Decimal("NaN")),
        ("liters_to_refuel", Decimal("Infinity")),
        ("liters_to_refuel", 40),
    ],
)
def test_invalid_optional_decimal_rejected(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        PersonalizedNearbyRequest(**{field: value})  # type: ignore[arg-type]


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_limit_rejected(limit: object) -> None:
    with pytest.raises(ValueError, match="limit"):
        PersonalizedNearbyRequest(limit=limit)  # type: ignore[arg-type]


@pytest.mark.parametrize("reserve", [-1, 100, math.nan, math.inf])
def test_invalid_reserve_rejected_even_without_autonomy(reserve: float) -> None:
    with pytest.raises(ValueError, match="safety_reserve_percent"):
        PersonalizedNearbyRequest(safety_reserve_percent=reserve)


def test_invalid_autonomy_and_sort_rejected() -> None:
    with pytest.raises(ValueError, match="autonomy_km"):
        PersonalizedNearbyRequest(autonomy_km=math.nan)
    with pytest.raises(ValueError, match="sort_by"):
        PersonalizedNearbyRequest(sort_by="price")  # type: ignore[arg-type]


class FakeProvider:
    def __init__(self, stations: tuple[Station, ...]) -> None:
        self.stations = stations
        self.calls = 0

    def get_stations(self) -> ProviderResult[StationBatch]:
        self.calls += 1
        return ProviderResult(StationBatch(self.stations, SOURCE), FRESHNESS)

    def get_products(self) -> ProviderResult[tuple[FuelProduct, ...]]:
        raise AssertionError("unexpected provider call")

    def get_provinces(self) -> ProviderResult[tuple[Province, ...]]:
        raise AssertionError("unexpected provider call")

    def get_municipalities(
        self, province_id: str | None = None
    ) -> ProviderResult[tuple[Municipality, ...]]:
        raise AssertionError("unexpected provider call")

    def get_stations_for_municipality_product(
        self, municipality_id: str, product: FuelProduct
    ) -> ProviderResult[StationBatch]:
        raise AssertionError("unexpected provider call")


def test_geographic_search_then_personalization_keeps_radius_and_fuel_filter() -> None:
    close_expensive = station("close", Decimal("2.00"), longitude=0.01)
    far_cheap = station("cheap", Decimal("1.00"), longitude=0.03)
    outside = station("outside", Decimal("0.50"), longitude=1)
    wrong_fuel = station("wrong", Decimal("0.10"), longitude=0.001)
    wrong_fuel = replace(wrong_fuel, prices=(FuelPrice(OTHER, Decimal("0.10")),))
    provider = FakeProvider((close_expensive, far_cheap, outside, wrong_fuel))
    geographic = search_nearby(provider, NearbySearchRequest(0, 0, "01", 10, None))
    assert ids(geographic) == ["close", "cheap"]
    assert provider.calls == 1
    ranked = personalize_nearby(
        geographic,
        PersonalizedNearbyRequest(sort_by=PersonalizedSortBy.PRICE, limit=1),
    )
    assert ids(ranked) == ["cheap"]
    assert ranked.source is SOURCE
    assert ranked.freshness is FRESHNESS
    assert ranked.items[0].price.product.id == "01"
    assert provider.calls == 1
