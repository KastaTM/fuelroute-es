"""Offline contract tests with real reduced fixtures and synthetic mutations."""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from fuelroute.domain.models import FuelPrice, FuelProduct, StationBatch
from fuelroute.providers.miteco.parser import (
    MitecoParseError,
    parse_general_stations,
    parse_municipalities,
    parse_product_stations,
    parse_products,
    parse_provinces,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any], json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    )


def products() -> tuple[FuelProduct, ...]:
    return parse_products(fixture("miteco_catalogs.json")["products"])


def general_payload() -> dict[str, Any]:
    source = fixture("miteco_ceuta.json")
    return {
        "Fecha": source["observed_fecha"],
        "ListaEESSPrecio": source["stations"],
        "Nota": None,
        "ResultadoConsulta": "OK",
    }


def filtered_payload(name: str = "miteco_ceuta_product.json") -> dict[str, Any]:
    return cast(dict[str, Any], fixture(name)["response"])


def test_catalogs_and_textual_ids() -> None:
    catalogs = fixture("miteco_catalogs.json")
    parsed_products = parse_products(catalogs["products"])
    assert len(parsed_products) == 30
    assert parsed_products[0] == FuelProduct("1", "Gasolina 95 E5", "G95E5")
    provinces = parse_provinces(catalogs["provinces"])
    assert provinces[0].id == "02"
    assert provinces[1].id == "51"
    municipalities = parse_municipalities(catalogs["municipalities"])
    assert [(m.id, m.name, m.province_id) for m in municipalities] == [
        ("8110", "Ceuta", "51")
    ]


def test_general_station_from_phase0_fixture() -> None:
    batch = parse_general_stations(general_payload(), products())
    assert isinstance(batch, StationBatch)
    assert batch.source.reported_at == datetime(2026, 9, 25, 19, 15, 43)
    assert batch.source.reported_at.tzinfo is None
    assert len(batch.stations) == 2
    station = batch.stations[0]
    assert station.id == "2754"
    assert station.brand == "CEPSA"
    assert station.address == "AVENIDA GONZALEZ TABLAS, S/N"
    assert station.latitude == 35.889972
    assert station.longitude == -5.319444
    assert station.schedule == "L-V: 07:00-22:00; S: 09:00-14:00"
    assert {p.product.name: p.price_eur_l for p in station.prices} == {
        "Gasolina 95 E5": Decimal("1.674"),
        "Gasóleo A habitual": Decimal("1.704"),
    }
    assert all(p.product.name != "Gasolina 98 E10" for p in station.prices)


def test_filtered_station_requires_product_context() -> None:
    product = products()[0]
    batch = parse_product_stations(filtered_payload(), product)
    assert len(batch.stations) == 1
    station = batch.stations[0]
    assert station.latitude == 35.894056
    assert station.longitude == -5.322917
    assert station.postal_code == "51001"
    assert station.prices == (FuelPrice(product, Decimal("1.698")),)
    assert batch.source.reported_at == datetime(2026, 9, 25, 20, 27, 10)
    assert batch.source.raw_reported_at == "25/09/2026 20:27:10"
    assert batch.source.note is not None


def test_valid_empty_filtered_result() -> None:
    batch = parse_product_stations(
        filtered_payload("miteco_ceuta_empty_product.json"), products()[0]
    )
    assert batch.stations == ()
    assert batch.source.reported_at is not None


@pytest.mark.parametrize("value", ["", None])
def test_synthetic_missing_or_empty_filtered_price(value: object) -> None:
    payload = filtered_payload()
    payload["ListaEESSPrecio"][0]["PrecioProducto"] = value
    assert parse_product_stations(payload, products()[0]).stations[0].prices == ()


def test_synthetic_absent_filtered_price() -> None:
    payload = filtered_payload()
    del payload["ListaEESSPrecio"][0]["PrecioProducto"]
    assert parse_product_stations(payload, products()[0]).stations[0].prices == ()


def test_synthetic_malformed_price_is_explicit_error() -> None:
    payload = filtered_payload()
    payload["ListaEESSPrecio"][0]["PrecioProducto"] = "abc"
    with pytest.raises(MitecoParseError, match="PrecioProducto: malformed decimal"):
        parse_product_stations(payload, products()[0])


