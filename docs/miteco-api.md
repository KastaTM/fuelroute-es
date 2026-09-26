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

## Investigación contractual de Fase 1, incremento 1 — 25/09/2026

Esta sección separa la documentación oficial de las respuestas medidas. Se usó únicamente `https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/`, peticiones GET con `Accept: application/json`, `urllib.request.urlopen`, timeout explícito de 15 s y lectura resumida en memoria. Las observaciones se hicieron entre las 18:25:50 y las 18:27:35 UTC. No se consultó de nuevo el conjunto nacional. Los catálogos proporcionaron los ID usados en los filtros: provincia CEUTA `IDPovincia="51"`, municipio Ceuta `IDMunicipio="8110"`, Gasolina 95 E5 `IDProducto="1"` e Hidrógeno `IDProducto="22"`.

### Operaciones y formas

| Endpoint lógico | Documentado por MITECO | Observado en esta investigación |
| --- | --- | --- |
| `EstacionesTerrestres/` | GET, objeto con `Fecha`, `ListaEESSPrecio`, `Nota`, `ResultadoConsulta`; cada estación lleva muchos campos `Precio …`. [Referencia oficial](https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/help/operations/PreciosEESSTerrestres). | No se consultó: la muestra de provincia de Fase 0 resuelve la forma general sin descargar el conjunto nacional. |
| `Listados/ProductosPetroliferos/` | Array JSON de `IDProducto`, `NombreProducto`, `NombreProductoAbreviatura`; los campos son cadenas en el esquema XML. [Referencia oficial](https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/help/operations/ProductosPetroliferos). | HTTP 200, `application/json; charset=utf-8`, array de 30; primera entrada Gasolina 95 E5, ID `"1"`, abreviatura `G95E5`. No tiene `Fecha`, `Nota` ni `ResultadoConsulta`. |
| `Listados/Provincias/` | Array JSON; la clave oficial del ID está escrita `IDPovincia` (sin `r`), además de `IDCCAA`, `Provincia`, `CCAA`. [Referencia oficial](https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/help/operations/Provincias). | HTTP 200, mismo content type, array de 52. Primer `IDPovincia="02"`; CEUTA tiene `"51"`. Los ID son texto y pueden conservar ceros iniciales. |
| `Listados/Municipios/` | Array JSON de `IDMunicipio`, `IDProvincia`, `IDCCAA`, `Municipio`, `Provincia`, `CCAA`. [Referencia oficial](https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/help/operations/Municipios). | No se consultó el catálogo completo: el filtro por provincia bastó para obtener un ID real sin una descarga amplia. |
| `Listados/MunicipiosPorProvincia/{IDProvincia}` | Mismo tipo de array municipal. [Referencia oficial](https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/help/operations/MunicipiosPorProvincia). | `/51`: HTTP 200, mismo content type, array de 1: Ceuta, `IDMunicipio="8110"`, `IDProvincia="51"`. |
| `EstacionesTerrestres/FiltroProvincia/{IDProvincia}` y `FiltroMunicipio/{IDMunicipio}` | Objeto de estaciones con campos de precio específicos por combustible. [Provincia](https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/help/operations/PreciosEESSTerrestresFiltroProvincia), [municipio](https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/help/operations/PreciosEESSTerrestresFiltroMunicipio). | Provincia `/51`: 10 estaciones en el spike de Fase 0. Municipio `/8110`: HTTP 200, mismo content type, 10 estaciones, `ResultadoConsulta="OK"`, `Fecha="25/09/2026 20:25:51"`; primera estación con `Precio Gasolina 95 E5="1,698"`, `Latitud="35,894056"`, `Longitud (WGS84)="-5,322917"`, `IDEESS="2755"`. |
| `EstacionesTerrestres/FiltroProvinciaProducto/{IDProvincia}/{IDProducto}` y `FiltroMunicipioProducto/{IDMunicipio}/{IDProducto}` | Objeto de igual envoltura, pero el registro usa `PrecioProducto` y omite los múltiples campos `Precio …`; el esquema XML es `EESSPrecioFiltroProducto`. [Provincia y producto](https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/help/operations/PreciosEESSTerrestresFiltroProvinciaProducto), [municipio y producto](https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/help/operations/PreciosEESSTerrestresFiltroMunicipioProducto). | `/51/1` y `/8110/1`: HTTP 200, mismo content type, 10 estaciones en cada respuesta; primera con `PrecioProducto="1,698"` y sin campos de precio por combustible. `ResultadoConsulta="OK"`. [Fixture de producto](../backend/tests/fixtures/miteco_ceuta_product.json). |
| `FiltroMunicipioProducto/8110/22` | Misma operación filtrada por producto. | HTTP 200, mismo content type, `ListaEESSPrecio=[]`, `ResultadoConsulta="OK"`, `Fecha` y `Nota` presentes. [Fixture vacío](../backend/tests/fixtures/miteco_ceuta_empty_product.json). |
| `FiltroMunicipio/999999` | La referencia documenta el parámetro, pero no fija aquí la semántica de un ID inválido. | HTTP 400 con cuerpo JSON de las cuatro claves: lista vacía y `ResultadoConsulta="Parametros de entrada incorrectos."`. Es un error de parámetros, distinto de una consulta válida sin coincidencias. |

