# PROJECT_CONTEXT.md — FuelRoute ES

> **Estado:** Documento maestro de contexto del proyecto  
> **Nombre provisional:** FuelRoute ES  
> **Tipo de proyecto:** Aplicación móvil personal para localizar y comparar gasolineras  
> **Mercado inicial:** España  
> **Objetivo principal:** Encontrar de forma rápida la gasolinera más conveniente para repostar teniendo en cuenta precio, ubicación, vehículo, consumo y autonomía disponible.

---

## 1. Visión del proyecto

FuelRoute ES será una aplicación móvil personal cuyo propósito principal será responder a una pregunta muy concreta:

> **“¿Dónde me conviene repostar ahora mismo?”**

La aplicación no debe limitarse a ordenar gasolineras por el precio nominal del combustible. Debe tener en cuenta el contexto real del usuario:

- Ubicación actual.
- Tipo de combustible del vehículo.
- Consumo medio del vehículo.
- Autonomía restante.
- Distancia hasta cada estación.
- Litros que se desean repostar.
- Precio actual del combustible.
- En fases posteriores, distancia real por carretera, desvío y coste de desplazarse hasta la estación.

El objetivo es que, con pocos toques, el usuario pueda localizar una estación adecuada y abrir inmediatamente la navegación hasta ella.

---

## 2. Problema que resuelve

Buscar manualmente gasolineras baratas tiene varios inconvenientes:

1. El precio por litro no refleja necesariamente qué opción es económicamente mejor.
2. Una estación muy barata puede estar demasiado lejos.
3. El usuario puede no disponer de suficiente autonomía para llegar.
4. Hay que alternar entre buscadores, mapas y páginas de precios.
5. Normalmente el usuario conduce siempre el mismo vehículo, por lo que repetir combustible y consumo en cada búsqueda es innecesario.
6. Cuando se busca en una zona concreta también es útil poder filtrar directamente por municipio y combustible.

FuelRoute ES centralizará estas decisiones.

---

## 3. Fuente principal de datos

La fuente primaria debe ser el servicio oficial de precios de carburantes del Gobierno de España / Ministerio para la Transición Ecológica y el Reto Demográfico.

### Fuentes oficiales

Geoportal:
https://geoportalgasolineras.es/

Servicio REST:
https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/

Documentación REST:
https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/help

Portal de Datos Abiertos MITECO:
https://catalogo.datosabiertos.miteco.gob.es/

### Principios

- No realizar scraping de webs de terceros si el dato existe en la fuente oficial.
- Crear un adaptador propio entre la API oficial y nuestro dominio.
- Nunca acoplar la interfaz móvil directamente al formato extraño de los campos del Ministerio.
- Normalizar precios, coordenadas, combustible, horarios y nombres de campos.
- Mantener una capa de caché para no descargar continuamente el dataset completo.
- Mostrar siempre la fecha/hora de actualización del dato cuando esté disponible.
- Indicar claramente que el precio puede haber cambiado antes de la llegada del usuario.

### Particularidades esperadas de los datos

La API oficial utiliza nombres de campos no especialmente cómodos para programación y algunos valores numéricos pueden llegar como texto y con coma decimal.

Por ello debe existir una capa:

`MITECO response -> parser/normalizer -> Station domain model`

Nunca debe propagarse el JSON original del Ministerio por toda la aplicación.

---

## 4. Producto de referencia

Web de referencia funcional:

https://www.gasoapp.es/

GasoApp servirá como inspiración, no como especificación que haya que copiar.

Funcionalidades interesantes observadas:

- Búsqueda por provincia/localidad/GPS.
- Selección de combustible.
- Comparación de precio y distancia.
- Cálculo orientativo del coste.
- Planificación de ruta.
- Autonomía.
- Desvío máximo.
- Gasolineras favoritas.
- Historial.
- Comparación entre estaciones.
- Registro de repostajes.

FuelRoute ES debe empezar siendo bastante más pequeño y centrarse en el caso de uso principal.

---

# 5. Alcance del MVP

## 5.1 Funcionalidad principal: “Buscar cerca de mí”

El usuario pulsa un botón similar a:

**Buscar gasolineras cerca de mí**

Flujo:

1. La aplicación solicita permiso de ubicación.
2. Obtiene latitud y longitud.
3. Utiliza el combustible configurado en el vehículo activo.
4. Opcionalmente pregunta:
   - autonomía actual en km;
   - litros que se quieren repostar.
5. Consulta las estaciones candidatas.
6. Descarta las estaciones sin precio para el combustible seleccionado.
7. Descarta las que excedan el radio máximo.
8. Si se indicó autonomía, identifica las estaciones que quedan fuera del margen incluso en línea recta y marca las demás como posiblemente alcanzables hasta comprobar una ruta real.
9. Calcula:
   - precio por litro;
   - distancia aproximada;
   - coste del repostaje;
   - coste aproximado de desplazarse hasta la estación;
   - coste económico estimado total.
10. Devuelve una lista ordenable.
11. El usuario selecciona una estación.
12. Puede abrir la navegación hasta ella en Google Maps.

### Ordenaciones mínimas

- Recomendado.
- Precio por litro.
- Distancia.
- Coste estimado total.

El sistema no debe ocultar cómo se toma la decisión. Se mostrarán las métricas relevantes para que el usuario pueda elegir.

---

