# Gobierno del repositorio

`main` es la rama de integración. Crear ramas cortas `feature/*` o `fix/*`, abrir un PR con la plantilla, ejecutar los checks y solicitar revisión humana. Resolver los comentarios y actualizar el PR con `main` antes de squash merge. No hacer cambios directos en `main` una vez esté protegida.

Los checks obligatorios son `backend`, `mobile` y `security` del workflow `CI`. `backend` valida instalación con lock, formato, lint, tipos y tests; `mobile` valida instalación con lock, lint, formato, tipos, tests, compatibilidad Expo y bundle Android; `security` detecta patrones de credenciales y archivos `.env` versionados, y bloquea hallazgos npm de severidad alta o crítica en dependencias de producción. La revisión de secretos es heurística y no sustituye una auditoría dedicada.

La [protección clásica de `main`](https://api.github.com/repos/KastaTM/fuelroute-es/branches/main/protection) exige PR, comentarios resueltos, rama actualizada (`strict: true`) y los checks `backend`, `mobile` y `security`. Se aplica también a administradores; force push y borrado están deshabilitados. Requiere 0 aprobaciones y no exige aprobación del último push, porque hay un único mantenedor que no puede aprobar su propio PR. Documentar la revisión propia en el PR. El [run CI 36171654419](https://github.com/KastaTM/fuelroute-es/actions/runs/36171654419) del SHA aprobado de Fase 0 terminó en `success` con los tres jobs en `success`.

La primera integración local del bootstrap crea la rama `main` y un commit inicial. A partir de la disponibilidad de un remoto, aplicar el flujo de PR anterior.

## Riesgos de dependencias observados

El 25/09/2026, `npm audit --audit-level=high --omit=dev --package-lock-only` terminó con código 0 y mostró 10 avisos moderados asociados a `uuid <11.1.1` a través de `xcode`/`@expo/config-plugins`. `npm audit fix --force` propuso bajar Expo a 46, incompatible con el SDK 57 elegido; revisar la cadena al actualizar Expo. Pytest pasó con un aviso de obsolescencia de `starlette.testclient`/`httpx`; revisar cuando FastAPI/Starlette publiquen la transición estable.