"""Public catalog API tests with provider fakes and no network access."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app import create_app
from fuelroute.api import get_provider
from fuelroute.domain.models import (
    FuelProduct,
    Municipality,
    Province,
    StationBatch,
)
from fuelroute.providers.base import (
    CacheState,
    Freshness,
    ProviderHTTPError,
    ProviderResult,
    ProviderSchemaError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from fuelroute.providers.cache import CachingFuelPriceProvider


class CatalogFake:
    def __init__(self) -> None:
        self.calls: list[str | None] = []
        self.failure: Exception | None = None
        self.municipalities: tuple[Municipality, ...] = (
            Municipality("100", "Municipio", "02"),
        )

    @staticmethod
    def _freshness() -> Freshness:
        return Freshness(
            datetime(2026, 9, 27, tzinfo=UTC), timedelta(0), CacheState.MISS
        )

    def _fail_if_needed(self) -> None:
        if self.failure is not None:
            raise self.failure

    def get_products(self) -> ProviderResult[tuple[FuelProduct, ...]]:
        self._fail_if_needed()
        return ProviderResult(
            (FuelProduct("1", "Gasolina 95 E5", "G95E5"),), self._freshness()
        )

    def get_provinces(self) -> ProviderResult[tuple[Province, ...]]:
        self._fail_if_needed()
        return ProviderResult((Province("02", "ALBACETE"),), self._freshness())

    def get_municipalities(
        self, province_id: str | None = None
    ) -> ProviderResult[tuple[Municipality, ...]]:
        self.calls.append(province_id)
        self._fail_if_needed()
        return ProviderResult(self.municipalities, self._freshness())

    def get_stations(self) -> ProviderResult[StationBatch]:
        raise AssertionError("station API must not call this method")

    def get_stations_for_municipality_product(
        self, municipality_id: str, product: FuelProduct
    ) -> ProviderResult[StationBatch]:
        raise AssertionError("station API must not call this method")


def _client(fake: CatalogFake | CachingFuelPriceProvider) -> TestClient:
    application = create_app()
    application.dependency_overrides[get_provider] = lambda: fake
    return TestClient(application)


def test_fuels_public_shape_and_freshness() -> None:
    with _client(CatalogFake()) as client:
        response = client.get("/fuels")
    assert response.status_code == 200
    assert response.json() == {
        "items": [{"id": "1", "name": "Gasolina 95 E5", "abbreviation": "G95E5"}],
        "freshness": {
            "fetched_at": "2026-09-27T00:00:00Z",
            "age_seconds": 0.0,
            "state": "miss",
            "is_stale": False,
        },
    }
    assert "IDProducto" not in response.text
    assert "NombreProducto" not in response.text


def test_provinces_keep_textual_ids() -> None:
    with _client(CatalogFake()) as client:
        response = client.get("/provinces")
    assert response.status_code == 200
    assert response.json()["items"] == [{"id": "02", "name": "ALBACETE"}]
    assert "IDPovincia" not in response.text


def test_municipalities_dispatch_preserves_leading_zero_and_empty() -> None:
    fake = CatalogFake()
    with _client(fake) as client:
        all_response = client.get("/municipalities")
        filtered_response = client.get("/municipalities?province_id=02")
        fake.municipalities = ()
        empty_response = client.get("/municipalities?province_id=51")
    assert fake.calls == [None, "02", "51"]
    assert all_response.status_code == filtered_response.status_code == 200
    assert filtered_response.json()["items"] == [
        {"id": "100", "name": "Municipio", "province_id": "02"}
    ]
    assert empty_response.status_code == 200
    assert empty_response.json()["items"] == []


def test_municipality_id_syntax_is_validated_without_upstream_call() -> None:
    fake = CatalogFake()
    with _client(fake) as client:
        response = client.get("/municipalities?province_id=https://example.org")
    assert response.status_code == 422
    assert fake.calls == []


def test_stale_cache_fallback_remains_http_200() -> None:
    fake = CatalogFake()
    current = datetime(2026, 9, 27, tzinfo=UTC)

    def clock() -> datetime:
        return current

    cached = CachingFuelPriceProvider(fake, now=clock)
    with _client(cached) as client:
        first = client.get("/fuels")
        current += timedelta(seconds=601)
        fake.failure = ProviderTimeoutError("products", "private timeout")
        stale = client.get("/fuels")
    assert first.status_code == stale.status_code == 200
    assert first.json()["freshness"]["state"] == "miss"
    assert stale.json()["freshness"] == {
        "fetched_at": first.json()["freshness"]["fetched_at"],
        "age_seconds": 601.0,
        "state": "stale",
        "is_stale": True,
    }


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (ProviderTimeoutError("private/path", "secret timeout"), 503),
        (ProviderUnavailableError("private/path", "secret unavailable"), 503),
        (ProviderHTTPError("private/path", 503), 503),
        (ProviderHTTPError("private/path", 429), 503),
        (ProviderHTTPError("private/path", 400), 502),
        (ProviderSchemaError("private/path", "secret schema"), 502),
    ],
)
def test_provider_errors_have_fixed_public_bodies(
    error: Exception, status: int
) -> None:
    fake = CatalogFake()
    fake.failure = error
    with _client(fake) as client:
        response = client.get("/fuels")
    assert response.status_code == status
    assert response.json() == {
        "detail": (
            "Fuel data temporarily unavailable"
            if status == 503
            else "Fuel data response unavailable"
        )
    }
    assert "private" not in response.text
    assert "secret" not in response.text


def test_health_is_independent_of_broken_provider() -> None:
    fake = CatalogFake()
    fake.failure = ProviderUnavailableError("private/path", "offline")
    with _client(fake) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake.calls == []


def test_lifespan_owns_one_http_client_and_composes_provider() -> None:
    def no_network(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("lifespan must not contact MITECO")

    http_client = httpx.Client(transport=httpx.MockTransport(no_network))
    application = create_app(client_factory=lambda: http_client)
    with TestClient(application) as client:
        provider = application.state.fuel_price_provider
        assert isinstance(provider, CachingFuelPriceProvider)
        assert client.get("/health").json() == {"status": "ok"}
        assert not http_client.is_closed
    assert http_client.is_closed
    assert not hasattr(application.state, "fuel_price_provider")


def test_real_composition_serves_second_catalog_request_from_cache() -> None:
    requests: list[str] = []

    def catalog_response(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(
            200,
            json=[
                {
                    "IDProducto": "1",
                    "NombreProducto": "Gasolina 95 E5",
                    "NombreProductoAbreviatura": "G95E5",
                }
            ],
        )

    http_client = httpx.Client(transport=httpx.MockTransport(catalog_response))
    application = create_app(client_factory=lambda: http_client)
    with TestClient(application) as client:
        first = client.get("/fuels")
        second = client.get("/fuels")
    assert first.status_code == second.status_code == 200
    assert first.json()["freshness"]["state"] == "miss"
    assert second.json()["freshness"]["state"] == "hit"
    assert first.json()["items"] == second.json()["items"]
    assert requests == [
        "https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/"
        "PreciosCarburantes/Listados/ProductosPetroliferos/"
    ]
    assert http_client.is_closed
