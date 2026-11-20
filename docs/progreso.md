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