@pytest.mark.parametrize("value", ["abc", "91,0", None])
def test_synthetic_malformed_or_missing_coordinate_is_error(value: object) -> None:
    payload = filtered_payload()
    payload["ListaEESSPrecio"][0]["Latitud"] = value
    with pytest.raises(MitecoParseError, match="Latitud"):
        parse_product_stations(payload, products()[0])


def test_synthetic_optional_texts_and_missing_date() -> None:
    payload = filtered_payload()
    row = payload["ListaEESSPrecio"][0]
    row["Rótulo"] = ""
    row["Horario"] = None
    del row["Localidad"]
    del payload["Fecha"]
    batch = parse_product_stations(payload, products()[0])
    station = batch.stations[0]
    assert station.brand is None
    assert station.schedule is None
    assert station.locality is None
    assert batch.source.reported_at is None
    assert batch.source.raw_reported_at is None


def test_synthetic_invalid_date_is_explicit_error() -> None:
    payload = filtered_payload()
    payload["Fecha"] = "yesterday"
    with pytest.raises(MitecoParseError, match="Fecha: invalid value"):
        parse_product_stations(payload, products()[0])


def test_synthetic_additive_price_field_is_ignored_and_counted() -> None:
    payload = general_payload()
    payload["ListaEESSPrecio"][0]["Precio Combustible Nuevo"] = "2,000"
    payload["ListaEESSPrecio"][1]["Precio Combustible Nuevo"] = ""
    batch = parse_general_stations(payload, products())
    assert len(batch.stations) == 2
    assert batch.source.unmapped_fuel_field_count == 1
    assert batch.stations[0].prices[0].price_eur_l == Decimal("1.674")
    assert all(
        price.product.name != "Combustible Nuevo" for price in batch.stations[0].prices
    )


def test_synthetic_malformed_known_general_price_remains_error() -> None:
    payload = general_payload()
    payload["ListaEESSPrecio"][0]["Precio Gasolina 95 E5"] = "abc"
    with pytest.raises(MitecoParseError, match="Precio Gasolina 95 E5"):
        parse_general_stations(payload, products())


def test_synthetic_wrong_station_shape_is_error() -> None:
    payload = general_payload()
    payload["ListaEESSPrecio"][0]["PrecioProducto"] = "1,698"
    with pytest.raises(MitecoParseError, match="filtered price in general response"):
        parse_general_stations(payload, products())


def test_synthetic_non_ok_result_is_error_even_with_empty_list() -> None:
    payload = filtered_payload("miteco_ceuta_empty_product.json")
    payload["ResultadoConsulta"] = "Parametros de entrada incorrectos."
    with pytest.raises(MitecoParseError, match="ResultadoConsulta"):
        parse_product_stations(payload, products()[0])


def test_domain_models_do_not_expose_miteco_keys() -> None:
    batch = parse_product_stations(filtered_payload(), products()[0])
    station = batch.stations[0]
    for external_key in ("IDPovincia", "PrecioProducto", "Longitud (WGS84)"):
        assert not hasattr(station, external_key)
        assert not hasattr(batch.source, external_key)


def test_synthetic_ambiguous_catalog_mapping_is_error() -> None:
    catalog = list(products())
    catalog.append(FuelProduct("other", "Gasoleo A"))
    with pytest.raises(MitecoParseError, match="ambiguous price field"):
        parse_general_stations(general_payload(), catalog)


def test_synthetic_product_context_is_not_inferred_from_price_value() -> None:
    product = FuelProduct("synthetic", "Otro producto")
    batch = parse_product_stations(filtered_payload(), product)
    assert batch.stations[0].prices == (FuelPrice(product, Decimal("1.698")),)


@pytest.mark.parametrize("value", ["0", "-1,2", "1.698"])
def test_synthetic_invalid_nonempty_price_is_error(value: str) -> None:
    payload = filtered_payload()
    payload["ListaEESSPrecio"][0]["PrecioProducto"] = value
    with pytest.raises(MitecoParseError, match="PrecioProducto"):
        parse_product_stations(payload, products()[0])
