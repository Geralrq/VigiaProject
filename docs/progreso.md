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

## Fase 6 — Reportes ciudadanos y misiones de verificación (reports; sin frontend)
- Storage: `StoragePort` (shared) con Supabase Storage por httpx (`SUPABASE_SERVICE_KEY`, bucket privado `evidencias`, URL firmada 1 h en lote; errores sin llave/URL) o en memoria con URL de marcador en demo sin llave. En BD solo la ruta (`reportes|misiones/<uuid>.ext`). Foto: JPEG/PNG/WebP detectados por contenido (no por nombre ni Content-Type), máx. 5 MB (413).
- `POST/GET /api/reports` (multipart; CIUDADANO/otros ven los suyos, AUTORIDAD y ADMIN todos, `bbox`, GeoJSON). Hexagonal: dominio puro (`photo`, `report`, `mission`, `verification`), casos de uso `citizen_reports` y `missions`, adaptadores SQL; `VerificationMissionModel` pasó de inspections a reports.
- `scan_zones` publica `AnomalyDetected` solo si el upsert crea la fila (`RETURNING xmax = 0`). `CreateVerificationMissions`: 5 más cercanos (CIUDADANO/GUARDABOSQUES) a ≤ `MISSION_RADIUS_M` (10 km), anomalía → EN_VERIFICACION, aviso por `NotificationPort` (`MissionNotice`), idempotente (id uuid5 + único BD + no repite si ya hay misiones).
- `GET /api/missions/mine`, `POST /api/missions/{id}/respuesta` (solo el asignado, una vez: 403/409), `GET /api/leaderboard` (solo nombre y puntos). Regla: 2 CONFIRMA → `confirm_anomaly` (alerta); 2 DESCARTA → FALSO_POSITIVO + umbral de la zona ×1,10 (más magnitud = menos sensible; signo conservado; tope NDVI 0,35 y NBR 0,50; detección usa `abs()`; nunca se baja uno ya excedido). Una anomalía ya CONFIRMADA no se descarta por voluntarios. Se decide bajo `FOR UPDATE` de la anomalía.
- Puntos: base 10 por misión respondida, bono 5 si coincide con el resultado final (se paga una vez al decidirse, o al instante a una respuesta tardía); `profiles.puntos` con incremento atómico.
- Migración `003` aplicada: `profiles.es_demo`, único (anomalía, usuario) y bucket `evidencias` privado (5 MB, jpeg/png/webp, sin políticas en storage.objects). Seed: 4 perfiles demo CIUDADANO (`es_demo`, sin cuenta de login), idempotente; NO ejecutado en la BD real: `uv run python -m scripts.seed`.
- `scripts/verify_reports.py` (transacción + rollback): SQL real de reportes, cercanos, misiones, alerta, puntos y umbral. 326 tests sin red ni BD (+ `provide_session` falla en tests), lint-imports y ruff OK. Pendiente: sin endpoint para fijar `ubicacion` del perfil (nadie real recibe misiones aún), probar Storage real con la llave, páginas del front.

## Fase 6b — Perfil propio, Storage real e imágenes de anomalías (sin frontend)
- Seed ejecutado contra la BD real (4 perfiles `es_demo` con ubicación; 2.ª ejecución sin duplicar). Perfil en `shared` (hexagonal): `GET/PATCH /api/me` (id, nombre, rol, ubicación GeoJSON, puntos, `telegram_linked` booleano, nunca el chat_id). PATCH solo nombre/ubicación (`location: null` la borra, lat/lng validados); cualquier otro campo (rol, puntos…) → 422. Ningún otro endpoint serializa la ubicación de un usuario (test que recorre reports, alerts, missions, leaderboard, anomalies, zones y la ficha pública).
- `scripts/verify_storage.py` + `StoragePort.delete` y `upload(overwrite=)`: BLOQUEADO, la llave en `.env.local` es una publishable (`sb_publishable_…`) y Storage responde RLS 403; poner la secret/service_role en `SUPABASE_SERVICE_KEY` y reejecutar. El script detecta el tipo de llave sin imprimirla y limpia el objeto al final.
- `SatelliteIndexPort.get_image(geometry, day, lookback_days)`: Sentinel Hub Process API (mismo OAuth, mosaico `leastCC`, color real, SCL como alfa ⇒ nubes transparentes, ≤768 px) y demo con Pillow (determinista, rotulada «DEMO sintetica»; Pillow ahora dependencia directa). Sin probar contra Copernicus real.
- `EnsureAnomalyImages`: antes = detección −30 d (±15), después = detección (−10 d); rutas `anomalias/<id>/{antes,despues}.png` en `imagen_*_url`; no regenera, falla parcial guarda la que sí salió y reintenta solo la otra, ambas fallan ⇒ 503; fila bloqueada `FOR UPDATE`. `GET /api/anomalies/{id}/images` (autenticado, URL firmadas 1 h).
- 382 tests sin red ni BD, lint-imports y ruff OK; SQL nuevo comprobado contra la BD real con rollback.
