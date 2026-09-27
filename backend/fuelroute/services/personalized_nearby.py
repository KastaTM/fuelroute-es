"""Enrich complete nearby candidates, then rank and limit without provider access."""

import math
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from fuelroute.domain.models import FuelPrice, SourceMetadata, Station
from fuelroute.providers.base import Freshness
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
from fuelroute.services.nearby import NearbySearchResult


class PersonalizedSortBy(StrEnum):
    DISTANCE = "distance"
    PRICE = "price"
    EFFECTIVE_COST = "effective_cost"


@dataclass(frozen=True, slots=True)
class PersonalizedNearbyRequest:
    average_consumption_l_100km: Decimal | None = None
    autonomy_km: float | None = None
    safety_reserve_percent: float = DEFAULT_SAFETY_RESERVE_PERCENT
    liters_to_refuel: Decimal | None = None
    sort_by: PersonalizedSortBy = PersonalizedSortBy.DISTANCE
    limit: int | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("average_consumption_l_100km", self.average_consumption_l_100km),
            ("liters_to_refuel", self.liters_to_refuel),
        ):
            if value is not None and (
                not isinstance(value, Decimal) or not value.is_finite() or value <= 0
            ):
                raise ValueError(f"{name} must be a finite positive Decimal or None")
        if self.autonomy_km is not None:
            usable_autonomy_km(self.autonomy_km, self.safety_reserve_percent)
        elif (
            not math.isfinite(self.safety_reserve_percent)
            or not 0 <= self.safety_reserve_percent < 100
        ):
            raise ValueError("safety_reserve_percent must be finite and in [0, 100)")
        if not isinstance(self.sort_by, PersonalizedSortBy):
            raise ValueError("sort_by must be a PersonalizedSortBy value")
        if self.limit is not None and (
            isinstance(self.limit, bool)
            or not isinstance(self.limit, int)
            or self.limit <= 0
        ):
            raise ValueError("limit must be a positive integer or None")
        if self.sort_by is PersonalizedSortBy.EFFECTIVE_COST and (
            self.liters_to_refuel is None or self.average_consumption_l_100km is None
        ):
            raise ValueError(
                "effective_cost sort requires liters_to_refuel and "
                "average_consumption_l_100km"
            )


@dataclass(frozen=True, slots=True)
class PersonalizedNearbyStation:
    station: Station
    price: FuelPrice
    distance_km: float
    reachability_status: Reachability
    usable_autonomy_km: float | None
    estimated_refuel_cost: Decimal | None
    estimated_travel_liters: Decimal | None
    estimated_travel_cost: Decimal | None
    estimated_effective_cost: Decimal | None


@dataclass(frozen=True, slots=True)
class PersonalizedNearbyResult:
    items: tuple[PersonalizedNearbyStation, ...]
    source: SourceMetadata
    freshness: Freshness | None


def personalize_nearby(
    nearby: NearbySearchResult, request: PersonalizedNearbyRequest
) -> PersonalizedNearbyResult:
    """Rank a complete, untruncated nearby result; apply limit only after sorting.

    Travel is origin-to-station Haversine distance, not a road route. Each
    candidate's selected fuel price values the travel fuel at its replacement
    price, not the historical price of fuel already in the tank. Costs are
    approximations; possibly_reachable never guarantees a real route.
    """
    usable = (
        usable_autonomy_km(request.autonomy_km, request.safety_reserve_percent)
        if request.autonomy_km is not None
        else None
    )
    items: list[PersonalizedNearbyStation] = []
    for candidate in nearby.items:
        reference_price = candidate.price.price_eur_l
        refueling = (
            refuel_cost(request.liters_to_refuel, reference_price)
            if request.liters_to_refuel is not None
            else None
        )
        traveling_liters = (
            travel_liters(candidate.distance_km, request.average_consumption_l_100km)
            if request.average_consumption_l_100km is not None
            else None
        )
        traveling_cost = (
            estimated_travel_cost(
                candidate.distance_km,
                request.average_consumption_l_100km,
                reference_price,
            )
            if request.average_consumption_l_100km is not None
            else None
        )
        effective = (
            estimated_effective_cost(refueling, traveling_cost)
            if refueling is not None and traveling_cost is not None
            else None
        )
        items.append(
            PersonalizedNearbyStation(
                station=candidate.station,
                price=candidate.price,
                distance_km=candidate.distance_km,
                reachability_status=classify_reachability(
                    candidate.distance_km,
                    request.autonomy_km,
                    request.safety_reserve_percent,
                ),
                usable_autonomy_km=usable,
                estimated_refuel_cost=refueling,
                estimated_travel_liters=traveling_liters,
                estimated_travel_cost=traveling_cost,
                estimated_effective_cost=effective,
            )
        )

    if request.sort_by is PersonalizedSortBy.DISTANCE:
        items.sort(key=lambda item: (item.distance_km, item.station.id))
    elif request.sort_by is PersonalizedSortBy.PRICE:
        items.sort(
            key=lambda item: (
                item.price.price_eur_l,
                item.distance_km,
                item.station.id,
            )
        )
    else:

        def effective_key(
            item: PersonalizedNearbyStation,
        ) -> tuple[Decimal, float, str]:
            cost = item.estimated_effective_cost
            if cost is None:
                raise ValueError("effective_cost sort requires calculable costs")
            return cost, item.distance_km, item.station.id

        items.sort(key=effective_key)
    if request.limit is not None:
        items = items[: request.limit]
    return PersonalizedNearbyResult(tuple(items), nearby.source, nearby.freshness)
