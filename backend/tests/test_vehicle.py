"""Vehicle construction contracts independent of providers."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from fuelroute.domain.models import Vehicle


def vehicle(**changes: object) -> Vehicle:
    fields: dict[str, object] = {
        "id": "car-1",
        "nickname": "Mi coche",
        "fuel_product_id": "01",
        "average_consumption_l_100km": Decimal("6.5"),
    }
    fields.update(changes)
    return Vehicle(**fields)  # type: ignore[arg-type]


def test_valid_vehicle_preserves_textual_fuel_and_optional_fields() -> None:
    car = vehicle()
    assert car.id == "car-1"
    assert car.fuel_product_id == "01"
    assert isinstance(car.fuel_product_id, str)
    assert car.make is None
    assert car.model is None
    assert car.year is None
    assert car.tank_capacity_l is None
    assert car.is_active is False
    full = vehicle(
        make="Seat",
        model="Ibiza",
        year=2020,
        tank_capacity_l=Decimal("45"),
        is_active=True,
    )
    assert full.tank_capacity_l == Decimal("45")
    assert full.is_active is True
    with pytest.raises(FrozenInstanceError):
        car.nickname = "Other"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", ""),
        ("id", "  "),
        ("id", 1),
        ("nickname", ""),
        ("nickname", "   "),
        ("fuel_product_id", ""),
        ("fuel_product_id", "  "),
        ("fuel_product_id", 1),
    ],
)
def test_required_text_must_be_nonempty_string(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        vehicle(**{field: value})


@pytest.mark.parametrize(
    "consumption",
    [
        Decimal("0"),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        6.5,
    ],
)
def test_invalid_consumption_rejected(consumption: object) -> None:
    with pytest.raises(ValueError, match="average_consumption_l_100km"):
        vehicle(average_consumption_l_100km=consumption)


@pytest.mark.parametrize(
    "capacity",
    [
        Decimal("0"),
        Decimal("-1"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        45,
    ],
)
def test_invalid_tank_capacity_rejected(capacity: object) -> None:
    with pytest.raises(ValueError, match="tank_capacity_l"):
        vehicle(tank_capacity_l=capacity)