## 5.2 Gestión del vehículo

Debe existir al menos un vehículo guardado.

Campos iniciales:

- `id`
- Nombre o alias, por ejemplo `Mi coche`.
- Marca — opcional.
- Modelo — opcional.
- Año — opcional.
- Combustible principal.
- Consumo medio en `L/100 km`.
- Capacidad del depósito en litros — opcional.
- Vehículo activo — booleano.

### Combustible

El combustible se seleccionará de los productos disponibles en la fuente oficial.

No debemos depender permanentemente de IDs hardcodeados del Ministerio. Siempre que sea razonable, la aplicación/backend debe recuperar y mapear el listado oficial de productos.

---

## 5.3 Autonomía

Antes de realizar una búsqueda cercana, el usuario podrá introducir opcionalmente:

`Autonomía restante: ___ km`

La app tendrá un margen de seguridad configurable.

Ejemplo:

- autonomía introducida: 40 km;
- reserva de seguridad: 20 %;
- autonomía utilizable: 32 km.

Si la distancia en línea recta supera la autonomía utilizable, marcar la estación como fuera del margen. Si no la supera, indicar que su alcance es provisional y debe comprobarse con la distancia real de conducción.

### MVP

En la primera implementación se puede utilizar distancia geodésica/Haversine para el prefiltrado. Un factor conservador no convierte esta distancia en una garantía de alcance.

### Futuro

Sustituir la aproximación por distancia real de conducción.

---

## 5.4 Búsqueda manual

Debe existir también:

**Buscar por municipio**

Filtros:

- Provincia.
- Municipio.
- Tipo de combustible.

Opcionales posteriores:

- Marca/rótulo.
- Abierta ahora.
- Radio máximo.
- Precio máximo.
- Solo favoritas.

Resultados:

- Nombre/rótulo.
- Dirección.
- Municipio.
- Precio.
- Horario.
- Distancia, si se dispone de ubicación.
- Botón de navegación.

---

## 5.6 Dashboard nacional de precios — requisito de producto

La aplicación incluirá una vista sencilla con el precio medio nacional por combustible, fecha y hora de los datos, número de estaciones que aportan un precio válido y una explicación de cómo se calcula la media. En fase 0/1 se decidirá si se calcula a partir del último conjunto de estaciones de la fuente oficial o se consume un agregado oficial que cubra los combustibles elegidos. Si se mezclan fuentes, se mostrarán por separado sus marcas temporales y metodologías. Los combustibles sin suficientes datos se señalarán como no disponibles; no se fabricarán valores ni se presentará como «tiempo real» una publicación retrasada. El dashboard se entregará después del flujo principal de búsqueda y navegación, con pruebas del agregado y de la ausencia de precios.

---

# 6. La métrica importante: coste real

El proyecto debe distinguir dos conceptos.

## Precio nominal

```text
precio_repostaje = litros_a_repostar * precio_por_litro
```

## Coste aproximado de llegar a la estación

Con distancia de desplazamiento `d`:

```text
litros_desplazamiento = d_km * consumo_l_100km / 100
coste_desplazamiento = litros_desplazamiento * precio_referencia
```

## Coste económico estimado

```text
coste_total_estimado =
    precio_repostaje
    + coste_desplazamiento
```

En el MVP, si solo se conoce distancia lineal, este valor deberá indicarse como aproximado.

En una fase avanzada se utilizará distancia de carretera y, preferiblemente, desvío real respecto a la ruta que el usuario estuviera realizando.

---

# 7. Indicador de ahorro

Una funcionalidad muy útil será mostrar algo similar a:

> Ahorras aproximadamente 3,40 € frente a repostar en la estación cercana de referencia.

Esto permite explicar por qué desplazarse 4 km adicionales puede o no compensar.

No se debe recomendar automáticamente recorrer grandes distancias por diferencias mínimas.

Posibles datos mostrados:

- Precio: `1,489 €/L`
- Distancia: `3,2 km`
- Repostaje de 40 L: `59,56 €`
- Desplazamiento estimado: `0,31 €`
- Coste efectivo estimado: `59,87 €`

---

# 8. Diseño funcional inicial

## Pantalla 1 — Inicio

Elementos principales:

- Vehículo activo.
- Combustible.
- Botón grande: `Buscar cerca de mí`.
- Campo opcional: autonomía actual.
- Campo opcional: litros a repostar.
- Acceso a búsqueda por municipio.

---

## Pantalla 2 — Resultados

Cada tarjeta:

- Rótulo.
- Precio.
- Distancia.
- Dirección.
- Horario / abierta ahora si puede determinarse.
- Coste estimado.
- Indicador de ahorro si procede.
- Botón `Ver`.
- Botón `Ir`.

Filtros/orden:

- Recomendado.
- Más barata.
- Más cercana.
- Menor coste efectivo.

---

## Pantalla 3 — Detalle de gasolinera

- Nombre/rótulo.
- Dirección.
- Coordenadas.
- Precio seleccionado.
- Otros combustibles disponibles.
- Horario.
- Distancia.
- Fecha/hora de actualización.
- Coste estimado.
- Botón `Abrir en Google Maps`.
- Favorito — fase posterior.

---

## Pantalla 4 — Mi vehículo

- Alias.
- Marca/modelo.
- Combustible.
- Consumo medio.
- Capacidad de depósito.
- Editar.
- Seleccionar como activo.

