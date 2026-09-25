# MITECO: contrato observado en el spike de Fase 0

Consulta real el 25/09/2026 desde Python con `uv run --locked python scripts/miteco_spike.py`, usando `urllib.request.urlopen` y timeout de 15 s:

`GET https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/EstacionesTerrestres/FiltroProvincia/51`

Resultado: HTTP 200, `ResultadoConsulta: "OK"`, `Fecha: "25/09/2026 19:15:43"`, 10 estaciones. No se versionó el cuerpo completo. El fixture [miteco_ceuta.json](../backend/tests/fixtures/miteco_ceuta.json) conserva dos registros y once campos por estación, extraídos de esa respuesta sin inventar valores ni normalizarlos. Incluye precio no disponible como cadena vacía. El script imprime status, claves y recuento sin volcar el dataset.

## Esquema observado

- Objeto raíz con `Fecha`, `ListaEESSPrecio`, `Nota`, `ResultadoConsulta`.
- `ListaEESSPrecio` es una lista de objetos. Las claves incluyen acentos, espacios, paréntesis y porcentajes, por ejemplo `Rótulo`, `Dirección`, `Longitud (WGS84)`, `Precio Gasolina 95 E5`, `% Éster metílico`.
- `IDEESS` es texto (`"2754"`); precios y coordenadas son texto con coma decimal: `"1,674"`, `"35,889972"`, `"-5,319444"`.
- `Precio Gasolina 98 E10` fue `""` en las dos estaciones conservadas. Un campo vacío no equivale a precio cero.
- `Horario` es texto libre, por ejemplo `L-V: 07:00-22:00; S: 09:00-14:00` o `L-D: 24H`.
- `Fecha` llegó en formato `dd/mm/yyyy HH:MM:SS` a nivel de respuesta. El spike no estableció zona horaria ni fecha por estación.
- Otras claves observadas en la primera estación: `C.P.`, `Localidad`, `Margen`, `Remisión`, `Tipo Venta`, `IDMunicipio`, `IDProvincia`, `IDCCAA` y numerosos `Precio ...`.

## Pendiente para Fase 1

Confirmar semántica y zona horaria de `Fecha`; distinguir ausencia, vacío y valores malformados; validar rangos de coordenadas; mapear productos mediante `Listados/ProductosPetroliferos/`; confirmar frecuencia de actualización, límites de uso, licencia y comportamiento ante caída o esquema cambiante. El script no es un proveedor ni un parser de producción. Repetir la consulta periódicamente fuera del CI obligatorio y comparar el esquema antes de integrar.

Documentación oficial: <https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/help>.
