"""Public catalog API tests with provider fakes and no network access."""

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

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
from fuelroute.services.nearby import NearbySearchResult, NearbyStation


class CatalogFake:
    def __init__(self) -> None:
        self.calls: list[str | None] = []
        self.failure: Exception | None = None
        self.station_failure: Exception | None = None
        self.station_calls = 0
        self.product_calls = 0
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
        self.product_calls += 1
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
                "reachability_status": "unknown",
                "usable_autonomy_km": None,
                "estimated_refuel_cost": None,
                "estimated_travel_liters": None,
                "estimated_travel_cost": None,
                "estimated_effective_cost": None,
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
                "reachability_status": "unknown",
                "usable_autonomy_km": None,
                "estimated_refuel_cost": None,
                "estimated_travel_liters": None,
                "estimated_travel_cost": None,
                "estimated_effective_cost": None,
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
    for phrase in ("road distances", "real routes", "detours", "reachability"):
        assert phrase in operation["description"]
    for phrase in (
        "straight-line",
        "road distance",
        "real route",
        "detour",
        "reachability",
    ):
        assert phrase in distance


def test_nearby_explicit_distance_sort_preserves_old_order_and_limit() -> None:
    fake = _nearby_fake()
    with _client(fake) as client:
        response = client.get(
            "/stations/nearby",
            params={**NEARBY_PARAMS, "sort_by": "distance", "limit": "1"},
        )
    assert response.status_code == 200
    assert [item["station"]["id"] for item in response.json()["items"]] == ["near"]
    assert fake.station_calls == 1


def _ranking_fake() -> CatalogFake:
    fake = _nearby_fake()
    selected = fake.products[1]
    fake.station_batch = StationBatch(
        (
            _station("near-expensive", 0.01, FuelPrice(selected, Decimal("1.50"))),
            _station("far-cheap", 0.03, FuelPrice(selected, Decimal("1.40"))),
            _station("middle", 0.02, FuelPrice(selected, Decimal("1.45"))),
            _station("wrong-fuel", 0.001, FuelPrice(fake.products[0], Decimal("0.1"))),
            _station("outside", 1, FuelPrice(selected, Decimal("0.5"))),
        ),
        fake.station_batch.source,
    )
    return fake


@pytest.mark.parametrize("sort_by", ["price", "effective_cost"])
def test_http_limit_is_after_economic_rank_over_full_radius(sort_by: str) -> None:
    fake = _ranking_fake()
    params = {
        **NEARBY_PARAMS,
        "radius_km": "10",
        "sort_by": sort_by,
        "limit": "1",
        "liters": "40",
        "consumption_l_100km": "6",
    }
    with _client(fake) as client:
        response = client.get("/stations/nearby", params=params)
    assert response.status_code == 200
    assert [item["station"]["id"] for item in response.json()["items"]] == ["far-cheap"]
    assert fake.station_calls == 1
    assert fake.product_calls == 1
    assert response.json()["items"][0]["price"]["product"]["id"] == "01"


def test_http_autonomy_default_custom_and_not_reachable_remains() -> None:
    fake = _nearby_fake()
    selected = fake.products[1]
    fake.station_batch = StationBatch(
        (
            _station("inside", 0.20, FuelPrice(selected, Decimal("1.50"))),
            _station("outside", 0.30, FuelPrice(selected, Decimal("1.50"))),
        ),
        fake.station_batch.source,
    )
    with _client(fake) as client:
        default = client.get(
            "/stations/nearby",
            params={**NEARBY_PARAMS, "autonomy_km": "40"},
        )
        custom = client.get(
            "/stations/nearby",
            params={
                **NEARBY_PARAMS,
                "autonomy_km": "40",
                "safety_reserve_percent": "25",
            },
        )
    assert default.status_code == custom.status_code == 200
    assert [item["station"]["id"] for item in default.json()["items"]] == [
        "inside",
        "outside",
    ]
    assert [item["usable_autonomy_km"] for item in default.json()["items"]] == [
        32.0,
        32.0,
    ]
    assert [item["reachability_status"] for item in default.json()["items"]] == [
        "possibly_reachable",
        "not_reachable",
    ]
    assert [item["usable_autonomy_km"] for item in custom.json()["items"]] == [
        30.0,
        30.0,
    ]
    assert custom.json()["items"][1]["reachability_status"] == "not_reachable"


def test_http_autonomy_exact_boundary_stays_possible() -> None:
    fake = _nearby_fake()
    price = FuelPrice(fake.products[1], Decimal("1.50"))
    edge = _station("edge", 0, price)
    beyond = _station("beyond", 0, price)
    geographic = NearbySearchResult(
        (
            NearbyStation(edge, price, 32.0),
            NearbyStation(beyond, price, math.nextafter(32.0, math.inf)),
        ),
        fake.station_batch.source,
        fake.station_freshness,
    )
    with patch("fuelroute.api.search_nearby", return_value=geographic):
        with _client(fake) as client:
            response = client.get(
                "/stations/nearby",
                params={**NEARBY_PARAMS, "autonomy_km": "40"},
            )
    assert response.status_code == 200
    assert [item["reachability_status"] for item in response.json()["items"]] == [
        "possibly_reachable",
        "not_reachable",
    ]


