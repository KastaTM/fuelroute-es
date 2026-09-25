# Auditoría Fase 0 — 25/09/2026

Base auditada: `0da6c269753413c92a613de0d920be19b00bb9f6`. El árbol comenzó limpio en `main`, sin remoto. `git ls-tree -r --name-only HEAD` confirma 33 archivos; `git show --stat HEAD` confirma 24.071 líneas añadidas. No se dispone de la captura ni del filtro del panel que mostraba 16 archivos: ese panel no sustituye el inventario de Git. En esta auditoría `gh auth status` sí terminó con código 0 y autenticación válida; la ausencia de remoto persiste.

Se leyeron los artefactos solicitados, el lockfile móvil mediante JSON, los archivos adicionales `mobile/AGENTS.md`, `mobile/index.ts`, `mobile/app.json`, `mobile/tsconfig.json` y la implementación instalada de `starlette.testclient`. El contexto maestro conserva los ADR-001 a ADR-006. No se añadieron dependencias ni lógica de producto.

## Correcciones

- El escaneo de CI mostraba líneas completas con `git grep -n`: ahora muestra únicamente nombres (`-l`), incluye todos los archivos versionados de texto y propaga errores de Git distintos de «sin coincidencias».
- README aclara Node de referencia, la redirección de npm del equipo, la política de mantenimiento del lockfile y el comando Expo de compatibilidad.

## Runtime y lockfile

`node --version`: 24.19.0; `node -p "process.execPath"`: `C:\Program Files\nodejs\node.exe`.
`where.exe npm` encuentra primero `C:\Program Files\nodejs\npm.cmd`. Su contenido consulta el prefijo y delega en `C:\Users\Rodrigo\AppData\Roaming\npm\node_modules\npm\bin\npm-cli.js`: npm 8.19.2.
`npm.cmd config get prefix`: `C:\Users\Rodrigo\AppData\Roaming\npm`.
`node 'C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js' --version`: 11.17.0.

El lockfile tiene formato 2 y 995 entradas en `packages`, incluidas alternativas por plataforma; no equivale al número de paquetes instalados en Windows. Fija Expo 57.0.25, React Native 0.86.3, React 19.2.3 y TypeScript 6.0.3. El requisito Node declarado por React Native incluye `^24.3.0`, satisfecho por 24.19.0. CI selecciona Node 24.19.0 y su npm incluido; su versión efectiva en GitHub aún no está observada.

Como comprobación adicional, desde `mobile/`:

```powershell
node 'C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js' ci --dry-run --ignore-scripts --audit=false --fund=false
```