### Implicaciones para el siguiente diseño

- **Documentado:** En los esquemas XML de estaciones y catálogos, los campos individuales son `minOccurs="0"` y `nillable="true"`. Esto permite ausencia o nulo en el contrato XML; los ejemplos JSON no garantizan cómo se serializa cada caso. **Observado:** los registros capturados traían cadenas, y los precios sin valor en el fixture de Fase 0 eran `""`. El parser futuro debe distinguir ausencia, `null`, vacío, precio válido y dato malformado; ninguno debe convertirse automáticamente en cero.
- **Documentado frente a observado:** los ejemplos JSON generados usan nombres XML escapados, como `Longitud_x0020__x0028_WGS84_x0029_` y `Precio_x0020_Gasolina_x0020_95_x0020_E5`. Las respuestas reales y el fixture tienen `Longitud (WGS84)` y `Precio Gasolina 95 E5`. No derivar nombres de clave exclusivamente del ejemplo generado.
- **Observado:** ID de estación, municipio, provincia y producto son texto; `IDPovincia` es la clave real del catálogo provincial, mientras una estación usa `IDProvincia`. Precio y coordenadas emplean coma decimal, y longitud oeste negativa. `Fecha` aparece en la envoltura, no en cada estación; la zona horaria no está especificada en la referencia. No inferir UTC a partir del reloj local de la respuesta.
- **Observado:** `Nota` afirma que los precios se actualizan cada media hora. No es una prueba de frescura efectiva de cada estación ni define una política de caché. En las respuestas capturadas el texto de `Nota` contiene mojibake (`actualizaciÃ³n`); el fixture conserva exactamente ese texto recibido. Evitar usar `Nota` como campo de control o corregir silenciosamente los datos de origen.
- **Inferencia de diseño:** `PrecioProducto` solo se puede asociar al combustible solicitado conservando el `IDProducto` de la petición; la respuesta no lo identifica por registro. El catálogo incluye productos marítimos y de aviación, por lo que no todos sus 30 elementos son necesariamente relevantes para estaciones terrestres. El nombre `Gasóleo A habitual` del catálogo tampoco coincide literalmente con la clave `Precio Gasoleo A` de estaciones. Se requiere un mapeo explícito y comprobado.
- **Observado:** `ResultadoConsulta="OK"` significa que la consulta fue aceptada, incluso con cero estaciones. Para distinguir error, usar también el HTTP status y validar tipo y contenido de la lista; un ID inválido produjo HTTP 400 y texto de error en `ResultadoConsulta`.

Los dos fixtures nuevos conservan la envoltura real, origen y hora de captura UTC. El de producto conserva todos los campos de la primera estación y recorta únicamente las otras nueve filas; el vacío conserva la respuesta completa. No sustituyen el fixture de Fase 0, que sigue representando una respuesta con varios precios y un precio vacío. Las llamadas en vivo siguen fuera de los tests y de CI.

**Pendiente antes de implementar parser, provider o caché:** decidir el contrato interno para precio no disponible y estación con coordenadas inválidas; probar ausencia/`null`/valor malformado con fixtures sintéticos claramente etiquetados, ya que no se observaron en estas respuestas reales; definir el mapeo producto–campo y unidades; decidir cómo exponer el tiempo global y la antigüedad sin asumir zona horaria; acordar política de errores, resultados vacíos y datos de caché antiguos. Ninguna de estas decisiones se implementa en este incremento.

## Frontera pura de dominio y normalización — Fase 1, incremento 2

El parser de `backend/fuelroute/providers/miteco/parser.py` recibe JSON ya decodificado y devuelve modelos internos de `backend/fuelroute/domain/models.py`. No accede a la red ni al reloj. El provider HTTP del Incremento 3 asume status, timeout y recuperación de datos.