---

## Pantalla 5 — Búsqueda manual

- Provincia.
- Municipio.
- Combustible.
- Buscar.

---

# 9. Navegación

Para el MVP no necesitamos construir navegación giro a giro.

Al seleccionar:

**Ir con Google Maps**

la app construirá un enlace con las coordenadas de la estación para abrir Google Maps.

Ventajas:

- Mucho menor alcance técnico.
- No duplicamos navegación.
- No dependemos inicialmente de una API de Directions de pago.
- El usuario obtiene tráfico y navegación real de Google.

Más adelante podremos mostrar ruta y desvío dentro de la propia aplicación.

---

# 10. Arquitectura propuesta

```text
┌──────────────────────────────────┐
│        React Native / Expo       │
│                                  │
│ GPS · UI · vehículo · resultados │
└───────────────┬──────────────────┘
                │ HTTPS / JSON
                ▼
┌──────────────────────────────────┐
│          FastAPI backend         │
│                                  │
│ ranking · filtros · normalización│
│ cache · cálculos · API propia    │
└───────────────┬──────────────────┘
                │
                ▼
┌──────────────────────────────────┐
│       MITECO Fuel REST API       │
│ precios · estaciones · productos │
└──────────────────────────────────┘
```

---

# 11. Stack recomendado

## Mobile

- React Native.
- Expo.
- TypeScript.
- Expo Location.
- Expo Router.
- Persistencia local:
  - inicialmente AsyncStorage o Expo SQLite.
- Tests:
  - Jest.
  - React Native Testing Library.

## Backend

- Python.
- FastAPI.
- Pydantic.
- httpx.
- Uvicorn.
- SQLite para caché/persistencia simple en MVP.
- SQLAlchemy o SQLModel si aparece persistencia relacional relevante.
- pytest.
- Ruff.
- mypy.
- pre-commit opcional.

## DevOps

- GitHub.
- GitHub Actions.
- Docker para backend.
- `.env` y configuración por entorno.
- Dependabot/Renovate opcional.
- Cobertura de tests.

---

# 12. Por qué esta arquitectura

El desarrollador del proyecto tiene experiencia profesional principalmente en Python, SQL, AWS, Spark/PySpark, MLflow y data/ML.

FastAPI permite aprovechar Python para:

- integración con la fuente oficial;
- transformación de datos;
- cálculos geográficos;
- ranking;
- testing;
- posible analítica futura.

React Native + Expo permite construir una aplicación móvil real para Android/iOS con una única base de código sin convertir el backend en una aplicación monolítica.

---

# 13. Modelo de dominio

## Vehicle

```text
Vehicle
- id
- nickname
- make?
- model?
- year?
- fuel_type
- average_consumption_l_100km
- tank_capacity_l?
- is_active
```

## Station

```text
Station
- id
- brand
- address
- municipality
- province
- postal_code
- latitude
- longitude
- schedule
- fuel_prices
- source_updated_at
```

## FuelPrice

```text
FuelPrice
- fuel_type
- price_eur_l
```

## SearchRequest

```text
SearchRequest
- latitude
- longitude
- fuel_type
- radius_km
- autonomy_km?
- safety_reserve_percent?
- liters_to_refuel?
- vehicle_consumption_l_100km
```

## StationResult

```text
StationResult
- station
- price
- distance_km
- reachability_status (posible / fuera de margen / desconocida)
- estimated_refuel_cost?
- estimated_travel_cost?
- estimated_effective_cost?
- estimated_savings?
```

---

# 14. Backend API propia

Endpoints iniciales propuestos:

```text
GET /health

GET /fuels

GET /provinces

GET /municipalities
    ?province_id=

GET /stations/nearby
    ?lat=
    &lon=
    &fuel=
    &radius_km=
    &autonomy_km=
    &consumption_l_100km=
    &liters=

GET /stations/search
    ?municipality_id=
    &fuel=

GET /stations/{station_id}
```

No tienen por qué ser definitivos. Se diseñarán mediante tests y casos de uso antes de estabilizar la API.

---

# 15. Integración MITECO

Endpoints oficiales útiles:

```text
GET EstacionesTerrestres/

GET EstacionesTerrestres/FiltroCCAA/{IDCCAA}

GET EstacionesTerrestres/FiltroCCAAProducto/{IDCCAA}/{IDPRODUCTO}

GET EstacionesTerrestres/FiltroProvincia/{IDProvincia}

GET EstacionesTerrestres/FiltroProvinciaProducto/{IDProvincia}/{IDPRODUCTO}

GET EstacionesTerrestres/FiltroMunicipio/{IDMunicipio}

GET EstacionesTerrestres/FiltroMunicipioProducto/{IDMunicipio}/{IDPRODUCTO}

GET Listados/ComunidadesAutonomas/

GET Listados/Provincias/

GET Listados/Municipios/

GET Listados/MunicipiosPorProvincia/{IDProvincia}

GET Listados/ProductosPetroliferos/
```

También existen endpoints históricos que podrán utilizarse en fases futuras.

---

# 16. Capa de adaptación de datos

Crear una interfaz similar a:

```text
FuelPriceProvider
```

Implementación inicial:

```text
MitecoFuelPriceProvider
```

Responsabilidades:

