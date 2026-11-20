# Progreso

## Fase 1 — Esqueleto del monorepo
- backend: uv + Python 3.13, FastAPI; `main.py` expone `app` creado en `app/bootstrap.py`; `GET /api/health`.
- Módulos hexagonales vacíos: monitoring, alerts, reports, inspections, notifications, shared.
- import-linter: domain/application sin fastapi, sqlalchemy, httpx, sentinelhub (test en tests/test_architecture.py).
- frontend: Next.js App Router + TS, react-query, supabase-js, maplibre-gl, deck.gl, openapi-typescript (`gen:api`); features vacías; sin estilos.
- vercel.json con servicios web y api; dev local proxifica /api a :8000.
- Pendiente: Alembic (migrations/ vacío), auth JWT, modo demo, puertos y casos de uso.
## Fase 2 — Base de datos (Alembic) — aplicada y verificada
- Settings: `app/shared/settings.py` (pydantic-settings, lee `.env.local` de la raíz; `DATABASE_URL` se normaliza a `postgresql+psycopg://`, SecretStr). `.env.example` creado.
- Alembic en `backend/migrations` (`alembic.ini`); `env.py` importa los modelos de cada módulo y usa `geoalchemy2.alembic_helpers`. Motor: psycopg3 con `prepare_threshold=None`.
- Migración `001`: 11 tablas, GIST en todas las geometrías, RLS activado sin políticas (también en `alembic_version`). Modelos en `<módulo>/adapters/outbound/persistence/models.py`.
- PostGIS/search_path: se instala `WITH SCHEMA extensions` (no `public`, para no exponer `spatial_ref_sys` en la API); `env.py` hace `SET LOCAL search_path TO public, extensions` para resolver `geometry`/`ST_*`. No usar `options=-c search_path` en la URL: el pooler transaccional de Supabase lo rechaza.
- RLS: el backend debe conectar con un rol que la omita (`postgres`); otro rol vería 0 filas.
- Seed: `uv run python -m scripts.seed` (ids uuid5 + ON CONFLICT DO NOTHING): 3 zonas, 5 carbon_factors, 78 lecturas, incendio (Paramillo) y deforestación (Guaviare).
- Verificado en Supabase (MCP, solo lectura): postgis 3.3.7 en `extensions`, 11 tablas con RLS y 0 políticas, 6 índices GIST, SRID 4326, filas del seed 3/5/78/5/2, `alembic_version`=001. Seed re-ejecutado sin duplicar.
- Pendiente: auth JWT, modo demo, puertos y casos de uso (Fase 3+).

## Fase 3 — Seguridad y módulo plantilla (zones en monitoring)
- Auth: `JwksTokenVerifier` (PyJWKClient con caché, aud `authenticated`, iss `SUPABASE_URL/auth/v1`, alg tomado de la llave y solo asimétricos) → `AuthenticateUser` crea el perfil CIUDADANO al primer ingreso; el rol sale siempre de `profiles`. `auth.current_user` / `auth.require_roles(Role.X)` en `shared/adapters/inbound/security.py`.
- Errores: excepciones de dominio (`shared/domain/errors.py`) → problem+json en `problems.py` (401/403/404/422/503/500). CORS: http://localhost:3000.
- PATRÓN a copiar por módulo (ver `monitoring/` + zones):
  1. `domain/<x>.py`: dataclass con invariantes en `__post_init__` (lanza `DomainValidationError`), sin frameworks.
  2. `application/ports/<x>_repository.py`: `Protocol`; `application/use_cases/<verbo>_<x>.py`: clase con `execute()` que recibe puertos por constructor (+ `Command` dataclass si hay entrada).
  3. `adapters/outbound/persistence/<x>_repository.py`: `to_domain(row)` / `to_row(entidad)`; columnas en español, dominio y API en inglés.
  4. `adapters/inbound/<x>_schemas.py` (Pydantic, `from_domain`/`to_command`) y `<x>_router.py` con `build_<x>_router(auth, provide_...)`; sin lógica.
  5. `app/bootstrap.py`: `provide_<repo>(SessionDep)` → `provide_<caso_de_uso>` → `include_router`. Tests: fakes en `tests/fakes.py` y `app.dependency_overrides[provide_<repo>]`.
- Sesión: una transacción por request (`Depends(scope="function")`, commit antes de responder).