- **Catálogos:** el [fixture de catálogos](../backend/tests/fixtures/miteco_catalogs.json) se capturó el 25/09/2026 a las 18:38:38 UTC mediante tres GET oficiales, con timeout de 15 s y HTTP 200. Conserva los 30 productos del catálogo pequeño completo, solo las provincias de ID textual `"02"` y `"51"` entre 52, y el municipio único de la provincia 51. Los tests leen el fixture sin red.
- **Precios generales:** el parser elimina `Precio ` del nombre de cada campo y busca el producto por nombre del catálogo oficial, normalizando mayúsculas, espacios y acentos. La única equivalencia adicional observada es quitar el sufijo `habitual` de `Gasóleo A habitual` para resolver `Precio Gasoleo A`. Los IDs se toman del catálogo y permanecen como texto; no hay tabla de IDs ministeriales fija. En el Incremento 2, un campo `Precio …` desconocido producía `MitecoParseError`; el Incremento 3 revisa esa política para tolerar ampliaciones aditivas. Una correspondencia ambigua sigue produciendo error.
- **Precios filtrados:** `parse_product_stations` exige el `FuelProduct` usado por la petición. Asocia `PrecioProducto` exclusivamente a ese producto; la fila ministerial no lo identifica.
- **Valores:** precios se convierten a `Decimal` en EUR/litro. Campo ausente, `null` o cadena vacía significa precio no disponible y no crea `FuelPrice`; texto no vacío inválido, cero o negativo produce error explícito. Coordenadas se convierten a `float` y se comprueban contra los rangos de latitud y longitud; ausencia, texto inválido y fuera de rango producen error. IDs oficiales no se convierten a enteros, para conservar ceros iniciales.
- **Fecha y frescura:** `Fecha` global válida se conserva como texto original y como `datetime` **sin zona horaria**. Ausencia, `null` o vacío deja ambos campos sin valor; fecha no vacía inválida produce error. `Nota` se conserva sin corregir. El parser no infiere hora UTC ni frescura por estación.
- **Resultado:** una lista de estaciones vacía con `ResultadoConsulta="OK"` es un resultado válido vacío. Un valor distinto de `OK`, una lista ausente o un tipo inesperado produce `MitecoParseError`. El status HTTP será responsabilidad del provider futuro.

Los casos malformados de los tests son **mutaciones sintéticas** de fixtures reales, nunca observaciones atribuidas a MITECO. Esta decisión deja explícita la separación `MITECO response -> parser/normalizer -> internal domain models`.

## Provider HTTP y evolución aditiva — Fase 1, incremento 3

`FuelPriceProvider` es un protocolo síncrono propio para productos, provincias, municipios (generales o de una provincia), estaciones generales y estaciones filtradas por municipio y producto. La implementación MITECO usa un `httpx.Client` inyectado cuyo ciclo de vida gestiona quien compone la aplicación. El backend existente usa un endpoint FastAPI síncrono; la futura integración puede llamar este provider desde un endpoint síncrono sin bloquear el event loop. `httpx` ya existía en el lockfile y se declara ahora como dependencia runtime, sin añadir un paquete nuevo.

El provider consulta el catálogo oficial antes de normalizar una respuesta general de estaciones; por ahora son dos peticiones por operación compuesta. Para el filtro por municipio y producto recibe un `FuelProduct` y lo conserva como contexto de `PrecioProducto`. No hay caché ni retries. Timeout positivo y finito configurable por petición; la futura capa de caché podrá envolver el protocolo sin importar MITECO ni `httpx`.

Errores públicos: `ProviderTimeoutError` y `ProviderUnavailableError` para indisponibilidad; `ProviderHTTPError` con `status_code`; `ProviderInvalidJSONError`, `ProviderSchemaError` y `ProviderSemanticError` para respuestas inválidas. Son subclases de `FuelPriceProviderError` y conservan la operación. No incorporan cuerpos HTTP. Un HTTP 200 con `ResultadoConsulta != "OK"` es error semántico; `OK` con lista vacía es éxito.

La revisión del parser detectó que antes cualquier campo nuevo `Precio …` no resuelto contra el catálogo abortaba el dataset completo. Ahora esos campos se omiten **sin asignarlos a otro combustible** y se publica su número de nombres distintos en `SourceMetadata.unmapped_fuel_field_count`. Un precio conocido malformado, una correspondencia ambigua o una estructura incompatible siguen fallando. Esto permite detectar la ampliación aditiva y aprovechar los combustibles ya conocidos. La zona horaria de `Fecha` sigue sin establecerse.

