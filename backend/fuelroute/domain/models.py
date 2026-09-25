"""Source-independent values consumed by later FuelRoute features."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class FuelProduct:
    id: str
    name: str
    abbreviation: str | None = None


@dataclass(frozen=True, slots=True)
class FuelPrice:
    product: FuelProduct
    price_eur_l: Decimal


@dataclass(frozen=True, slots=True)
class Province:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class Municipality:
    id: str
    name: str
    province_id: str | None


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    reported_at: datetime | None
    raw_reported_at: str | None
    note: str | None


@dataclass(frozen=True, slots=True)
class Station:
    id: str
    brand: str | None
    address: str | None
    locality: str | None
    municipality: str | None
    province: str | None
    municipality_id: str | None
    province_id: str | None
    postal_code: str | None
    latitude: float
    longitude: float
    schedule: str | None
    prices: tuple[FuelPrice, ...]


@dataclass(frozen=True, slots=True)
class StationBatch:
    stations: tuple[Station, ...]
    source: SourceMetadata
