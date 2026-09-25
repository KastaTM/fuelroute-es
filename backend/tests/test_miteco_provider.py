"""Offline provider contract tests using httpx.MockTransport only."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from fuelroute.domain.models import (
    FuelPrice,
    FuelProduct,
    Municipality,
    Province,
    StationBatch,
)
from fuelroute.providers.base import (
    FuelPriceProvider,
    ProviderHTTPError,
    ProviderInvalidJSONError,
    ProviderSchemaError,
    ProviderSemanticError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from fuelroute.providers.miteco.provider import BASE_URL, MitecoFuelPriceProvider

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any], json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    )


def response(payload: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def test_catalog_operations_and_paths() -> None:
    catalogs = fixture("miteco_catalogs.json")
    paths: list[str] = []
    payloads = {
        "/Listados/ProductosPetroliferos/": catalogs["products"],
        "/Listados/Provincias/": catalogs["provinces"],
        "/Listados/Municipios/": catalogs["municipalities"],
        "/Listados/MunicipiosPorProvincia/51": catalogs["municipalities"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(BASE_URL)
        assert request.headers["Accept"] == "application/json"
        path = request.url.path.removeprefix(
            "/ServiciosRestCarburantes/PreciosCarburantes"
        )
        paths.append(path)
        return response(payloads[path])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider: FuelPriceProvider = MitecoFuelPriceProvider(client)
        products = provider.get_products()
        provinces = provider.get_provinces()
        municipalities = provider.get_municipalities()
        by_province = provider.get_municipalities("51")
        assert len(products) == 30 and isinstance(products[0], FuelProduct)
        assert products[0].id == "1"
        assert provinces == (Province("02", "ALBACETE"), Province("51", "CEUTA"))
        assert municipalities == by_province == (Municipality("8110", "Ceuta", "51"),)
        assert paths == list(payloads)
        assert not client.is_closed


def test_province_id_keeps_leading_zero_in_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/Listados/MunicipiosPorProvincia/02")
        return response([])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert MitecoFuelPriceProvider(client).get_municipalities("02") == ()


def test_general_stations_fetches_catalog_before_station_data() -> None:
    catalogs = fixture("miteco_catalogs.json")
    sample = fixture("miteco_ceuta.json")
    general = {
        "Fecha": sample["observed_fecha"],
        "ListaEESSPrecio": sample["stations"],
        "Nota": None,
        "ResultadoConsulta": "OK",
    }
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/Listados/ProductosPetroliferos/"):
            return response(catalogs["products"])
        assert request.url.path.endswith("/EstacionesTerrestres/")
        return response(general)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider: FuelPriceProvider = MitecoFuelPriceProvider(client)
        batch = provider.get_stations()
    assert isinstance(batch, StationBatch)
    assert len(batch.stations) == 2
    assert batch.stations[0].prices[0] == FuelPrice(
        FuelProduct("1", "Gasolina 95 E5", "G95E5"), Decimal("1.674")
    )
    assert {price.product.id for price in batch.stations[0].prices} == {"1", "4"}
    assert batch.source.unmapped_fuel_field_count == 0
    assert paths[0].endswith("/Listados/ProductosPetroliferos/")
    assert paths[1].endswith("/EstacionesTerrestres/")


def test_filtered_stations_use_requested_product_and_path() -> None:
    payload = fixture("miteco_ceuta_product.json")["response"]
    product = FuelProduct("1", "Gasolina 95 E5", "G95E5")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/FiltroMunicipioProducto/8110/1")
        return response(payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider: FuelPriceProvider = MitecoFuelPriceProvider(client)
        batch = provider.get_stations_for_municipality_product("8110", product)
    assert isinstance(batch, StationBatch)
    assert batch.stations[0].prices == (FuelPrice(product, Decimal("1.698")),)


def test_valid_empty_result_is_not_an_error() -> None:
    payload = fixture("miteco_ceuta_empty_product.json")["response"]
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: response(payload))
    ) as client:
        batch = MitecoFuelPriceProvider(client).get_stations_for_municipality_product(
            "8110", FuelProduct("22", "Hidrógeno", "H2")
        )
    assert batch.stations == ()


def test_configurable_timeout_maps_to_own_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        timeout = request.extensions["timeout"]
        assert timeout["read"] == 2.5
        raise httpx.ReadTimeout("simulated", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = MitecoFuelPriceProvider(client, timeout=2.5)
        with pytest.raises(ProviderTimeoutError) as captured:
            provider.get_products()
    assert captured.value.operation == "Listados/ProductosPetroliferos/"
    assert isinstance(captured.value, ProviderUnavailableError)
    assert not isinstance(captured.value, httpx.HTTPError)


def test_connection_error_maps_to_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderUnavailableError) as captured:
            MitecoFuelPriceProvider(client).get_products()
    assert type(captured.value) is ProviderUnavailableError


@pytest.mark.parametrize("status", [400, 503])
def test_http_error_exposes_status_without_body(status: int) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status, text="private body")
        )
    ) as client:
        with pytest.raises(ProviderHTTPError) as captured:
            MitecoFuelPriceProvider(client).get_products()
    assert captured.value.status_code == status
    assert captured.value.operation == "Listados/ProductosPetroliferos/"
    assert "private body" not in str(captured.value)


def test_invalid_json_has_distinct_error() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="{"))
    ) as client:
        with pytest.raises(ProviderInvalidJSONError) as captured:
            MitecoFuelPriceProvider(client).get_products()
    assert captured.value.operation == "Listados/ProductosPetroliferos/"


def test_incompatible_shape_has_distinct_error() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: response({"unexpected": []}))
    ) as client:
        with pytest.raises(ProviderSchemaError) as captured:
            MitecoFuelPriceProvider(client).get_products()
    assert captured.value.operation == "Listados/ProductosPetroliferos/"


def test_semantic_error_on_http_200_is_not_empty_success() -> None:
    payload: dict[str, object] = {
        "Fecha": "25/09/2026 20:27:10",
        "ListaEESSPrecio": [],
        "Nota": None,
        "ResultadoConsulta": "Parametros de entrada incorrectos.",
    }
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: response(payload))
    ) as client:
        with pytest.raises(ProviderSemanticError) as captured:
            MitecoFuelPriceProvider(client).get_stations_for_municipality_product(
                "8110", FuelProduct("1", "Gasolina 95 E5")
            )
    assert captured.value.operation.endswith("/8110/1")


def test_malformed_station_is_provider_schema_error() -> None:
    payload = fixture("miteco_ceuta_product.json")["response"]
    payload["ListaEESSPrecio"][0]["Latitud"] = "abc"  # synthetic mutation
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: response(payload))
    ) as client:
        with pytest.raises(ProviderSchemaError, match="Latitud"):
            MitecoFuelPriceProvider(client).get_stations_for_municipality_product(
                "8110", FuelProduct("1", "Gasolina 95 E5")
            )


def test_invalid_path_and_timeout_are_rejected_before_request() -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: response([]))) as client:
        with pytest.raises(ValueError, match="timeout"):
            MitecoFuelPriceProvider(client, timeout=0)
        provider = MitecoFuelPriceProvider(client)
        with pytest.raises(ValueError, match="official ID"):
            provider.get_municipalities("51/../../")