def test_http_costs_use_decimal_candidate_price_with_manual_expected() -> None:
    fake = _nearby_fake()
    price = FuelPrice(fake.products[1], Decimal("1.50"))
    target = _station("ten-km", 0, price)
    geographic = NearbySearchResult(
        (NearbyStation(target, price, 10.0),),
        fake.station_batch.source,
        fake.station_freshness,
    )
    with patch("fuelroute.api.search_nearby", return_value=geographic):
        with _client(fake) as client:
            response = client.get(
                "/stations/nearby",
                params={
                    **NEARBY_PARAMS,
                    "autonomy_km": "40",
                    "liters": "40",
                    "consumption_l_100km": "6",
                    "sort_by": "effective_cost",
                },
            )
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["price"]["price_eur_l"] == "1.50"
    assert item["distance_km"] == 10.0
    assert item["reachability_status"] == "possibly_reachable"
    assert item["usable_autonomy_km"] == 32.0
    assert item["estimated_refuel_cost"] == "60.00"
    assert item["estimated_travel_liters"] == "0.6"
    assert item["estimated_travel_cost"] == "0.900"
    assert item["estimated_effective_cost"] == "60.900"


@pytest.mark.parametrize(
    ("extra", "expected_present", "expected_null"),
    [
        (
            {"liters": "40"},
            {"estimated_refuel_cost": "49.360"},
            (
                "estimated_travel_liters",
                "estimated_travel_cost",
                "estimated_effective_cost",
            ),
        ),
        (
            {"consumption_l_100km": "6"},
            {},
            ("estimated_refuel_cost", "estimated_effective_cost"),
        ),
    ],
)
def test_http_optional_costs_are_null_without_required_inputs(
    extra: dict[str, str],
    expected_present: dict[str, str],
    expected_null: tuple[str, ...],
) -> None:
    fake = _nearby_fake()
    with _client(fake) as client:
        response = client.get(
            "/stations/nearby", params={**NEARBY_PARAMS, **extra, "sort_by": "price"}
        )
    assert response.status_code == 200
    item = response.json()["items"][0]
    for name, value in expected_present.items():
        assert item[name] == value
    for name in expected_null:
        assert item[name] is None
    if "consumption_l_100km" in extra:
        assert item["estimated_travel_liters"] is not None
        assert item["estimated_travel_cost"] is not None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("autonomy_km", "0"),
        ("autonomy_km", "-1"),
        ("autonomy_km", "NaN"),
        ("autonomy_km", "Infinity"),
        ("consumption_l_100km", "0"),
        ("consumption_l_100km", "-1"),
        ("consumption_l_100km", "NaN"),
        ("consumption_l_100km", "Infinity"),
        ("liters", "0"),
        ("liters", "-1"),
        ("liters", "NaN"),
        ("liters", "Infinity"),
        ("safety_reserve_percent", "-1"),
        ("safety_reserve_percent", "100"),
        ("safety_reserve_percent", "101"),
        ("safety_reserve_percent", "NaN"),
        ("safety_reserve_percent", "Infinity"),
        ("sort_by", "unknown"),
    ],
)
def test_http_invalid_phase3_query_is_422_before_provider(key: str, value: str) -> None:
    fake = _nearby_fake()
    with _client(fake) as client:
        response = client.get("/stations/nearby", params={**NEARBY_PARAMS, key: value})
    assert response.status_code == 422
    assert fake.product_calls == 0
    assert fake.station_calls == 0


@pytest.mark.parametrize(
    "extra",
    [
        {"sort_by": "effective_cost"},
        {"sort_by": "effective_cost", "liters": "40"},
        {"sort_by": "effective_cost", "consumption_l_100km": "6"},
    ],
)
def test_http_effective_sort_requires_both_inputs_before_provider(
    extra: dict[str, str],
) -> None:
    fake = _nearby_fake()
    with _client(fake) as client:
        response = client.get("/stations/nearby", params={**NEARBY_PARAMS, **extra})
    assert response.status_code == 422
    assert "effective_cost sort requires" in response.json()["detail"]
    assert fake.product_calls == 0
    assert fake.station_calls == 0


@pytest.mark.parametrize(
    "extra",
    [
        {"liters": "40", "consumption_l_100km": "6"},
        {
            "liters": "40",
            "consumption_l_100km": "6",
            "sort_by": "effective_cost",
        },
    ],
)
def test_http_zero_candidates_remains_success_with_economic_inputs(
    extra: dict[str, str],
) -> None:
    fake = _nearby_fake()
    with _client(fake) as client:
        response = client.get(
            "/stations/nearby",
            params={**NEARBY_PARAMS, "radius_km": "1", **extra},
        )
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["freshness"]["state"] == "miss"
    assert fake.station_calls == 1


def test_http_openapi_documents_personalization_policy() -> None:
    with _client(_nearby_fake()) as client:
        schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/stations/nearby"]["get"]
    description = operation["description"].lower()
    for phrase in (
        "haversine",
        "origin-to-station",
        "straight-line",
        "not road distances",
        "possibly_reachable",
        "confirm the real route",
        "not_reachable",
        "candidate station",
        "replacement reference price",
        "round trips",
        "detours",
    ):
        assert phrase in description
    parameters = {item["name"]: item for item in operation["parameters"]}
    assert parameters["sort_by"]["schema"]["default"] == "distance"
    assert parameters["safety_reserve_percent"]["schema"]["default"] == 20.0
    for name in (
        "autonomy_km",
        "safety_reserve_percent",
        "consumption_l_100km",
        "liters",
        "sort_by",
    ):
        assert parameters[name]["description"]
    fields = schema["components"]["schemas"]["NearbyStationResponse"]["properties"]
    assert "origin-to-station" in fields["distance_km"]["description"]
    assert (
        "outside the safety margin even" in fields["reachability_status"]["description"]
    )
    assert "confirm the real route" in fields["reachability_status"]["description"]
    assert "candidate station" in fields["estimated_travel_cost"]["description"]
    assert (
        "replacement reference price" in fields["estimated_travel_cost"]["description"]
    )
