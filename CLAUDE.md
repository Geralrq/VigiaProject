# Vigía — inteligencia ambiental y alerta temprana
Monorepo: /backend (FastAPI, Python 3.13, uv) · /frontend (Next.js App Router + TS) · /api-tests (Bruno) · /docs

## Arquitectura (obligatoria)
- Backend hexagonal por módulo: monitoring, alerts, reports, inspections, notifications, shared.
- Cada módulo: domain/ (Python puro) · application/{ports,use_cases} · adapters/inbound (routers) · adapters/outbound/*
- Los puertos son typing.Protocol. Solo app/bootstrap.py conoce adaptadores concretos (inyección con Depends).
- domain/ y application/ NO importan fastapi, sqlalchemy, httpx ni sentinelhub. Lo hace cumplir import-linter (pyproject).
- Los routers solo llaman casos de uso. Sin lógica en routers ni modelos ORM en el dominio.
- Frontend por features: src/features/<feature>/{api,components,hooks}, src/shared. Ningún componente llama fetch directo.

## Base de datos
- Supabase Postgres + PostGIS. El esquema vive en backend/migrations (Alembic); no se edita a mano en el panel.
- Geometrías SRID 4326; GeoJSON en la API.

## Convenciones
- Código y nombres en inglés; textos de UI en español.
- Nombres de columnas, estados y roles en español (lenguaje del dominio); código Python y TypeScript en inglés.
- Pydantic v2 en los bordes de la API; tipos del front generados con openapi-typescript desde /openapi.json.
- Seguridad: JWT de Supabase validado por JWKS (PyJWT); roles CIUDADANO, GUARDABOSQUES, TECNICO, AUTORIDAD, ADMIN.
- Proveedores externos (Sentinel Hub, FIRMS, Telegram, LLM) siempre detrás de un puerto, con adaptador simulado para tests y modo demo (APP_MODE=demo).
- Vercel: sistema de archivos de solo lectura (solo /tmp); PDF e imágenes en memoria y a Supabase Storage. Bundle < 500 MB: sin torch ni tensorflow.

## Comandos
- backend: uv run pytest · uv run lint-imports · uv run fastapi dev
- frontend: npm run dev · npm run build · npm run lint · npm run gen:api

## Forma de trabajo
- Antes de terminar: compila, corre tests y lint-imports, y actualiza docs/progreso.md (máx 10 líneas por fase).
- No leas archivos que no necesitas. Pregunta si algo del alcance no está claro.

## Al compactar
Conserva: decisiones de arquitectura, archivos modificados, errores pendientes.