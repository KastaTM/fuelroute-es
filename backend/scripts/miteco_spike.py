"""One-off, opt-in contract probe. Never part of the normal test suite."""

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = (
    "https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/"
    "PreciosCarburantes/EstacionesTerrestres/FiltroProvincia/51"
)
FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "miteco_ceuta.json"
)
FIELDS = (
    "IDEESS",
    "Rótulo",
    "Dirección",
    "Municipio",
    "Provincia",
    "Latitud",
    "Longitud (WGS84)",
    "Precio Gasolina 95 E5",
    "Precio Gasoleo A",
    "Precio Gasolina 98 E10",
    "Horario",
)


def main() -> int:
    request = Request(
        URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "FuelRouteES-phase0-spike/1",
        },
    )
    print(f"GET {URL} (timeout=15s)")
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            payload = json.load(response)
    except HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.reason}", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"Request or JSON error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    top_keys = list(payload) if isinstance(payload, dict) else "not an object"
    print(f"HTTP {status}; top-level keys: {top_keys}")
    if not isinstance(payload, dict):
        return 1
    rows = payload.get("ListaEESSPrecio")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        print("No representative station rows; no fixture written", file=sys.stderr)
        return 1
    print(f"station count: {len(rows)}; station keys: {list(rows[0])}")
    fecha = payload.get("Fecha")
    resultado = payload.get("ResultadoConsulta")
    print(f"fecha: {fecha!r}; resultado: {resultado!r}")
    selected = [{key: row.get(key) for key in FIELDS if key in row} for row in rows[:2]]
    fixture = {
        "source": URL,
        "observed_fecha": payload.get("Fecha"),
        "stations": selected,
    }
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"fixture: {FIXTURE.relative_to(Path.cwd())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