## Fase 4 — Motor de monitoreo satelital (monitoring, sin frontend)
- Dominio puro: `spectral` (NDVI/NBR/NDWI, baseline mediana 60 d, delta, severidad dNBR USGS), `impact` (ha = px×0.01, CO2 = ha×tC/ha×3.67), `confidence` (0.7·|ΔNDVI|/0.4 + 0.3·foco FIRMS en zona y ventana, × (1−nubes²)), `detection`, `ScanWindow` (bloques fijos de 10 d → idempotencia por zona+ventana con id uuid5).
- Puertos: SatelliteIndexPort, FireHotspotPort, repos de lecturas/focos/anomalías/factores de carbono. Upserts: re-escanear no duplica ni pisa `estado`. Sin migración nueva.
- Adaptadores: Sentinel Hub Statistical (CDSE, máscara SCL, token OAuth en caché), FIRMS área (VIIRS_NOAA20_NRT, bloques de 5 d), reintentos acotados (3, backoff); demo deterministas (deforestación Guaviare 120 ha, incendio Paramillo 38 ha + 5 focos).
- `ScanZones`: zonas activas en paralelo (Semaphore 5); un fallo por zona se reporta en el resumen y no detiene las demás.
- API: `GET /api/jobs/scan` (Bearer CRON_SECRET, compare_digest; cron diario en vercel.json), `POST /api/admin/scan` (ADMIN), `GET /api/anomalies|hotspots` (GeoJSON; bbox, start, end, min_confidence 0..1).
- Modo live: en `.env.local` poner `APP_MODE=live`, `SENTINEL_CLIENT_ID/SECRET` (cliente OAuth de dataspace.copernicus.eu) y `FIRMS_MAP_KEY`; `CRON_SECRET` también en Vercel. Por defecto `APP_MODE=demo`.
- Pendiente: probar live contra las APIs reales; geometría de la anomalía = polígono de la zona (sin píxeles localizados).

## Fase 5 — Alertas y notificaciones (alerts, notifications; sin frontend)
- Eventos en `shared` (bus en memoria síncrono, uno por request; un handler que falla se registra y no corta nada): `AnomalyConfirmed` → alerts → `AlertCreated` → notifications. Se publica al confirmar (`ConfirmAnomaly`, `POST /api/admin/anomalies/{id}/confirm`, ADMIN; reconfirmar republica) o si el scan llega a `CRITICAL_CONFIDENCE_THRESHOLD` (0,75: en demo el incendio 0,79 alerta solo y la deforestación 0,645 se confirma a mano).
- alerts: `assess_risk` (ha ponderadas, incendio ×1,5; confianza <0,5 baja un nivel) y geocerca con shapely (buffer métrico 2/5/10/20 km por nivel); alerta con id uuid5(anomalía) + `ON CONFLICT DO NOTHING` ⇒ idempotente. Destinatarios: perfiles dentro de la geocerca (PostGIS) + todos los AUTORIDAD. `GET /api/alerts[/{id}]` (GeoJSON) y `GET /api/public/alerts/{id}` (ficha reducida, sin auth).
- notifications: `NotificationPort` con Telegram (httpx; sin token solo log; el error nunca incluye la URL/token), SMS simulado y web (tabla `notifications`); un canal caído no cancela los demás.
- Telegram: `GET /api/me/telegram-link` (código HMAC-SHA256 de 48 car., 10 min, `TELEGRAM_LINK_SECRET`, sin tabla), `POST /api/telegram/webhook` (`X-Telegram-Bot-Api-Secret-Token` = `TELEGRAM_WEBHOOK_SECRET`; responde 200 siempre que el secreto sea válido), `PATCH /api/me/telegram` solo si `APP_MODE!=live`. Nuevo 409 (`ConflictError`).
- Migración `002` aplicada: `notifications` en `supabase_realtime`, `GRANT SELECT` a `authenticated` (no tenía) y política `usuario = auth.uid()`; verificado por MCP (anon sin acceso, authenticated solo SELECT). Columna real: `usuario`, no `user_id`.
- Verificación Fase 4 (`scripts/verify_scan.py`): demo contra la BD real, 2 DEFORESTACION + 2 INCENDIO, 2.º scan sin duplicar. `scripts/verify_alerts.py`: adaptadores SQL reales en transacción con rollback (geocerca, destinatarios, notificación web, idempotencia).
- 208 tests sin red ni BD, lint-imports y ruff OK. Pendiente: probar Telegram real (setWebhook con el secreto), SMS real, `/a/[id]` en el frontend.
