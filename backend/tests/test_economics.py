"""Offline tests for autonomy and economic calculations."""

import math
from decimal import Decimal

import pytest

from fuelroute.services.economics import (
    DEFAULT_SAFETY_RESERVE_PERCENT,
    Reachability,
    classify_reachability,
    estimated_effective_cost,
    estimated_travel_cost,
    refuel_cost,
    travel_liters,
    usable_autonomy_km,
)


def test_usable_autonomy_examples_without_rounding() -> None:
    assert DEFAULT_SAFETY_RESERVE_PERCENT == 20.0
    assert usable_autonomy_km(40) == 32
    assert usable_autonomy_km(40, 0) == 40
    assert usable_autonomy_km(40, 25) == 30
    assert usable_autonomy_km(41, 20) == pytest.approx(32.8)


@pytest.mark.parametrize("reserve", [-1, 100, math.nan, math.inf, -math.inf])
def test_invalid_reserve_rejected(reserve: float) -> None:
    with pytest.raises(ValueError, match="safety_reserve_percent"):
        usable_autonomy_km(40, reserve)


@pytest.mark.parametrize("autonomy", [0, -1, math.nan, math.inf, -math.inf])
def test_invalid_autonomy_rejected(autonomy: float) -> None:
    with pytest.raises(ValueError, match="autonomy_km"):
        usable_autonomy_km(autonomy)


def test_reachability_unknown_and_inclusive_boundary() -> None:
    assert classify_reachability(5, None) is Reachability.UNKNOWN
    assert classify_reachability(31, 40) is Reachability.POSSIBLY_REACHABLE
    assert classify_reachability(32, 40) is Reachability.POSSIBLY_REACHABLE
    assert (
        classify_reachability(math.nextafter(32, math.inf), 40)
        is Reachability.NOT_REACHABLE
    )
    assert classify_reachability(33, 40) is Reachability.NOT_REACHABLE
    assert classify_reachability(30, 40, 25) is Reachability.POSSIBLY_REACHABLE


@pytest.mark.parametrize("distance", [-1, math.nan, math.inf, -math.inf])
def test_invalid_distance_rejected_even_without_autonomy(distance: float) -> None:
    with pytest.raises(ValueError, match="distance_km"):
        classify_reachability(distance, None)
    with pytest.raises(ValueError, match="distance_km"):
        travel_liters(distance, Decimal("6"))


def test_cost_examples_and_zero_distance() -> None:
    assert refuel_cost(Decimal("40"), Decimal("1.50")) == Decimal("60.00")
    assert travel_liters(10, Decimal("6")) == Decimal("0.6")
    assert estimated_travel_cost(10, Decimal("6"), Decimal("1.50")) == Decimal("0.900")
    assert estimated_effective_cost(Decimal("60.00"), Decimal("0.900")) == Decimal(
        "60.900"
    )
    assert travel_liters(0, Decimal("6")) == Decimal("0")
    assert estimated_travel_cost(0, Decimal("6"), Decimal("1.50")) == Decimal("0.000")


def test_decimal_precision_and_no_premature_rounding() -> None:
    assert refuel_cost(Decimal("0.123"), Decimal("1.234")) == Decimal("0.151782")
    assert travel_liters(0.1, Decimal("1")) == Decimal("0.001")
    assert estimated_travel_cost(0.1, Decimal("1"), Decimal("1.234")) == Decimal(
        "0.001234"
    )
    assert estimated_effective_cost(
        Decimal("0.151782"), Decimal("0.001234")
    ) == Decimal("0.153016")


@pytest.mark.parametrize(
    ("liters", "price"),
    [
        (Decimal("0"), Decimal("1")),
        (Decimal("-1"), Decimal("1")),
        (Decimal("NaN"), Decimal("1")),
        (Decimal("Infinity"), Decimal("1")),
        (Decimal("1"), Decimal("0")),
        (Decimal("1"), Decimal("-1")),
        (Decimal("1"), Decimal("NaN")),
        (Decimal("1"), Decimal("Infinity")),
    ],
)
def test_refuel_cost_rejects_invalid_components(
    liters: Decimal, price: Decimal
) -> None:
    with pytest.raises(ValueError):
        refuel_cost(liters, price)


@pytest.mark.parametrize(
    "consumption",
    [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")],
)
def test_travel_liters_rejects_invalid_consumption(consumption: Decimal) -> None:
    with pytest.raises(ValueError, match="consumption_l_100km"):
        travel_liters(10, consumption)


@pytest.mark.parametrize(
    "price", [Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")]
)
def test_travel_cost_rejects_invalid_reference_price(price: Decimal) -> None:
    with pytest.raises(ValueError, match="reference_price"):
        estimated_travel_cost(10, Decimal("6"), price)


@pytest.mark.parametrize(
    ("refueling", "travel"),
    [
        (Decimal("-1"), Decimal("0")),
        (Decimal("NaN"), Decimal("0")),
        (Decimal("Infinity"), Decimal("0")),
        (Decimal("1"), Decimal("-1")),
        (Decimal("1"), Decimal("NaN")),
        (Decimal("1"), Decimal("Infinity")),
    ],
)
def test_effective_cost_rejects_invalid_components(
    refueling: Decimal, travel: Decimal
) -> None:
    with pytest.raises(ValueError):
        estimated_effective_cost(refueling, travel)
