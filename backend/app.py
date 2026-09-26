"""FuelRoute ES HTTP application and owned provider composition."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from fuelroute.api import provider_error_handler, router
from fuelroute.providers.base import FuelPriceProviderError
from fuelroute.providers.cache import CachingFuelPriceProvider
from fuelroute.providers.miteco.provider import MitecoFuelPriceProvider


def create_app(*, client_factory: Callable[[], httpx.Client] = httpx.Client) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        with client_factory() as client:
            application.state.fuel_price_provider = CachingFuelPriceProvider(
                MitecoFuelPriceProvider(client)
            )
            yield
            del application.state.fuel_price_provider

    application = FastAPI(title="FuelRoute ES", lifespan=lifespan)
    application.include_router(router)
    application.add_exception_handler(FuelPriceProviderError, provider_error_handler)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