- descargar información;
- validar respuesta;
- normalizar claves;
- convertir coma decimal;
- transformar coordenadas;
- eliminar precios vacíos;
- mapear productos;
- devolver modelos internos.

Esto permitirá sustituir la fuente o añadir otra sin modificar la app completa.

---

# 17. Caché

La aplicación no debe descargar el dataset nacional completo en cada búsqueda.

Estrategia inicial:

1. Backend mantiene caché.
2. Cada entrada tiene `fetched_at`.
3. Si la información sigue fresca, se reutiliza.
4. Si ha caducado, se solicita de nuevo.
5. Si MITECO falla temporalmente pero existe una caché reciente, se puede devolver el último dato conocido indicando su antigüedad.

TTL inicial recomendado:

```text
5–15 minutos
```

Será configurable.

---

# 18. Geolocalización

La ubicación será sensible y deberá tratarse de forma minimalista.

Principios:

- Pedir permiso únicamente cuando sea necesario.
- Explicar por qué se solicita.
- No almacenar histórico de ubicación en el MVP.
- No guardar coordenadas permanentemente en backend.
- Utilizar ubicación exclusivamente para realizar la consulta.
- Permitir búsqueda manual si se rechaza el permiso.

---

# 19. Cálculo de distancia

## Fase inicial

Usar Haversine entre:

- posición del usuario;
- coordenadas de cada estación.

Ventajas:

- gratis;
- rápido;
- sin API adicional;
- suficiente para prefiltrar candidatos.

Limitación:

La distancia en línea recta no equivale a la distancia por carretera.

Por ello:

- se mostrará como aproximación cuando corresponda;
- podrá aplicarse un factor de seguridad para autonomía;
- no se utilizará como si fuera una distancia de navegación exacta.

## Fase posterior

Evaluar:

- Google Routes API.
- OpenRouteService.
- proveedor alternativo de rutas.

La selección deberá considerar precio, límites de uso, calidad y facilidad de integración.

---

# 20. Ranking

No crear inicialmente un algoritmo opaco.

Propuesta:

### Vista “Más barata”

```text
sort price_per_liter ASC
```

### Vista “Más cercana”

```text
sort distance ASC
```

### Vista “Coste efectivo”

```text
sort estimated_effective_cost ASC
```

### Vista “Recomendado”

En la primera versión puede ser equivalente a `Coste efectivo`.

Si posteriormente se crea una puntuación compuesta, deberá ser interpretable y configurable.

---

# 21. Autonomía y seguridad

No apurar al 100 % la autonomía indicada por el usuario.

Parámetro:

```text
safety_reserve_percent = 20
```

Ejemplo:

```text
usable_autonomy =
    autonomy_km * (1 - safety_reserve_percent / 100)
```

La reserva será modificable.

Una estación podrá tener estados:

- `possibly_reachable`
- `near_limit`
- `not_reachable`
- `unknown`

---

# 22. Persistencia

## MVP

Datos locales en el móvil:

- vehículo;
- preferencias;
- último combustible;
- radio favorito;
- reserva de autonomía.

No es necesario crear cuentas de usuario.

## Futuro

Si se desea sincronización entre dispositivos:

- autenticación;
- base de datos remota;
- favoritos;
- repostajes;
- histórico;
- rutas frecuentes.

No implementar hasta que exista una necesidad real.

---

# 23. Testing

El proyecto debe tener tests desde las primeras fases.

Especial atención a:

- parsing de precios con coma decimal;
- coordenadas;
- campos vacíos;
- combustibles no disponibles;
- cálculo Haversine;
- autonomía;
- reserva de seguridad;
- cálculo del coste;
- ranking;
- fallback de caché;
- respuestas defectuosas de MITECO.

Las llamadas reales a MITECO no deben ser necesarias para ejecutar la mayoría de los tests.

Utilizar fixtures de respuestas reales anonimizadas/recortadas.

---

# 24. Calidad

Objetivo:

- código tipado;
- módulos pequeños;
- separación de responsabilidades;
- tests;
- linters;
- CI;
- documentación de decisiones.

Evitar:

- overengineering;
- microservicios innecesarios;
- Kubernetes;
- infraestructura compleja;
- autenticación antes de necesitarla;
- IA/ML sin un caso real.

Este es primero un producto útil y después un proyecto de portfolio.

---

# 25. Estructura inicial del repositorio

```text
fuelroute-es/
│
├── mobile/
│   ├── app/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── domain/
│   │   ├── hooks/
│   │   ├── storage/
│   │   └── utils/
│   └── tests/
│
├── backend/
│   ├── src/
│   │   └── fuelroute/
│   │       ├── api/
│   │       ├── config/
│   │       ├── domain/
│   │       ├── providers/
│   │       ├── repositories/
│   │       ├── services/
│   │       └── main.py
│   └── tests/
│
├── docs/
│   ├── architecture.md
│   ├── miteco-api.md
│   └── decisions/
│
├── .github/
│   └── workflows/
│
├── PROJECT_CONTEXT.md
├── README.md
├── docker-compose.yml
└── .gitignore
```

---

# 26. Roadmap

## Fase 0 — Bootstrap

Objetivo:

Tener repositorio, tooling y arquitectura mínima funcionando.

Entregables:

- repositorio Git;
- estructura `mobile/backend`;
- FastAPI `/health`;
- app Expo mínima;
- linters;
- tests;
- GitHub Actions;
- README.
- Protección de rama, plantilla de PR y comprobaciones obligatorias definidas y verificadas en cuanto exista el repositorio remoto.

