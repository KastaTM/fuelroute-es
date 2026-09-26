"""Provider contract and errors independent of an upstream API or HTTP library."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from fuelroute.domain.models import (
    FuelProduct,
    Municipality,
    Province,
    StationBatch,
)


class CacheState(StrEnum):
    """How a caching provider produced this response."""

    MISS = "miss"
    HIT = "hit"
    REFRESHED = "refreshed"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class Freshness:
    """FuelRoute fetch time, separate from MITECO's reported source time."""

    fetched_at: datetime
    age: timedelta
    state: CacheState

    @property
    def is_stale(self) -> bool:
        return self.state is CacheState.STALE


@dataclass(frozen=True, slots=True)
class ProviderResult[T]:
    """Provider value and optional cache freshness metadata."""

    value: T
    freshness: Freshness | None = None


class FuelPriceProviderError(Exception):
    """Base for failures at the fuel data boundary."""

    def __init__(self, operation: str, message: str) -> None:
        self.operation = operation
        super().__init__(f"{operation}: {message}")


class ProviderUnavailableError(FuelPriceProviderError):
    """The upstream service could not be reached."""


class ProviderTimeoutError(ProviderUnavailableError):
    """The upstream request exceeded its configured timeout."""


class ProviderHTTPError(FuelPriceProviderError):
    """The upstream service returned an unsuccessful HTTP status."""

    def __init__(self, operation: str, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(operation, f"HTTP {status_code}")


class ProviderInvalidResponseError(FuelPriceProviderError):
    """An upstream response cannot be used as fuel data."""


class ProviderInvalidJSONError(ProviderInvalidResponseError):
    """The HTTP response is not syntactically valid JSON."""


class ProviderSchemaError(ProviderInvalidResponseError):
    """JSON has an incompatible shape or malformed value."""


class ProviderSemanticError(ProviderInvalidResponseError):
    """The upstream response explicitly reports a failed query."""


class FuelPriceProvider(Protocol):
    """Operations needed by the current fuel data boundary."""

    def get_products(self) -> ProviderResult[tuple[FuelProduct, ...]]: ...

    def get_provinces(self) -> ProviderResult[tuple[Province, ...]]: ...

    def get_municipalities(
        self, province_id: str | None = None
    ) -> ProviderResult[tuple[Municipality, ...]]: ...

    def get_stations(self) -> ProviderResult[StationBatch]: ...

    def get_stations_for_municipality_product(
        self, municipality_id: str, product: FuelProduct
    ) -> ProviderResult[StationBatch]: ...
