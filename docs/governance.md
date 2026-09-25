# Gobierno del repositorio

`main` es la rama de integración. Crear ramas cortas `feature/*` o `fix/*`, abrir un PR con la plantilla, ejecutar los checks y solicitar revisión humana. Resolver los comentarios y actualizar el PR con `main` antes de squash merge. No hacer cambios directos en `main` una vez esté protegida.

Los checks propuestos como obligatorios son `backend`, `mobile` y `security` del workflow `CI`. `backend` valida instalación con lock, formato, lint, tipos y tests; `mobile` valida instalación con lock, lint, formato, tipos, tests, compatibilidad Expo y bundle Android; `security` detecta patrones de credenciales y archivos `.env` versionados, y bloquea hallazgos npm de severidad alta o crítica en dependencias de producción. La revisión de secretos es heurística y no sustituye una auditoría dedicada.

Cuando exista remoto GitHub, configurar en **Settings → Rules → Rulesets** una regla para `main` que exija PR, comentarios resueltos y, si hay otro revisor con permisos, una aprobación humana, rama actualizada y esos tres checks. Restringir cambios directos y force push. Verificar la regla leyendo su configuración y adjuntando un enlace o captura; aportar también enlace y conclusión de una ejecución de Actions en PR. Hasta entonces: **workflow definido, ejecución CI pendiente de evidencia**. No se ha verificado protección de rama. GitHub no permite que el autor apruebe su propio PR; si hay un único mantenedor, documentar su revisión en el PR sin exigir una aprobación imposible.

La primera integración local del bootstrap crea la rama `main` y un commit inicial. A partir de la disponibilidad de un remoto, aplicar el flujo de PR anterior.

## Riesgos de dependencias observados

El 25/09/2026, `npm audit --audit-level=high --omit=dev --package-lock-only` terminó con código 0 y mostró 10 avisos moderados asociados a `uuid <11.1.1` a través de `xcode`/`@expo/config-plugins`. `npm audit fix --force` propuso bajar Expo a 46, incompatible con el SDK 57 elegido; revisar la cadena al actualizar Expo. Pytest pasó con un aviso de obsolescencia de `starlette.testclient`/`httpx`; revisar cuando FastAPI/Starlette publiquen la transición estable.