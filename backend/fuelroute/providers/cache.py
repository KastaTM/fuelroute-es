"""In-memory TTL decorator for the source-independent provider boundary."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import TypeVar, cast

from fuelroute.domain.models import FuelProduct, Municipality, Province, StationBatch
from fuelroute.providers.base import (
    CacheState,
    Freshness,
    FuelPriceProvider,
    ProviderHTTPError,
    ProviderResult,
    ProviderUnavailableError,
)

DEFAULT_FRESH_TTL = timedelta(minutes=10)
DEFAULT_MAX_STALE_AGE = timedelta(minutes=30)
T = TypeVar("T")
CacheKey = tuple[str | None, ...]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class _Entry:
    value: object
    fetched_at: datetime


class CachingFuelPriceProvider:
    """Cache immutable provider values; try expired refresh before stale fallback.

    Concurrent misses may duplicate upstream work. The lock protects only the
    dictionary, never the provider call.
    """

    def __init__(
        self,
        provider: FuelPriceProvider,
        *,
        fresh_ttl: timedelta = DEFAULT_FRESH_TTL,
        max_stale_age: timedelta = DEFAULT_MAX_STALE_AGE,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        if fresh_ttl <= timedelta(0):
            raise ValueError("fresh_ttl must be positive")
        if max_stale_age < fresh_ttl:
            raise ValueError("max_stale_age must be at least fresh_ttl")
        self._provider = provider
        self._fresh_ttl = fresh_ttl
        self._max_stale_age = max_stale_age
        self._now = now
        self._entries: dict[CacheKey, _Entry] = {}
        self._lock = Lock()

    def _time(self) -> datetime:
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("cache clock must return a timezone-aware datetime")
        return now.astimezone(UTC)

    @staticmethod
    def _age(entry: _Entry, now: datetime) -> timedelta:
        return max(timedelta(0), now - entry.fetched_at)

    @staticmethod
    def _result(entry: _Entry, age: timedelta, state: CacheState) -> ProviderResult[T]:
        return ProviderResult(
            cast(T, entry.value),
            Freshness(entry.fetched_at, age, state),
        )

    @staticmethod
    def _can_fallback(error: ProviderUnavailableError | ProviderHTTPError) -> bool:
        if isinstance(error, ProviderUnavailableError):
            return True
        return error.status_code in (408, 429) or 500 <= error.status_code <= 599

    def _get(
        self, key: CacheKey, fetch: Callable[[], ProviderResult[T]]
    ) -> ProviderResult[T]:
        now = self._time()
        with self._lock:
            entry = self._entries.get(key)
        if entry is not None:
            age = self._age(entry, now)
            if age <= self._fresh_ttl:
                return self._result(entry, age, CacheState.HIT)
        try:
            fetched = fetch()
        except (ProviderUnavailableError, ProviderHTTPError) as error:
            if entry is None or not self._can_fallback(error):
                raise
            age = self._age(entry, self._time())
            if age > self._max_stale_age:
                raise
            return self._result(entry, age, CacheState.STALE)
        replacement = _Entry(fetched.value, self._time())
        with self._lock:
            self._entries[key] = replacement
        state = CacheState.MISS if entry is None else CacheState.REFRESHED
        return self._result(replacement, timedelta(0), state)

    def get_products(self) -> ProviderResult[tuple[FuelProduct, ...]]:
        return self._get(("products",), self._provider.get_products)

    def get_provinces(self) -> ProviderResult[tuple[Province, ...]]:
        return self._get(("provinces",), self._provider.get_provinces)

    def get_municipalities(
        self, province_id: str | None = None
    ) -> ProviderResult[tuple[Municipality, ...]]:
        key = (
            ("municipalities_all",)
            if province_id is None
            else ("municipalities_province", province_id)
        )
        return self._get(key, lambda: self._provider.get_municipalities(province_id))

    def get_stations(self) -> ProviderResult[StationBatch]:
        return self._get(("stations",), self._provider.get_stations)

    def get_stations_for_municipality_product(
        self, municipality_id: str, product: FuelProduct
    ) -> ProviderResult[StationBatch]:
        key = (
            "stations_municipality_product",
            municipality_id,
            product.id,
            product.name,
            product.abbreviation,
        )
        return self._get(
            key,
            lambda: self._provider.get_stations_for_municipality_product(
                municipality_id, product
            ),
        )
