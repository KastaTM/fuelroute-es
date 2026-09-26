"""Small public catalog API over the source-independent fuel provider."""

from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from fuelroute.providers.base import (
    CacheState,
    Freshness,
    FuelPriceProvider,
    FuelPriceProviderError,
    ProviderHTTPError,
    ProviderUnavailableError,
)

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