## Incremento 4: caché del provider

`CachingFuelPriceProvider` es un decorador en memoria de `FuelPriceProvider` y no conoce HTTP, URLs ni JSON de MITECO. Se configura al construirlo con `fresh_ttl` (10 minutos por defecto), `max_stale_age` (30 minutos por defecto) y un reloj `now` inyectable. Los intervalos usan `timedelta`; el TTL debe ser positivo y la edad máxima no puede ser inferior al TTL. La futura composición de la API podrá pasar estos valores al constructor. No se añadió configuración de entorno antes de tener un punto de composición.

Cada operación tiene una clave independiente: productos, provincias y estaciones generales son únicas; municipios distingue la consulta general de cada `province_id`; las estaciones filtradas incluyen `municipality_id` y los campos `id`, `name` y `abbreviation` del producto. Así un catálogo renombrado no recupera un lote con etiquetas antiguas. También se cachean resultados vacíos válidos.

`ProviderResult.value` contiene el dato. `ProviderResult.freshness` contiene `fetched_at` (UTC consciente de zona), `age` y `state` (`miss`, `hit`, `refreshed` o `stale`) cuando se usa el decorador; el provider MITECO sin decorador deja `freshness=None`. La `Fecha` comunicada por MITECO permanece en `StationBatch.source`, sin asignarle una zona horaria desconocida. Un hit conserva el `fetched_at` original. Una entrada con edad igual al TTL sigue fresca; al superarlo se intenta siempre refrescar. Un refresh correcto sustituye el valor y reinicia la edad. Un fallback stale conserva el timestamp y vuelve a intentar refresh en la siguiente consulta.

El fallback stale solo procede si ya había entrada, su edad al terminar el intento no supera `max_stale_age` y el fallo es `ProviderTimeoutError`, `ProviderUnavailableError`, HTTP 408, 429 o 5xx. HTTP 4xx ordinario, JSON inválido, errores de esquema, `ProviderSemanticError` y errores desconocidos se propagan. El error semántico actual indica una consulta fallida según el payload y no hay evidencia suficiente para tratarlo como transitorio. Sin entrada, o con una demasiado antigua, se propaga el fallo original.

La caché desaparece al reiniciar y cada proceso o worker tiene la suya; no hay coherencia distribuida. Esto basta para el MVP de Fase 1 y evita añadir SQLite o infraestructura. Un `Lock` protege lecturas y escrituras del diccionario, pero no se mantiene durante la llamada al provider. Dos misses concurrentes pueden duplicar trabajo; no hay coalescing.

En un hit de estaciones generales no se llama a MITECO. En un miss o refresh, `MitecoFuelPriceProvider.get_stations()` vuelve a obtener el catálogo de productos antes de normalizar el lote. Distintas claves de estaciones pueden repetir esa consulta interna porque el decorador no puede reutilizarla sin acoplarse a detalles del provider; queda como posible optimización posterior.

## Integración HTTP mínima — Fase 1, incremento 5

`backend/app.py` crea un único `httpx.Client` por proceso en el lifespan de FastAPI, lo entrega a `MitecoFuelPriceProvider` y envuelve este en `CachingFuelPriceProvider`. El cliente se cierra al apagar la aplicación. La dependencia `get_provider` permite sustituir el provider en tests sin consultar MITECO. La URL oficial permanece fija en el módulo MITECO; el timeout de 15 s y los intervalos de caché de 10/30 min proceden de los defaults validados de sus constructores. No hay configuración de entorno ni dependencia nueva.

`GET /fuels`, `GET /provinces` y `GET /municipalities` exponen solo campos normalizados de FuelRoute dentro de `items`; este último acepta opcionalmente un `province_id` textual de dígitos, conservando ceros iniciales. `freshness` informa del instante de obtención UTC, edad en segundos, estado de caché y si es stale. Un fallback stale válido sigue siendo HTTP 200. La `Fecha` de MITECO no se usa como timestamp de caché.

La API traduce indisponibilidad, timeout y HTTP upstream 408/429/5xx a 503; respuestas inválidas, errores semánticos y otros 4xx upstream a 502. Los cuerpos de error son fijos y no contienen rutas ni mensajes ministeriales. `/health` permanece independiente del provider.

Las estaciones ya se obtienen y normalizan en pruebas internas, pero todavía no tienen rutas HTTP. `/stations/nearby` pertenece a Fase 2; publicar ahora búsqueda o detalle no aporta evidencia necesaria para cerrar Fase 1 y fijaría contratos prematuramente. La Fase 1 sigue en curso.
