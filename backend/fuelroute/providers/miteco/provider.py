"""Synchronous MITECO HTTP provider; its client lifecycle belongs to the caller."""

import math
import re
from collections.abc import Callable
from typing import TypeVar, cast

import httpx

from fuelroute.domain.models import FuelProduct, Municipality, Province, StationBatch
from fuelroute.providers.base import (
    ProviderHTTPError,
    ProviderInvalidJSONError,
    ProviderSchemaError,
    ProviderSemanticError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from fuelroute.providers.miteco.parser import (
    MitecoParseError,
    MitecoResultError,
    parse_general_stations,
    parse_municipalities,
    parse_product_stations,
    parse_products,
    parse_provinces,
)

BASE_URL = (
    "https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/"
)
_ID = re.compile(r"[0-9]+\Z")
T = TypeVar("T")


def _id_segment(value: str) -> str:
    if _ID.fullmatch(value) is None:
        raise ValueError("official ID must contain only ASCII digits")
    return value


class MitecoFuelPriceProvider:
    """Normalize official responses through an injected, caller-owned HTTP client."""

    def __init__(self, client: httpx.Client, *, timeout: float = 15.0) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        self._client = client
        self._timeout = timeout

    def _get_json(self, path: str) -> object:
        try:
            response = self._client.get(
                BASE_URL + path,
                headers={"Accept": "application/json"},
                timeout=self._timeout,
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(path, "request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(path, "request failed") from exc
        if not 200 <= response.status_code < 300:
            raise ProviderHTTPError(path, response.status_code)
        try:
            return cast(object, response.json())
        except ValueError as exc:
            raise ProviderInvalidJSONError(path, "invalid JSON") from exc

    def _load(self, path: str, parser: Callable[[object], T]) -> T:
        payload = self._get_json(path)
        try:
            return parser(payload)
        except MitecoResultError as exc:
            raise ProviderSemanticError(path, str(exc)[:160]) from exc
        except MitecoParseError as exc:
            raise ProviderSchemaError(path, str(exc)[:160]) from exc

    def get_products(self) -> tuple[FuelProduct, ...]:
        return self._load("Listados/ProductosPetroliferos/", parse_products)

    def get_provinces(self) -> tuple[Province, ...]:
        return self._load("Listados/Provincias/", parse_provinces)

    def get_municipalities(
        self, province_id: str | None = None
    ) -> tuple[Municipality, ...]:
        path = (
            "Listados/Municipios/"
            if province_id is None
            else f"Listados/MunicipiosPorProvincia/{_id_segment(province_id)}"
        )
        return self._load(path, parse_municipalities)

    def get_stations(self) -> StationBatch:
        products = self.get_products()
        return self._load(
            "EstacionesTerrestres/",
            lambda payload: parse_general_stations(payload, products),
        )

    def get_stations_for_municipality_product(
        self, municipality_id: str, product: FuelProduct
    ) -> StationBatch:
        path = (
            "EstacionesTerrestres/FiltroMunicipioProducto/"
            f"{_id_segment(municipality_id)}/{_id_segment(product.id)}"
        )
        return self._load(
            path, lambda payload: parse_product_stations(payload, product)
        )
