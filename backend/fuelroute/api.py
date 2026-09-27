"""Small public catalog API over the source-independent fuel provider."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from fuelroute.domain.models import Station
from fuelroute.providers.base import (
    CacheState,
    Freshness,
    FuelPriceProvider,
    FuelPriceProviderError,
    ProviderHTTPError,
    ProviderUnavailableError,
)
from fuelroute.services.nearby import NearbySearchRequest, search_nearby

router = APIRouter()


class FreshnessResponse(BaseModel):
    fetched_at: datetime
    age_seconds: float
    state: CacheState
    is_stale: bool


class FuelResponse(BaseModel):
    id: str
    name: str
    abbreviation: str | None


class ProvinceResponse(BaseModel):
    id: str
    name: str


class MunicipalityResponse(BaseModel):
    id: str
    name: str
    province_id: str | None


class FuelsResponse(BaseModel):
    items: list[FuelResponse]
    freshness: FreshnessResponse


class ProvincesResponse(BaseModel):
    items: list[ProvinceResponse]
    freshness: FreshnessResponse


class MunicipalitiesResponse(BaseModel):
    items: list[MunicipalityResponse]
    freshness: FreshnessResponse


def get_provider(request: Request) -> FuelPriceProvider:
    """FastAPI dependency; tests may override it without touching HTTP internals."""
    return cast(FuelPriceProvider, request.app.state.fuel_price_provider)


def _freshness(value: Freshness | None) -> FreshnessResponse:
    if value is None:
        raise HTTPException(status_code=500, detail="Fuel data freshness unavailable")
    return FreshnessResponse(
        fetched_at=value.fetched_at,
        age_seconds=value.age.total_seconds(),
        state=value.state,
        is_stale=value.is_stale,
    )


def provider_error_handler(_request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, FuelPriceProviderError):
        raise error
    transient = isinstance(error, ProviderUnavailableError) or (
        isinstance(error, ProviderHTTPError)
        and (error.status_code in (408, 429) or 500 <= error.status_code <= 599)
    )
    if transient:
        return JSONResponse(
            status_code=503, content={"detail": "Fuel data temporarily unavailable"}
        )
    return JSONResponse(
        status_code=502, content={"detail": "Fuel data response unavailable"}
    )


@router.get("/fuels", response_model=FuelsResponse)
def get_fuels(
    provider: Annotated[FuelPriceProvider, Depends(get_provider)],
) -> FuelsResponse:
    result = provider.get_products()
    return FuelsResponse(
        items=[
            FuelResponse(
                id=product.id,
                name=product.name,
                abbreviation=product.abbreviation,
            )
            for product in result.value
        ],
        freshness=_freshness(result.freshness),
    )


@router.get("/provinces", response_model=ProvincesResponse)
def get_provinces(
    provider: Annotated[FuelPriceProvider, Depends(get_provider)],
) -> ProvincesResponse:
    result = provider.get_provinces()
    return ProvincesResponse(
        items=[ProvinceResponse(id=item.id, name=item.name) for item in result.value],
        freshness=_freshness(result.freshness),
    )


@router.get("/municipalities", response_model=MunicipalitiesResponse)
def get_municipalities(
    provider: Annotated[FuelPriceProvider, Depends(get_provider)],
    province_id: str | None = Query(default=None, pattern=r"^[0-9]+$"),
) -> MunicipalitiesResponse:
    result = provider.get_municipalities(province_id)
    return MunicipalitiesResponse(
        items=[
            MunicipalityResponse(
                id=item.id, name=item.name, province_id=item.province_id
            )
            for item in result.value
        ],
        freshness=_freshness(result.freshness),
    )


class StationResponse(BaseModel):
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


class SelectedPriceResponse(BaseModel):
    product: FuelResponse
    price_eur_l: Decimal


class NearbyStationResponse(BaseModel):
    station: StationResponse
    price: SelectedPriceResponse
    distance_km: float = Field(
        description=(
            "Haversine geodesic distance in km: a straight-line approximation, "
            "not road distance, a real route, a detour, or a reachability guarantee."
        )
    )


class NearbyStationsResponse(BaseModel):
    items: list[NearbyStationResponse]
    freshness: FreshnessResponse


def _station_response(station: Station) -> StationResponse:
    return StationResponse(
        id=station.id,
        brand=station.brand,
        address=station.address,
        locality=station.locality,
        municipality=station.municipality,
        province=station.province,
        municipality_id=station.municipality_id,
        province_id=station.province_id,
        postal_code=station.postal_code,
        latitude=station.latitude,
        longitude=station.longitude,
        schedule=station.schedule,
    )


@router.get(
    "/stations/nearby",
    response_model=NearbyStationsResponse,
    summary="Find nearby stations with a selected fuel price",
    description=(
        "Distances use Haversine and are straight-line approximations. They are "
        "not road distances, real routes, detours, or reachability guarantees. "
        "The radius includes stations on its boundary."
    ),
)
def get_nearby_stations(
    provider: Annotated[FuelPriceProvider, Depends(get_provider)],
    lat: Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)],
    lon: Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)],
    fuel: Annotated[
        str, Query(min_length=1, description="Text product ID from /fuels")
    ],
    radius_km: Annotated[float, Query(gt=0, allow_inf_nan=False)],
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> NearbyStationsResponse:
    if not fuel.strip():
        raise HTTPException(status_code=422, detail="Invalid fuel product")
    if not any(product.id == fuel for product in provider.get_products().value):
        raise HTTPException(status_code=422, detail="Unknown fuel product")

    result = search_nearby(
        provider, NearbySearchRequest(lat, lon, fuel, radius_km, limit)
    )
    return NearbyStationsResponse(
        items=[
            NearbyStationResponse(
                station=_station_response(item.station),
                price=SelectedPriceResponse(
                    product=FuelResponse(
                        id=item.price.product.id,
                        name=item.price.product.name,
                        abbreviation=item.price.product.abbreviation,
                    ),
                    price_eur_l=item.price.price_eur_l,
                ),
                distance_km=item.distance_km,
            )
            for item in result.items
        ],
        freshness=_freshness(result.freshness),
    )