---

## Fase 1 — Investigación e integración MITECO

Objetivo:

Comprender y encapsular completamente la API oficial.

Entregables:

- documentación de endpoints;
- fixture real;
- parser;
- modelos internos;
- listado de combustibles;
- estaciones;
- municipios;
- tests;
- caché inicial.

No construir todavía una interfaz compleja.

---

## Fase 2 — Motor geográfico

Objetivo:

Encontrar estaciones cercanas.

Entregables:

- Haversine;
- filtro por radio;
- orden por distancia;
- filtro por combustible;
- tests.

Entrada:

```text
lat + lon + fuel
```

Salida:

```text
top N estaciones
```

---

## Fase 3 — Vehículo y coste económico

Objetivo:

Personalizar resultados.

Entregables:

- modelo Vehicle;
- consumo;
- combustible;
- litros a repostar;
- cálculo de coste;
- autonomía;
- margen de seguridad;
- ranking por coste efectivo.

---

## Fase 4 — MVP móvil

Objetivo:

Poder utilizar realmente la app desde el móvil.

Entregables:

- permisos GPS;
- pantalla Inicio;
- vehículo;
- resultados;
- detalle;
- búsqueda manual;
- manejo de errores;
- loading states.

---

## Fase 5 — Google Maps

Objetivo:

Navegación práctica.

Entregables:

- botón `Ir`;
- deep link;
- coordenadas;
- fallback web si Google Maps no está disponible.

---

## Fase 6 — Mejoras de producto

Candidatos:

- dashboard nacional de precio medio por combustible, con metodología, cobertura y frescura visibles;
- favoritas;
- repostajes;
- histórico;
- ahorro acumulado;
- estación habitual;
- rutas frecuentes;
- abierta ahora;
- filtros de marcas;
- límite de distancia;
- descuentos específicos;
- modo oscuro.

---

## Fase 7 — Rutas reales

Objetivo:

Sustituir distancia aproximada por distancia y desvío por carretera.

Posibles capacidades:

- ruta origen → gasolinera;
- desvío;
- tiempo extra;
- coste incremental;
- gasolineras a lo largo de una ruta;
- máximo desvío permitido.

---

## Fase 8 — Histórico y alertas

Gracias a los datos históricos:

- evolución de precios;
- precio medio de una estación;
- mínimo/máximo reciente;
- “precio bajo respecto a los últimos 30 días”;
- alertas por umbral;
- alertas por estaciones favoritas.

Solo implementar si aporta utilidad real.

---

# 27. Ideas futuras

No pertenecen al MVP.

- Registro de repostajes.
- Coste mensual/anual.
- Consumo real calculado entre repostajes.
- Ahorro acumulado usando FuelRoute.
- Estadísticas del vehículo.
- Predicción simple de evolución de precio.
- Widgets móviles.
- Android Auto / CarPlay si técnicamente compensa.
- Alertas cuando una estación favorita baje de un precio.
- Búsqueda a lo largo de un trayecto.
- Comparación de descuentos de programas de fidelización.
- Varias personas/vehículos.
- Exportación CSV.
- Modo offline con último dataset.
- Visualización en mapa.
- Heatmap de precios.
- “Mejor momento para repostar” basado en histórico.

---

# 28. Fuera de alcance inicial

No implementar al principio:

- navegación giro a giro propia;
- pagos;
- cuentas;
- redes sociales;
- recomendaciones mediante IA;
- ML predictivo;
- scraping de gasolineras;
- infraestructura distribuida;
- microservicios;
- versión web pública;
- monetización;
- iOS y Android con código nativo separado.

---

# 29. Criterios de éxito del MVP

El MVP se considera útil cuando desde el móvil se puede:

1. Configurar un vehículo.
2. Definir su combustible y consumo.
3. Dar permiso de ubicación.
4. Introducir opcionalmente autonomía y litros.
5. Consultar estaciones cercanas con precios oficiales.
6. Saber cuáles son alcanzables.
7. Ordenarlas por precio, distancia y coste estimado.
8. Consultar el detalle de una estación.
9. Abrir Google Maps y navegar hasta ella.
10. Buscar manualmente por municipio y combustible.

---

# 30. Principios de desarrollo

1. **Vertical slices:** cada fase debe terminar con algo ejecutable.
2. **Tests primero en lógica crítica:** parsing, geodistancia, coste y autonomía.
3. **Fuente oficial encapsulada:** nunca mezclar MITECO directamente con UI.
4. **MVP pequeño:** no añadir funciones porque “podrían venir bien”.
5. **Decisiones documentadas:** ADR para decisiones importantes.
6. **No romper funcionalidad existente:** cada fase incluye regresión.
7. **CI obligatoria antes de fusionar.**
8. **Configuración por entorno.**
9. **No almacenar secretos en Git.**
10. **Commits pequeños y PRs comprensibles.**

---

# 31. Forma de trabajo con ChatGPT — Chat Orquestador

Este chat actuará como **orquestador del proyecto**.

Sus responsabilidades serán:

