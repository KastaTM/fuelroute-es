"""Public catalog API tests with provider fakes and no network access."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from app import create_app
from fuelroute.api import get_provider
from fuelroute.domain.models import (
    FuelPrice,
    FuelProduct,
    Municipality,
    Province,
    SourceMetadata,
    Station,
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
        self.station_failure: Exception | None = None
        self.station_calls = 0
        self.products: tuple[FuelProduct, ...] = (
            FuelProduct("1", "Gasolina 95 E5", "G95E5"),
        )
        self.station_batch = StationBatch((), SourceMetadata(None, None, None))
        self.station_freshness = self._freshness()
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
        return ProviderResult(self.products, self._freshness())

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
        self.station_calls += 1
        if self.station_failure is not None:
            raise self.station_failure
        return ProviderResult(self.station_batch, self.station_freshness)

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


NEARBY_PARAMS = {"lat": "0", "lon": "0", "fuel": "01", "radius_km": "300"}


def _station(station_id: str, longitude: float, *prices: FuelPrice) -> Station:
    return Station(
        id=station_id,
        brand="Brand",
        address="Street 1",
        locality="Locality",
        municipality="Town",
        province="Province",
        municipality_id="0001",
        province_id="02",
        postal_code="12345",
        latitude=0,
        longitude=longitude,
        schedule="24H",
        prices=prices,
    )


def _nearby_fake() -> CatalogFake:
    fake = CatalogFake()
    selected = FuelProduct("01", "Product 01", "P01")
    fake.products = (fake.products[0], selected)
    fake.station_batch = StationBatch(
        (
            _station("far", 2, FuelPrice(selected, Decimal("1.999"))),
            _station(
                "near",
                1,
                FuelPrice(fake.products[0], Decimal("1.111")),
                FuelPrice(selected, Decimal("1.234")),
            ),
        ),
        SourceMetadata(None, "private source time", "private note"),
    )
    return fake


def test_nearby_exact_normalized_json_and_textual_fuel() -> None:
    fake = _nearby_fake()
    with _client(fake) as client:
        response = client.get("/stations/nearby", params=NEARBY_PARAMS)
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "station": {
                    "id": "near",
                    "brand": "Brand",
                    "address": "Street 1",
                    "locality": "Locality",
                    "municipality": "Town",
                    "province": "Province",
                    "municipality_id": "0001",
                    "province_id": "02",
                    "postal_code": "12345",
                    "latitude": 0.0,
                    "longitude": 1.0,
                    "schedule": "24H",
                },
                "price": {
                    "product": {
                        "id": "01",
                        "name": "Product 01",
                        "abbreviation": "P01",
                    },
                    "price_eur_l": "1.234",
                },
                "distance_km": pytest.approx(111.1950802335329),
            },
            {
                "station": {
                    "id": "far",
                    "brand": "Brand",
                    "address": "Street 1",
                    "locality": "Locality",
                    "municipality": "Town",
                    "province": "Province",
                    "municipality_id": "0001",
                    "province_id": "02",
                    "postal_code": "12345",
                    "latitude": 0.0,
                    "longitude": 2.0,
                    "schedule": "24H",
                },
                "price": {
                    "product": {
                        "id": "01",
                        "name": "Product 01",
                        "abbreviation": "P01",
                    },
                    "price_eur_l": "1.999",
                },
                "distance_km": pytest.approx(222.3901604670658),
            },
        ],
        "freshness": {
            "fetched_at": "2026-09-27T00:00:00Z",
            "age_seconds": 0.0,
            "state": "miss",
            "is_stale": False,
        },
    }
    assert fake.station_calls == 1
    for forbidden in ("IDEESS", "PrecioProducto", "ListaEESSPrecio", "private"):
        assert forbidden not in response.text


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("lat", "-90.01"),
        ("lat", "90.01"),
        ("lon", "-180.01"),
        ("lon", "180.01"),
        ("lat", "NaN"),
        ("lon", "Infinity"),
        ("radius_km", "0"),
        ("radius_km", "-1"),
        ("radius_km", "Infinity"),
        ("fuel", ""),
        ("fuel", "   "),
        ("limit", "0"),
        ("limit", "-1"),
        ("limit", "101"),
    ],
)
def test_nearby_invalid_query_is_422_without_station_fetch(
    key: str, value: str
) -> None:
    fake = _nearby_fake()
    params = {**NEARBY_PARAMS, key: value}
    with _client(fake) as client:
        response = client.get("/stations/nearby", params=params)
    assert response.status_code == 422
    assert fake.station_calls == 0


def test_nearby_unknown_fuel_is_fixed_422() -> None:
    fake = _nearby_fake()
    with _client(fake) as client:
        response = client.get(
            "/stations/nearby", params={**NEARBY_PARAMS, "fuel": "001"}
        )
    assert response.status_code == 422
    assert response.json() == {"detail": "Unknown fuel product"}
    assert fake.station_calls == 0


def test_nearby_limit_after_distance_order_and_empty_success() -> None:
    fake = _nearby_fake()
    with _client(fake) as client:
        limited = client.get("/stations/nearby", params={**NEARBY_PARAMS, "limit": "1"})
        empty = client.get(
            "/stations/nearby", params={**NEARBY_PARAMS, "radius_km": "1"}
        )
    assert limited.status_code == empty.status_code == 200
    assert [item["station"]["id"] for item in limited.json()["items"]] == ["near"]
    assert empty.json() == {
        "items": [],
        "freshness": {
            "fetched_at": "2026-09-27T00:00:00Z",
            "age_seconds": 0.0,
            "state": "miss",
            "is_stale": False,
        },
    }


def test_nearby_stale_freshness_remains_http_200() -> None:
    fake = _nearby_fake()
    fake.station_freshness = Freshness(
        datetime(2026, 9, 26, tzinfo=UTC), timedelta(minutes=20), CacheState.STALE
    )
    with _client(fake) as client:
        response = client.get("/stations/nearby", params=NEARBY_PARAMS)
    assert response.status_code == 200
    assert response.json()["freshness"] == {
        "fetched_at": "2026-09-26T00:00:00Z",
        "age_seconds": 1200.0,
        "state": "stale",
        "is_stale": True,
    }


@pytest.mark.parametrize(
    ("error", "status", "detail", "stage"),
    [
        (
            ProviderTimeoutError("stations", "private timeout"),
            503,
            "Fuel data temporarily unavailable",
            "stations",
        ),
        (
            ProviderUnavailableError("stations", "private offline"),
            503,
            "Fuel data temporarily unavailable",
            "stations",
        ),
        (
            ProviderSchemaError("stations", "private schema"),
            502,
            "Fuel data response unavailable",
            "stations",
        ),
        (
            ProviderTimeoutError("products", "private timeout"),
            503,
            "Fuel data temporarily unavailable",
            "products",
        ),
        (
            ProviderSchemaError("products", "private schema"),
            502,
            "Fuel data response unavailable",
            "products",
        ),
    ],
)
def test_nearby_provider_failures_keep_existing_public_policy(
    error: Exception, status: int, detail: str, stage: str
) -> None:
    fake = _nearby_fake()
    if stage == "products":
        fake.failure = error
    else:
        fake.station_failure = error
    with _client(fake) as client:
        response = client.get("/stations/nearby", params=NEARBY_PARAMS)
    assert response.status_code == status
    assert response.json() == {"detail": detail}
    assert "private" not in response.text
    assert fake.station_calls == (0 if stage == "products" else 1)


def test_nearby_route_keeps_catalog_and_health_working() -> None:
    fake = _nearby_fake()
    with _client(fake) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/fuels").json()["items"][1]["id"] == "01"
        assert client.get("/stations/nearby", params=NEARBY_PARAMS).status_code == 200


def test_nearby_openapi_explains_straight_line_limitations() -> None:
    with _client(_nearby_fake()) as client:
        schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/stations/nearby"]["get"]
    distance = schema["components"]["schemas"]["NearbyStationResponse"]["properties"][
        "distance_km"
    ]["description"]
    assert "Haversine" in operation["description"]
    for phrase in (
        "straight-line",
        "road distance",
        "real route",
        "detour",
        "reachability",
    ):
        assert phrase in distance
