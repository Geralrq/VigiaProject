# Progreso

## Fase 1 — Esqueleto del monorepo
- backend: uv + Python 3.13, FastAPI; `main.py` expone `app` creado en `app/bootstrap.py`; `GET /api/health`.
- Módulos hexagonales vacíos: monitoring, alerts, reports, inspections, notifications, shared.
- import-linter: domain/application sin fastapi, sqlalchemy, httpx, sentinelhub (test en tests/test_architecture.py).
- frontend: Next.js App Router + TS, react-query, supabase-js, maplibre-gl, deck.gl, openapi-typescript (`gen:api`); features vacías; sin estilos.
- vercel.json con servicios web y api; dev local proxifica /api a :8000.
- Pendiente: Alembic (migrations/ vacío), auth JWT, modo demo, puertos y casos de uso.