Código 0, `up to date in 7s`. Es evidencia de lectura/resolución del lockfile con npm 11, no de ejecución de scripts ni de un runner Linux. Los lockfiles no cambiaron. [npm documenta sus formatos de lockfile](https://docs.npmjs.com/cli/v11/configuring-npm/package-lock-json/).

## Validaciones backend

Desde `backend/`, variables locales necesarias en este entorno:

```powershell
$env:UV_CACHE_DIR='C:\Projects\fuelroute-es\.uv-cache'
$env:UV_PYTHON_INSTALL_DIR='C:\Projects\fuelroute-es\.uv-python'
```

| Comando | Exit | Salida relevante | Estado |
| --- | --- | --- | --- |
| `uv --version` | 0 | 0.12.10 | PASS |
| `uv run --locked python --version` | 0 | Python 3.13.15 | PASS |
| `uv sync --locked` | 0 | Resolved 28 packages; Checked 27 packages | PASS |
| `uv run --locked ruff format --check .` | 0 | 3 files already formatted | PASS |
| `uv run --locked ruff check .` | 0 | All checks passed! | PASS |
| `uv run --locked mypy` | 0 | Success: no issues found in 3 source files | PASS |
| `uv run --locked python -m pytest --collect-only -q` | 0 | tests/test_health.py::test_health; 1 test collected | PASS |
| `uv run --locked python -m pytest -q` | 0 | 1 passed, 1 warning in 0.30s | PASS |

Warning exacto:

```text
.venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Projects\fuelroute-es\backend\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa
```

Clasificación A: aviso upstream del fallback de importación de Starlette al encontrar httpx y no httpx2. Nuestro código usa `fastapi.testclient.TestClient(app)` sin parámetros obsoletos. No es un fallo del endpoint; una futura actualización upstream podría retirar el fallback. Se mantiene documentado, sin cambiar dependencias.

## Smoke HTTP reproducible

Desde `backend/`, con las variables anteriores:

```powershell
@'
import json
import threading
import time
from urllib.request import urlopen
import uvicorn

server = uvicorn.Server(uvicorn.Config('app:app', host='127.0.0.1', port=8765))
worker = threading.Thread(target=server.run, daemon=True)
worker.start()
try:
    deadline = time.monotonic() + 10
    while not server.started:
        if not worker.is_alive() or time.monotonic() >= deadline:
            raise RuntimeError('Uvicorn did not start')
        time.sleep(0.1)
    with urlopen('http://127.0.0.1:8765/health', timeout=2) as response:
        body = response.read().decode()
        print(f'HTTP {response.status}; body={body}')
        assert response.status == 200 and json.loads(body) == {'status': 'ok'}
finally:
    server.should_exit = True
    worker.join(timeout=10)
    assert not worker.is_alive(), 'Uvicorn did not stop'
print('Uvicorn shutdown complete; worker stopped')
'@ | uv run --locked python -
```

Código 0; `HTTP 200; body={"status":"ok"}`. Uvicorn registró `Application startup complete`, `Application shutdown complete` y `Finished server process [21576]`. El proceso de comprobación terminó y no quedó servidor activo.

## Móvil

Desde `mobile/`, con `$env:npm_config_cache='C:\Projects\fuelroute-es\.npm-cache'`:

| Comando | Exit | Salida relevante | Estado |
| --- | --- | --- | --- |
| `npm.cmd ci` | 0 | added 956 packages, audited 957; 10 moderate severity vulnerabilities | PASS con avisos |
| `npm.cmd run lint` | 0 | expo lint, sin errores | PASS |
| `npm.cmd run format:check` | 0 | All matched files use Prettier code style! | PASS |
| `npm.cmd run typecheck` | 0 | tsc --noEmit, sin errores | PASS |
| `npm.cmd run test` | 0 | 1 suite y 1 test pasan | PASS |
| `npx.cmd expo install --check` | 0 | Dependencies are up to date | PASS |
| `npm.cmd run bundle` | 0 | Android Bundled 4225ms; 580 modules; 1.4 MB; Exported: dist | PASS |
| `npm.cmd audit --audit-level=high --omit=dev --package-lock-only` | 0 | 10 moderate severity vulnerabilities; ninguna alta/crítica informada | PASS para el umbral definido |

Los avisos moderados corresponden a la cadena uuid/xcode/Expo ya documentada en `governance.md`. No se afirma que sean diez vulnerabilidades independientes ni que no exista ningún riesgo. No se ejecutó la app en teléfono/emulador.

## MITECO y aislamiento de tests

Se conserva la evidencia real de la iteración anterior: `uv run --locked python scripts/miteco_spike.py`, HTTP 200, 10 estaciones, `ResultadoConsulta="OK"`, `Fecha="25/09/2026 19:15:43"`. Endpoint:

`https://energia.serviciosmin.gob.es/ServiciosRestCarburantes/PreciosCarburantes/EstacionesTerrestres/FiltroProvincia/51`

No se repitió la consulta ni se regeneró el fixture en esta auditoría. La procedencia está respaldada por la ejecución anterior de esta conversación, el script, el campo `source` y `docs/miteco-api.md`; no se conservó el dataset completo para verificarlo byte a byte.

`backend/tests/fixtures/miteco_ceuta.json`: 973 bytes en el blob Git (`git cat-file -s HEAD:backend/tests/fixtures/miteco_ceuta.json`), 1.005 bytes en el archivo Windows (CRLF). Dos estaciones, once campos: `IDEESS`, `Rótulo`, `Dirección`, `Municipio`, `Provincia`, `Latitud`, `Longitud (WGS84)`, `Precio Gasolina 95 E5`, `Precio Gasoleo A`, `Precio Gasolina 98 E10`, `Horario`. Representa números como texto con coma decimal, longitud negativa, precio vacío, nombres de campos peculiares y dos formatos de horario. El documento del contrato cubre además la forma superior, fecha sin zona horaria explícita y dudas para Fase 1.

Desde la raíz:

```powershell
git -c safe.directory=C:/Projects/fuelroute-es grep -n -I -E 'MITECO|serviciosmin|httpx|requests|urllib|EstacionesTerrestres' -- backend/tests
```

Código 0: una coincidencia, la URL de procedencia en la línea 2 del fixture. El único test recogido usa TestClient con la app en memoria; no abre conexiones a MITECO. El spike queda fuera de `testpaths` y CI.

## Seguridad reproducible

Desde la raíz, sobre todos los archivos versionados de texto:

```powershell
git -c safe.directory=C:/Projects/fuelroute-es grep -l -I -E '(ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)' -- .
```

Código 1, sin coincidencias: PASS. Solo se imprimen nombres de archivos si aparecen coincidencias. Es una revisión heurística, complementada con la lectura de código, configuración y fixture; no una garantía universal de ausencia de secretos.

Inventario local `.env*` excluyendo dependencias/cachés generadas:

```powershell
rg --files --hidden --no-ignore -g '.env*' -g '!.git/**' -g '!**/node_modules/**' -g '!**/.venv/**' -g '!.uv-cache/**' -g '!.uv-python/**' -g '!.npm-cache/**'
```

Código 1, sin archivos. Tampoco hay `.env*` en `git ls-files`. El bloque Bash de seguridad del workflow se ejecutó localmente con Git Bash: código 0. En repositorio temporal, detectó una credencial sintética con código 1 sin imprimir el valor; con texto normal devolvió 0; fuera de un repositorio propagó el error 128.

## CI y gobierno

Backend: Python 3.13.15, uv 0.12.10, sync bloqueado, formato, lint, mypy y pytest. Móvil: Node 24.19.0, npm ci, lint, formato, tipos, test, Expo check y bundle. Seguridad: escaneo anterior y npm audit con umbral alto. Permisos `contents: read`; eventos PR y push a main; sin MITECO en vivo.

Workflow definido; GitHub Actions no ejecutado por ausencia de remoto/evidencia externa.

`gh` está autenticado, pero no hay remoto que permita identificar repositorio/ruleset. Sigue pendiente conectar un remoto y aportar una ejecución CI contra el commit revisado y evidencia de protección de `main`. `docs/governance.md` describe PR, checks, prohibición de push directo al proteger main y revisión propia documentada para un único mantenedor. La autenticación válida no autoriza por sí sola a publicar el repositorio.

Los criterios 1–12, 14–17 y 19 cuentan con evidencia local/documental. El 13 queda pendiente de ejecución CI externa. El 18 se satisface por su alternativa explícita de documentar la acción manual: la protección real no está completada. La Fase 0 queda para revisión del chat de fase.