- mantener la visión global;
- decidir qué fase toca;
- dividir cada fase en tareas manejables;
- preparar prompts precisos para Codex;
- revisar resultados;
- detectar decisiones de arquitectura;
- impedir que el alcance crezca sin motivo;
- mantener actualizado el roadmap;
- proponer tests y criterios de aceptación;
- decidir cuándo crear documentación;
- indicar qué comprobar manualmente;
- ayudar a interpretar errores;
- preparar la siguiente iteración.

Este chat no debe intentar implementar todo el proyecto de una vez.

---

# 32. Protocolo de cada fase

Antes de comenzar una fase, el orquestador debe entregar:

```text
FASE X — Nombre

Objetivo
Alcance
Fuera de alcance
Archivos esperados
Criterios de aceptación
Tests obligatorios
Riesgos
Prompt recomendado para Codex
Modelo / nivel de razonamiento recomendado
Cómo validar manualmente
Qué información devolver al orquestador
```

Cuando Codex termine:

1. El usuario pega el resumen/resultados.
2. El orquestador los analiza.
3. Se revisan errores, tests y decisiones.
4. Se decide:
   - aprobar;
   - corregir;
   - ampliar;
   - dividir.
5. Solo entonces se avanza.

---

# 33. Estrategia de uso de Codex

Los prompts deben:

- dar contexto suficiente;
- limitar claramente el alcance;
- indicar archivos que puede modificar;
- pedir tests;
- pedir comandos de validación;
- impedir refactors no relacionados;
- exigir resumen final;
- exigir listar cambios;
- indicar cualquier decisión pendiente;
- no incluir secretos;
- no asumir que una API funciona sin probarla.

Siempre se indicará explícitamente:

- modelo recomendado;
- nivel de razonamiento recomendado;
- justificación breve basada en calidad vs. consumo de tokens.

---

# 34. Reglas para dependencias

Antes de añadir una dependencia:

1. justificar qué problema resuelve;
2. comprobar mantenimiento;
3. comprobar licencia cuando sea relevante;
4. evitar una librería si la funcionalidad trivial puede implementarse bien;
5. fijar versiones de manera reproducible.

---

# 35. Seguridad y privacidad

- No guardar GPS histórico sin necesidad.
- HTTPS.
- Validación de inputs.
- Timeouts para llamadas externas.
- Retries limitados.
- Manejo de caída de MITECO.
- No exponer trazas internas al cliente.
- Secrets únicamente por variables de entorno.
- No introducir claves de Google Maps en el repositorio.
- Minimizar datos personales.

---

# 36. Observabilidad inicial

Mínimo:

- logs estructurados en backend;
- duración de petición a MITECO;
- estado de caché;
- errores de parsing;
- errores HTTP externos.

No implementar una plataforma completa de observabilidad en el MVP.

---

# 37. UX: filosofía

La función principal debería poder completarse aproximadamente con:

```text
Abrir app
→ introducir autonomía si se desea
→ Buscar cerca de mí
→ elegir estación
→ Ir
```

No obligar a rellenar filtros innecesarios.

La app recordará:

- vehículo activo;
- combustible;
- consumo;
- preferencias.

---

# 38. Decisiones iniciales

## ADR-001 — Fuente de precios

**Decisión:** usar MITECO como fuente primaria.

**Motivo:** fuente oficial, nacional y con datos estructurados.

---

## ADR-002 — Backend

**Decisión:** FastAPI/Python.

**Motivo:** rapidez de desarrollo, validación fuerte y alineación con experiencia existente.

---

## ADR-003 — Mobile

**Decisión:** React Native + Expo + TypeScript.

**Motivo:** app móvil multiplataforma con una única base de código y buen acceso a GPS/deep links.

---

## ADR-004 — Navegación MVP

**Decisión:** abrir Google Maps mediante deep link.

**Motivo:** conseguir navegación real sin integrar todavía un motor de rutas.

---

## ADR-005 — Geodistancia MVP

**Decisión:** Haversine para búsqueda y prefiltrado.

**Motivo:** simple, rápida y gratuita.

---

## ADR-006 — Autenticación

**Decisión:** no habrá login en MVP.

**Motivo:** aplicación inicialmente personal; evita complejidad sin valor inmediato.

---

# 39. Primera tarea del proyecto

La primera fase real será:

> **Fase 0 — Bootstrap del repositorio y spike técnico de la API MITECO**

Objetivo inmediato:

1. crear repositorio;
2. crear estructura mínima;
3. comprobar desde Python que podemos consultar el servicio MITECO;
4. guardar un fixture pequeño;
5. inspeccionar el esquema real;
6. documentar peculiaridades;
7. dejar documentado el contrato observado y las dudas de integración para la fase 1;
8. comprobar el arranque mínimo de backend y móvil, con tests básicos y CI.

Antes de desarrollar la interfaz móvil completa debemos demostrar que la fuente de datos está bajo control.

---

# 40. Definition of Done general

Una tarea no está terminada porque “funciona en mi máquina”.

Debe incluir, cuando aplique:

- implementación;
- typing;
- tests;
- lint;
- documentación;
- manejo de errores;
- comandos de validación;
- README/docs actualizados;
- ausencia de secretos;
- resumen de cambios.

---

# 41. Fuente de verdad

Este archivo es el contexto maestro inicial.

Si durante el proyecto una decisión cambia:

- no asumir silenciosamente la nueva decisión;
- registrar el cambio;
- actualizar este archivo o un ADR;
- explicar el motivo.

