# FuelRoute ES

Base técnica de la Fase 0. La visión y las decisiones de producto están en [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md). Esta fase solo contiene una API de salud, una pantalla Expo mínima y una consulta controlada a MITECO.

## Requisitos

- Python 3.13.15, gestionado con [uv](https://docs.astral.sh/uv/) 0.12.10.
- Node 24 LTS (probado con 24.19.0) y npm (probado con 8.19.2).
- En PowerShell con scripts bloqueados, usar `npm.cmd` y `npx.cmd`.

La referencia móvil para esta fase es Node **24.19.0**, igual que CI. Comprobar `node --version`, `npm.cmd --version` y `where.exe npm` antes de regenerar el lockfile. En el entorno auditado, `C:\Program Files\nodejs\npm.cmd` delega en npm 8.19.2 del prefijo de usuario; el npm incluido junto a Node es 11.17.0. No se han actualizado estas instalaciones.

Usar `npm ci` para instalar. El lockfile actual es versión 2, generado con npm 8.19.2; npm posterior puede leerlo, pero regenerarlo con otra versión puede cambiar su formato o resolución. Mantener npm 8.19.2 al editar este lockfile durante la Fase 0; cualquier migración del gestor debe ser explícita y revisar su diff. CI usa el npm incluido con Node 24.19.0: su ejecución y versión efectiva aún requieren evidencia externa. [Formato del lockfile en npm](https://docs.npmjs.com/cli/v11/configuring-npm/package-lock-json/).

La selección de Expo SDK 57, React Native 0.86.3 y React 19.2.3 sigue la [tabla oficial de compatibilidad](https://docs.expo.dev/versions/v57.0.0/). Node 24 supera el mínimo 22.13. El archivo `backend/.python-version`, `backend/uv.lock` y `mobile/package-lock.json` fijan el entorno de ejecución y las dependencias resueltas. Actualizar SDK y lockfiles en un PR separado, con `expo install --check`, tests y bundle. Revisar soporte de Android/iOS del teléfono objetivo antes de publicarlo.

## Backend

```powershell
cd backend
uv sync --locked
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked mypy
uv run --locked python -m pytest -q
uv run --locked uvicorn app:app --host 127.0.0.1 --port 8000
# En otra terminal: Invoke-RestMethod http://127.0.0.1:8000/health
```

`GET /health` devuelve `{"status":"ok"}`. No se necesita `.env` para esta fase.

## Móvil

```powershell
cd mobile
npm.cmd ci
npm.cmd run lint
npm.cmd run format:check
npm.cmd run typecheck
npm.cmd run test
npx.cmd expo install --check
npm.cmd run bundle
npm.cmd start
```

`bundle` exporta un bundle Android con Metro sin emulador. El arranque visual y la instalación en teléfono quedan pendientes de un dispositivo. `dist/` es generado y se ignora.

## Spike MITECO

Desde `backend/`, ejecutar voluntariamente:

```powershell
uv run --locked python scripts/miteco_spike.py
```

La consulta usa un timeout de 15 segundos, lee la provincia 51 (Ceuta) y sobrescribe el fixture pequeño solo si obtiene estaciones válidas. La API externa no forma parte de los tests normales ni del CI. El contrato observado, procedencia y dudas constan en [docs/miteco-api.md](docs/miteco-api.md).

## Colaboración y CI

Usar ramas cortas `feature/*` o `fix/*`, PR hacia `main`, revisión humana y squash merge. La plantilla de PR pide alcance, riesgos, pruebas y evidencia. `main` debería exigir los jobs `backend`, `mobile` y `security` de [CI](.github/workflows/ci.yml), PR actualizado con base, comentarios resueltos y al menos una revisión humana cuando exista un repositorio remoto con permisos para ello. Ninguna ejecución GitHub Actions ni protección de rama está demostrada hasta que se conecte un remoto y se verifique en GitHub. No hay `CODEOWNERS` porque no se conocen revisores reales.

Los ADR se crean desde [docs/decisions/000-template.md](docs/decisions/000-template.md). Este bootstrap no despliega servicios ni añade credenciales.
