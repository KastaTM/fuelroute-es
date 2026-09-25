"""Pure normalization of the two MITECO station shapes and their catalogs."""

import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import cast

from fuelroute.domain.models import (
    FuelPrice,
    FuelProduct,
    Municipality,
    Province,
    SourceMetadata,
    Station,
    StationBatch,
)

_MISSING = object()
_DECIMAL = re.compile(r"-?\d+(?:,\d+)?\Z")


class MitecoParseError(Exception):
    """A response has an unexpected shape or a malformed nonempty value."""


class MitecoResultError(MitecoParseError):
    """MITECO reports a semantic error in an otherwise parseable response."""


def _object(value: object, location: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise MitecoParseError(f"{location}: expected an object with string keys")
    return cast(Mapping[str, object], value)


def _array(value: object, location: str) -> list[object]:
    if not isinstance(value, list):
        raise MitecoParseError(f"{location}: expected an array")
    return cast(list[object], value)


def _text(value: object, location: str, *, required: bool = False) -> str | None:
    if value is _MISSING or value is None:
        result = None
    elif isinstance(value, str):
        result = value.strip() or None
    else:
        raise MitecoParseError(f"{location}: expected text, null, or absence")
    if required and result is None:
        raise MitecoParseError(f"{location}: required text is missing")
    return result


def _required_text(value: object, location: str) -> str:
    result = _text(value, location, required=True)
    assert result is not None
    return result


def _decimal_text(value: object, location: str) -> Decimal | None:
    raw = _text(value, location)
    if raw is None:
        return None
    if _DECIMAL.fullmatch(raw) is None:
        raise MitecoParseError(f"{location}: malformed decimal {raw!r}")
    number = Decimal(raw.replace(",", "."))
    if not number.is_finite() or number <= 0:
        raise MitecoParseError(f"{location}: price must be positive and finite")
    return number


def _coordinate(value: object, location: str, lower: float, upper: float) -> float:
    raw = _required_text(value, location)
    if _DECIMAL.fullmatch(raw) is None:
        raise MitecoParseError(f"{location}: malformed coordinate {raw!r}")
    number = float(raw.replace(",", "."))
    if not lower <= number <= upper:
        raise MitecoParseError(f"{location}: coordinate outside [{lower}, {upper}]")
    return number


def _source(payload: Mapping[str, object]) -> SourceMetadata:
    result = _required_text(
        payload.get("ResultadoConsulta", _MISSING), "ResultadoConsulta"
    )
    if result != "OK":
        raise MitecoResultError(f"ResultadoConsulta: {result}")
    raw_date = _text(payload.get("Fecha", _MISSING), "Fecha")
    reported_at = None
    if raw_date is not None:
        try:
            reported_at = datetime.strptime(raw_date, "%d/%m/%Y %H:%M:%S")
        except ValueError as exc:
            raise MitecoParseError(f"Fecha: invalid value {raw_date!r}") from exc
    return SourceMetadata(
        reported_at=reported_at,
        raw_reported_at=raw_date,
        note=_text(payload.get("Nota", _MISSING), "Nota"),
    )


def parse_products(payload: object) -> tuple[FuelProduct, ...]:
    result = []
    for index, value in enumerate(_array(payload, "products")):
        row = _object(value, f"products[{index}]")
        result.append(
            FuelProduct(
                id=_required_text(row.get("IDProducto", _MISSING), "IDProducto"),
                name=_required_text(
                    row.get("NombreProducto", _MISSING), "NombreProducto"
                ),
                abbreviation=_text(
                    row.get("NombreProductoAbreviatura", _MISSING),
                    "NombreProductoAbreviatura",
                ),
            )
        )
    return tuple(result)


def parse_provinces(payload: object) -> tuple[Province, ...]:
    result = []
    for index, value in enumerate(_array(payload, "provinces")):
        row = _object(value, f"provinces[{index}]")
        result.append(
            Province(
                id=_required_text(row.get("IDPovincia", _MISSING), "IDPovincia"),
                name=_required_text(row.get("Provincia", _MISSING), "Provincia"),
            )
        )
    return tuple(result)


def parse_municipalities(payload: object) -> tuple[Municipality, ...]:
    result = []
    for index, value in enumerate(_array(payload, "municipalities")):
        row = _object(value, f"municipalities[{index}]")
        result.append(
            Municipality(
                id=_required_text(row.get("IDMunicipio", _MISSING), "IDMunicipio"),
                name=_required_text(row.get("Municipio", _MISSING), "Municipio"),
                province_id=_text(row.get("IDProvincia", _MISSING), "IDProvincia"),
            )
        )
    return tuple(result)


def _product_key(name: str) -> str:
    folded = "".join(
        char
        for char in unicodedata.normalize("NFKD", name.casefold())
        if not unicodedata.combining(char)
    )
    words = folded.split()
    if words[-1:] == ["habitual"]:
        words.pop()
    return " ".join(words)


def _product_fields(products: Sequence[FuelProduct]) -> Mapping[str, FuelProduct]:
    fields: dict[str, FuelProduct] = {}
    for product in products:
        key = "Precio " + _product_key(product.name)
        if key in fields:
            raise MitecoParseError(f"catalog: ambiguous price field {key!r}")
        fields[key] = product
    return fields


def _general_prices(
    row: Mapping[str, object], products: Mapping[str, FuelProduct]
) -> tuple[tuple[FuelPrice, ...], set[str]]:
    if "PrecioProducto" in row:
        raise MitecoParseError("station: filtered price in general response")
    result = []
    unmapped = set()
    for field, value in row.items():
        if not field.startswith("Precio "):
            continue
        key = "Precio " + _product_key(field.removeprefix("Precio "))
        product = products.get(key)
        if product is None:
            unmapped.add(field)
            continue
        price = _decimal_text(value, field)
        if price is not None:
            result.append(FuelPrice(product=product, price_eur_l=price))
    return tuple(result), unmapped


def _filtered_prices(
    row: Mapping[str, object], product: FuelProduct
) -> tuple[tuple[FuelPrice, ...], set[str]]:
    if any(key.startswith("Precio ") for key in row):
        raise MitecoParseError("station: general prices in filtered response")
    price = _decimal_text(row.get("PrecioProducto", _MISSING), "PrecioProducto")
    prices = () if price is None else (FuelPrice(product=product, price_eur_l=price),)
    return prices, set()


def _station(row: Mapping[str, object], prices: tuple[FuelPrice, ...]) -> Station:
    return Station(
        id=_required_text(row.get("IDEESS", _MISSING), "IDEESS"),
        brand=_text(row.get("Rótulo", _MISSING), "Rótulo"),
        address=_text(row.get("Dirección", _MISSING), "Dirección"),
        locality=_text(row.get("Localidad", _MISSING), "Localidad"),
        municipality=_text(row.get("Municipio", _MISSING), "Municipio"),
        province=_text(row.get("Provincia", _MISSING), "Provincia"),
        municipality_id=_text(row.get("IDMunicipio", _MISSING), "IDMunicipio"),
        province_id=_text(row.get("IDProvincia", _MISSING), "IDProvincia"),
        postal_code=_text(row.get("C.P.", _MISSING), "C.P."),
        latitude=_coordinate(row.get("Latitud", _MISSING), "Latitud", -90, 90),
        longitude=_coordinate(
            row.get("Longitud (WGS84)", _MISSING), "Longitud (WGS84)", -180, 180
        ),
        schedule=_text(row.get("Horario", _MISSING), "Horario"),
        prices=prices,
    )


def _stations(
    payload: object,
    prices_for: Callable[
        [Mapping[str, object]], tuple[tuple[FuelPrice, ...], set[str]]
    ],
) -> StationBatch:
    root = _object(payload, "stations")
    source = _source(root)
    stations = []
    unmapped_fields: set[str] = set()
    for index, value in enumerate(
        _array(root.get("ListaEESSPrecio", _MISSING), "ListaEESSPrecio")
    ):
        row = _object(value, f"ListaEESSPrecio[{index}]")
        try:
            prices, unmapped = prices_for(row)
            unmapped_fields.update(unmapped)
            stations.append(_station(row, prices))
        except MitecoParseError as exc:
            raise MitecoParseError(f"ListaEESSPrecio[{index}]: {exc}") from exc
    return StationBatch(
        stations=tuple(stations),
        source=replace(source, unmapped_fuel_field_count=len(unmapped_fields)),
    )


def parse_general_stations(
    payload: object, products: Sequence[FuelProduct]
) -> StationBatch:
    """Resolve all official price fields against the supplied product catalog."""
    fields = _product_fields(products)
    return _stations(payload, lambda row: _general_prices(row, fields))


def parse_product_stations(payload: object, product: FuelProduct) -> StationBatch:
    """Bind PrecioProducto to the product used by the caller's filter."""
    return _stations(payload, lambda row: _filtered_prices(row, product))
