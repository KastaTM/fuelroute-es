"""Deterministic cache contract tests; no network or wall-clock waiting."""

from datetime import UTC, datetime, timedelta

import pytest

from fuelroute.domain.models import (
    FuelProduct,
    Municipality,
    Province,
    SourceMetadata,
    StationBatch,
)
from fuelroute.providers.base import (
    CacheState,
    ProviderHTTPError,
    ProviderInvalidJSONError,
    ProviderResult,
    ProviderSchemaError,
    ProviderSemanticError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from fuelroute.providers.cache import CachingFuelPriceProvider


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 26, tzinfo=UTC)

    def now(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.failure: Exception | None = None
        self.product = FuelProduct("1", "Gasolina")
        self.batch = StationBatch((), SourceMetadata(None, "unknown", None))

    def _call(self, *key: str) -> None:
        self.calls.append(key)
        if self.failure is not None:
            raise self.failure

    def get_products(self) -> ProviderResult[tuple[FuelProduct, ...]]:
        self._call("products")
        return ProviderResult((self.product,))

    def get_provinces(self) -> ProviderResult[tuple[Province, ...]]:
        self._call("provinces")
        return ProviderResult((Province("51", "Ceuta"),))

    def get_municipalities(
        self, province_id: str | None = None
    ) -> ProviderResult[tuple[Municipality, ...]]:
        self._call("municipalities", province_id or "all")
        return ProviderResult((Municipality(province_id or "0", "Town", province_id),))

    def get_stations(self) -> ProviderResult[StationBatch]:
        self._call("stations")
        return ProviderResult(self.batch)

    def get_stations_for_municipality_product(
        self, municipality_id: str, product: FuelProduct
    ) -> ProviderResult[StationBatch]:
        self._call("filtered", municipality_id, product.id, product.name)
        return ProviderResult(self.batch)


def test_miss_hit_boundary_refresh_and_timestamp() -> None:
    clock, upstream = Clock(), FakeProvider()
    cached = CachingFuelPriceProvider(upstream, now=clock.now)
    first = cached.get_products()
    assert first.freshness is not None
    assert first.freshness.state is CacheState.MISS
    fetched_at = first.freshness.fetched_at
    upstream.product = FuelProduct("2", "Diesel")
    clock.advance(600)
    hit = cached.get_products()
    assert hit.value == first.value
    assert hit.freshness is not None
    assert hit.freshness.state is CacheState.HIT
    assert hit.freshness.age == timedelta(minutes=10)
    assert hit.freshness.fetched_at == fetched_at
    assert upstream.calls == [("products",)]
    clock.advance(1)
    refreshed = cached.get_products()
    assert refreshed.value == (upstream.product,)
    assert refreshed.freshness is not None
    assert refreshed.freshness.state is CacheState.REFRESHED
    assert refreshed.freshness.age == timedelta(0)
    assert refreshed.freshness.fetched_at > fetched_at
    assert upstream.calls == [("products",), ("products",)]


def test_empty_result_and_all_operation_keys() -> None:
    clock, upstream = Clock(), FakeProvider()
    upstream.batch = StationBatch((), SourceMetadata(None, "source date", None))
    cached = CachingFuelPriceProvider(upstream, now=clock.now)
    assert cached.get_provinces().value == cached.get_provinces().value
    assert cached.get_municipalities().value != cached.get_municipalities("51").value
    cached.get_municipalities("02")
    product = upstream.product
    filtered = cached.get_stations_for_municipality_product("8110", product)
    assert filtered.value.stations == ()
    cached.get_stations_for_municipality_product("8110", product)
    cached.get_stations_for_municipality_product("9999", product)
    cached.get_stations_for_municipality_product(
        "8110", FuelProduct(product.id, "Renamed")
    )
    general = cached.get_stations()
    hit = cached.get_stations()
    assert general.freshness is not None
    assert general.freshness.state is CacheState.MISS
    assert hit.freshness is not None
    assert hit.freshness.state is CacheState.HIT
    assert hit.value.source.raw_reported_at == "source date"
    assert upstream.calls == [
        ("provinces",),
        ("municipalities", "all"),
        ("municipalities", "51"),
        ("municipalities", "02"),
        ("filtered", "8110", "1", "Gasolina"),
        ("filtered", "9999", "1", "Gasolina"),
        ("filtered", "8110", "1", "Renamed"),
        ("stations",),
    ]


@pytest.mark.parametrize(
    "error",
    [
        ProviderTimeoutError("products", "timeout"),
        ProviderUnavailableError("products", "offline"),
        ProviderHTTPError("products", 503),
        ProviderHTTPError("products", 408),
        ProviderHTTPError("products", 429),
    ],
)
def test_transient_error_returns_bounded_stale(error: Exception) -> None:
    clock, upstream = Clock(), FakeProvider()
    cached = CachingFuelPriceProvider(upstream, now=clock.now)
    first = cached.get_products()
    clock.advance(601)
    upstream.failure = error
    stale = cached.get_products()
    assert stale.value == first.value
    assert stale.freshness is not None
    assert first.freshness is not None
    assert stale.freshness.is_stale
    assert stale.freshness.age == timedelta(seconds=601)
    assert stale.freshness.fetched_at == first.freshness.fetched_at
    clock.advance(1)
    again = cached.get_products()
    assert again.freshness is not None
    assert again.freshness.is_stale
    assert len(upstream.calls) == 3


@pytest.mark.parametrize(
    "error",
    [
        ProviderHTTPError("products", 400),
        ProviderHTTPError("products", 404),
        ProviderInvalidJSONError("products", "invalid JSON"),
        ProviderSchemaError("products", "shape drift"),
        ProviderSemanticError("products", "failed query"),
        RuntimeError("bug"),
    ],
)
def test_non_transient_error_is_never_hidden(error: Exception) -> None:
    clock, upstream = Clock(), FakeProvider()
    cached = CachingFuelPriceProvider(upstream, now=clock.now)
    cached.get_products()
    clock.advance(601)
    upstream.failure = error
    with pytest.raises(type(error)) as captured:
        cached.get_products()
    assert captured.value is error


def test_max_stale_boundary_and_no_usable_entry() -> None:
    clock, upstream = Clock(), FakeProvider()
    cached = CachingFuelPriceProvider(upstream, now=clock.now)
    upstream.failure = ProviderTimeoutError("products", "timeout")
    with pytest.raises(ProviderTimeoutError) as captured:
        cached.get_products()
    assert captured.value is upstream.failure
    upstream.failure = None
    cached.get_products()
    upstream.failure = ProviderUnavailableError("products", "offline")
    clock.advance(1800)
    boundary = cached.get_products()
    assert boundary.freshness is not None
    assert boundary.freshness.state is CacheState.STALE
    clock.advance(1)
    with pytest.raises(ProviderUnavailableError) as unavailable:
        cached.get_products()
    assert unavailable.value is upstream.failure


def test_configuration_and_clock_validation() -> None:
    upstream = FakeProvider()
    with pytest.raises(ValueError, match="fresh_ttl"):
        CachingFuelPriceProvider(upstream, fresh_ttl=timedelta(0))
    with pytest.raises(ValueError, match="max_stale_age"):
        CachingFuelPriceProvider(
            upstream,
            fresh_ttl=timedelta(minutes=10),
            max_stale_age=timedelta(minutes=9),
        )
    cached = CachingFuelPriceProvider(upstream, now=lambda: datetime(2026, 9, 26))
    with pytest.raises(ValueError, match="timezone-aware"):
        cached.get_products()
    assert upstream.calls == []