El objetivo es que cualquier nueva conversación o agente pueda leer `PROJECT_CONTEXT.md` y comprender rápidamente:

- qué estamos construyendo;
- por qué;
- arquitectura;
- alcance actual;
- fase activa;
- restricciones;
- forma de trabajo.

---

# 42. Protocolo explícito de chats y traspasos

- **Este chat es el orquestador permanente.** Aquí se mantienen la fase activa, las decisiones, los problemas pendientes y la aprobación para avanzar.
- **Un chat nuevo por fase de trabajo.** El orquestador indicará el momento exacto para abrirlo, propondrá su título y entregará un prompt autocontenido para pegar allí. Una corrección pequeña de la fase vigente puede continuar en el mismo chat de esa fase.
- **Contexto compartido.** Cada chat de fase debe leer este documento y la documentación vigente del repositorio. Si no tiene acceso directo, el prompt llevará el contexto y las rutas necesarias. El repositorio será la fuente de verdad para el código y los resultados de pruebas.
- **Codex.** Cada prompt indicará explícitamente el modelo disponible recomendado y el esfuerzo de razonamiento, con una justificación breve sobre calidad y consumo. Se concretarán al preparar la fase, según la complejidad real y los modelos disponibles en ese momento.
- **Entrega al orquestador.** Al terminar cada fase, el usuario traerá un reporte del chat de trabajo con: objetivo alcanzado; commits o PR; archivos modificados; decisiones; pruebas y comandos con sus resultados; comprobación manual en móvil si procede; incidencias; limitaciones; próximos pasos propuestos. Se pegará el resultado completo cuando haya errores.
- **Cierre.** El orquestador comprobará los criterios de aceptación con el reporte y las evidencias disponibles, pedirá arreglos en el chat de fase si hacen falta y solo entonces propondrá abrir el chat de la siguiente fase. No se dará por validada una prueba o un despliegue sin su resultado.

**Estado inicial:** fase 0 pendiente. Al incorporar este documento y este chat a la carpeta del proyecto, el siguiente paso será abrir el chat de la fase 0 con el prompt que proporcione el orquestador.

---

# 43. Precisiones para evitar resultados engañosos

## Autonomía y distancias

La distancia Haversine es en línea recta y constituye un límite inferior de la distancia por carretera. Un multiplicador arbitrario no garantiza que una estación sea alcanzable: carreteras, accesos y sentidos de circulación pueden exigir muchos más kilómetros. Hasta disponer de una ruta real, mostrar **«posiblemente alcanzable; confirma la ruta»** cuando la estimación entre en el margen y **«fuera del margen incluso en línea recta»** cuando lo supere. No prometer alcance seguro ni eliminar silenciosamente opciones por una supuesta distancia de conducción. En el momento de navegar, Google Maps permite verificar el trayecto real y la autonomía indicada por el vehículo prevalece como referencia práctica.

## Precio y coste

El usuario debe distinguir el precio por litro del coste estimado de ir a repostar. Para comparar de forma justa, usar el mismo volumen de repostaje en todas las estaciones y comparar el desplazamiento adicional desde el punto de partida. Si el viaje es de ida y vuelta o forma parte de una ruta, el cálculo debe reflejar ese caso concreto. Sin kilómetros de conducción reales, el coste de desplazamiento y el ahorro serán solo aproximaciones, etiquetadas como tales. Si no se indican litros, ordenar por precio o distancia, sin presentar un «ahorro total» ficticio.

## Disponibilidad móvil y arquitectura

Antes de decidir despliegue, comprobar desde el teléfono real cómo accederá a FastAPI fuera de la red local, qué coste y mantenimiento tendrá y si el servicio oficial es accesible. La solución con backend es una propuesta inicial, no un requisito que obligue a pagar alojamiento desde la fase 0. Mantener el acceso a precios encapsulado para poder revisar la arquitectura tras el prototipo. Registrar los costes de rutas y mapas antes de añadir proveedores de pago.

## Pendiente de decidir antes de cerrar el MVP

- Plataforma del primer teléfono: Android o iOS.
- Dónde se probará y alojará el backend durante el uso real.
- Criterio de actualización y comportamiento cuando el dato oficial sea antiguo.
- Si el usuario normalmente busca una parada con retorno al punto de partida o durante un trayecto a otro destino.

Referencias consultadas el 25/09/2026: https://www.gasoapp.es/ ; https://www.gasoapp.es/ruta ; https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/help ; https://datos.gob.es/es/catalogo/e05068001-instalaciones-de-suministro-de-combustibles-a-vehiculos-con-venta-publica .

---

# 44. Estándar de ingeniería y entrega continua

Se trata como un producto mantenible durante años y apto para una futura publicación. «Profesional» significa trazabilidad y controles medibles; cada fase debe entregar una parte funcional y verificada. Antes de fijar versiones concretas, confirmar soporte actual de Expo/React Native, Node, Python, sistema operativo de los teléfonos objetivo y origen de datos. Documentar política de actualización y compatibilidad en el repositorio.

## Repositorio y revisión

