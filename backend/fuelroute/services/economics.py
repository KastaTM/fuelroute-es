"""Pure vehicle autonomy and economic calculations."""

import math
from decimal import Decimal
from enum import StrEnum

DEFAULT_SAFETY_RESERVE_PERCENT = 20.0


class Reachability(StrEnum):
    """Straight-line assessment; a real route must still be checked."""

    UNKNOWN = "unknown"
    POSSIBLY_REACHABLE = "possibly_reachable"
    NOT_REACHABLE = "not_reachable"


def _finite_nonnegative_distance(distance_km: float) -> None:
    if not math.isfinite(distance_km) or distance_km < 0:
        raise ValueError("distance_km must be finite and non-negative")


def _positive_decimal(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a finite positive Decimal")


def usable_autonomy_km(
    autonomy_km: float,
    safety_reserve_percent: float = DEFAULT_SAFETY_RESERVE_PERCENT,
) -> float:
    """Return remaining straight-line margin without rounding."""
    if not math.isfinite(autonomy_km) or autonomy_km <= 0:
        raise ValueError("autonomy_km must be finite and positive")
    if (
        not math.isfinite(safety_reserve_percent)
        or not 0 <= safety_reserve_percent < 100
    ):
        raise ValueError("safety_reserve_percent must be finite and in [0, 100)")
    return autonomy_km * (1 - safety_reserve_percent / 100)


def classify_reachability(
    distance_km: float,
    autonomy_km: float | None,
    safety_reserve_percent: float = DEFAULT_SAFETY_RESERVE_PERCENT,
) -> Reachability:
    """Classify straight-line distance without asserting road reachability."""
    _finite_nonnegative_distance(distance_km)
    if autonomy_km is None:
        return Reachability.UNKNOWN
    usable = usable_autonomy_km(autonomy_km, safety_reserve_percent)
    if distance_km > usable:
        return Reachability.NOT_REACHABLE
    return Reachability.POSSIBLY_REACHABLE


def refuel_cost(liters_to_refuel: Decimal, price_eur_l: Decimal) -> Decimal:
    """Calculate exact nominal refueling cost."""
    _positive_decimal(liters_to_refuel, "liters_to_refuel")
    _positive_decimal(price_eur_l, "price_eur_l")
    return liters_to_refuel * price_eur_l


def travel_liters(distance_km: float, consumption_l_100km: Decimal) -> Decimal:
    """Estimate fuel for a distance in km, including zero distance."""
    _finite_nonnegative_distance(distance_km)
    _positive_decimal(consumption_l_100km, "consumption_l_100km")
    return Decimal(str(distance_km)) * consumption_l_100km / Decimal(100)


def estimated_travel_cost(
    distance_km: float,
    consumption_l_100km: Decimal,
    reference_price: Decimal,
) -> Decimal:
    """Estimate travel cost using the explicitly supplied reference price."""
    _positive_decimal(reference_price, "reference_price")
    return travel_liters(distance_km, consumption_l_100km) * reference_price


def estimated_effective_cost(
    refuel_cost: Decimal, estimated_travel_cost: Decimal
) -> Decimal:
    """Sum the two cost components without rounding."""
    for name, value in (
        ("refuel_cost", refuel_cost),
        ("estimated_travel_cost", estimated_travel_cost),
    ):
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError(f"{name} must be a finite non-negative Decimal")
    return refuel_cost + estimated_travel_cost
