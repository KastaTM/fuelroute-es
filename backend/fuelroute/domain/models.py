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
class Vehicle:
    id: str
    nickname: str
    fuel_product_id: str
    average_consumption_l_100km: Decimal
    make: str | None = None
    model: str | None = None
    year: int | None = None
    tank_capacity_l: Decimal | None = None
    is_active: bool = False

    def __post_init__(self) -> None:
        for field_name in ("id", "nickname", "fuel_product_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        for field_name in ("average_consumption_l_100km", "tank_capacity_l"):
            value = getattr(self, field_name)
            if value is None and field_name == "tank_capacity_l":
                continue
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise ValueError(f"{field_name} must be a finite positive Decimal")


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
    unmapped_fuel_field_count: int = 0


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