- Ramas de trabajo cortas; cambios mediante PR con descripción, riesgos, capturas o vídeo de UI cuando corresponda, comandos y resultados de prueba, y referencias a requisitos y ADR.
- Proteger la rama principal: checks obligatorios, PR actualizado con base, revisión humana del propio usuario, resolución de comentarios y bloqueo de cambios directos cuando el servicio lo permita. La revisión por IA/Codex complementa la humana; no constituye evidencia de que una prueba haya pasado.
- Plantillas de issue, PR y ADR; CODEOWNERS solo si hay revisores reales. Registrar el alcance de cada cambio, sus criterios de aceptación y su evidencia. Evitar métricas decorativas.
- Integración de dependencias automatizada con actualización periódica, alertas de seguridad y changelog; PRs pequeños para migraciones de SDK y pruebas en el dispositivo real.

## CI por PR y rama principal

- Instalación reproducible desde lockfiles, versiones fijadas de herramientas y jobs separados de backend y móvil. Documentar las versiones soportadas y probar matrices de versiones cuando exista una necesidad de compatibilidad real.
- Backend: formato, lint, tipos, pruebas unitarias e integración con fixtures/control de red, build de artefacto o imagen y análisis de dependencias. Móvil: formato, lint, tipos, pruebas de componentes/lógica, comprobación de configuración y bundle/build verificable según la fase.
- Pruebas de contratos del adaptador de datos con snapshots/fixtures representativos; una comprobación programada contra la fuente real, aislada de la suite obligatoria para no bloquear PRs por una caída externa. Registrar cambios de esquema observados.
- Tests de extremo a extremo de los recorridos críticos cuando haya pantallas utilizables: guardar vehículo, buscar cerca, autonomía provisional, buscar municipio, abrir navegación, error de red y dato antiguo. Ejecutarlos en emulador y verificar también en un móvil físico antes de declarar un release.
- Cobertura visible con umbrales razonados para lógica crítica, sin exigir un porcentaje arbitrario global. Cada fallo de producción relevante tendrá test de regresión.
- Escaneo de secretos y dependencias; principio de mínimo privilegio para tokens de CI y credenciales por entorno. No ejecutar workflows de terceros con secretos de producción sin revisión.
- Un PR no se fusiona con checks rojos; las excepciones justificadas quedan anotadas. Revisar seguridad, privacidad, accesibilidad y rendimiento según el cambio.

## CD, versiones y mantenimiento

- Pipeline separado para artefactos de desarrollo, preproducción y publicación. Versiones y notas de cambios identificables; despliegues repetibles, configuración validada y rollback del backend documentado.
- Fase 0 define la estrategia; ningún servicio de pago ni distribución pública es requisito del bootstrap. Una vez exista backend alojado, desplegar a entorno de pruebas automáticamente tras integrar y mantener la promoción a producción controlada hasta demostrar tests, smoke checks y rollback.
- Para móvil, establecer distribución interna, pruebas de instalación y actualización, firma y compatibilidad con Android/iOS que realmente se soporten; publicación pública solo tras revisión de privacidad, licencia de datos, requisitos de tienda y pruebas en dispositivos reales.
- Mantener runbook de incidentes de API oficial, caché, caídas del backend, datos antiguos y actualizaciones de SDK. Revisar dependencias, sistemas operativos y coste de alojamiento periódicamente.

## Criterio de cierre por fase

Cerrar únicamente con lista de requisitos satisfechos y evidencia verificable: hash/PR, checks de CI, comandos y resultados, pruebas manuales, capturas cuando proceda, documentación/ADR y riesgos abiertos. «Hecho» no significa que Codex haya escrito código; el orquestador revisa el reporte y decide formalmente el avance.

---

# 45. Protocolo operativo Orquestador → Chat de fase → Codex

1. **Orquestador:** anuncia una sola fase activa y entrega el prompt de arranque para un chat nuevo, con objetivo, alcance, criterios medibles, supuestos y documentación de referencia. Recomienda un modelo y esfuerzo de razonamiento disponibles para el prompt de Codex, ajustados a complejidad y consumo.
2. **Chat de fase:** primero revisa contexto y estado real del repositorio. En las fases con código, redacta el primer prompt exacto para Codex, indicando explícitamente modelo y nivel de razonamiento. El usuario lo pega en Codex.
3. **Bucle:** el usuario trae al chat de fase la respuesta de Codex, errores, diff o resultados. El chat de fase contrasta evidencias, indica qué falta y redacta el siguiente prompt exacto de respuesta a Codex, también con modelo y esfuerzo. Repite hasta completar la fase. Una salida resumida de Codex no sustituye resultados de tests y CI.
4. **Informe:** al completar la fase, el chat de fase entrega un único reporte autocontenido para pegar aquí: objetivo, alcance implementado, rutas y commit/PR, decisiones/ADR, pruebas con comandos y resultados, estado de CI, revisión de seguridad y privacidad pertinente, prueba real en móvil si aplica, limitaciones y propuesta de siguiente fase.
5. **Cierre:** el orquestador coteja reporte, criterios y evidencias. Si algo falta, devuelve instrucciones concretas para el mismo chat de fase. Si se cumple, declara cerrada la fase, actualiza el estado y proporciona el prompt del chat de la siguiente fase. Una pregunta o mejora puntual puede resolverse aquí sin alterar este circuito.

Este documento fija los requisitos y el proceso; el repositorio y sus pruebas son la fuente de verdad para la implementación. Registrar aquí cambios de visión o fase activa tras aprobarlos.

**Estado al crear esta versión:** fase 0 pendiente; no se afirma que existan repositorio, pipelines o aplicación.
