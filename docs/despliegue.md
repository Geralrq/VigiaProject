# Guía de despliegue — Vercel (Services)

## Pasos en la interfaz de Vercel

1. **Importar repositorio**: New Project → Import Git Repository → seleccionar este repo.
2. Vercel detecta dos servicios (`frontend/` y `backend/`) gracias al `vercel.json` con `services`.
3. **Servicio `web`** (Next.js): root directory `frontend`, framework Next.js — detección automática.
4. **Servicio `api`** (FastAPI): root directory `backend`, framework FastAPI, entrypoint `main:app`.
5. Configurar las variables de entorno de cada servicio (tabla abajo) antes del primer deploy.
6. Deploy. El dominio de producción queda en `https://<proyecto>.vercel.app`.

## Variables de entorno

Configurar en **Settings → Environment Variables** del proyecto. Marcar `Production` (y `Preview` si se quiere).

| Variable | Servicio | Descripción |
|---|---|---|
| `APP_MODE` | `api` | `demo` (sin llamadas externas) o `live` (Sentinel Hub + FIRMS reales) |
| `DATABASE_URL` | `api` | Pooler transaccional de Supabase, **puerto 6543**: `postgresql://postgres.[ref]:[pwd]@aws-0-*.pooler.supabase.com:6543/postgres` — el driver se convierte a `postgresql+psycopg://` automáticamente. Sin `options=-c search_path` |
| `SUPABASE_URL` | `api` | URL del proyecto Supabase, p. ej. `https://xxxx.supabase.co` |
| `SUPABASE_JWKS_URL` | `api` | Opcional; si se omite se deduce de `SUPABASE_URL` |
| `SUPABASE_SERVICE_KEY` | `api` | Service role key (secret). Para Storage y migraciones |
| `CRON_SECRET` | `api` | String aleatorio ≥16 caracteres. Vercel lo envía como `Authorization: Bearer <CRON_SECRET>` al invocar el cron |
| `TELEGRAM_BOT_TOKEN` | `api` | Token del bot de Telegram (BotFather) |
| `TELEGRAM_WEBHOOK_SECRET` | `api` | String aleatorio para validar las llamadas de Telegram al webhook |
| `TELEGRAM_LINK_SECRET` | `api` | Clave HMAC para los códigos de vinculación de cuenta |
| `TELEGRAM_BOT_USERNAME` | `api` | Username del bot sin @, p. ej. `VigiaBot` |
| `PUBLIC_APP_URL` | `api` | URL pública de la app, p. ej. `https://<proyecto>.vercel.app` |
| `NEXT_PUBLIC_SUPABASE_URL` | `web` | Igual que `SUPABASE_URL` — expuesta al navegador |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `web` | Anon/public key de Supabase |
| `NEXT_PUBLIC_APP_MODE` | `web` | `demo` o `live`; controla la UI del perfil (chat_id manual solo en demo) |
| `API_INTERNAL_URL` | `web` | URL interna del servicio `api` para SSR. Con Services en el mismo proyecto usar `https://<proyecto>.vercel.app`; dejar vacío en local (usa `localhost:8000`) |

> **Modo demo**: con `APP_MODE=demo` el backend usa adaptadores deterministas sin llamar a Sentinel Hub ni FIRMS. No se necesitan `SENTINEL_CLIENT_ID/SECRET` ni `FIRMS_MAP_KEY`. Ideal para verificar el despliegue antes de activar live.

## Ajustes en Supabase tras el despliegue

En **Authentication → URL Configuration**:
- **Site URL**: `https://<proyecto>.vercel.app`
- **Redirect URLs**: añadir `https://<proyecto>.vercel.app/**`

## Registrar el webhook de Telegram

```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=https://<proyecto>.vercel.app/api/telegram/webhook" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"
```

Verificar con `getWebhookInfo`: debe mostrar `pending_update_count: 0` y sin errores.

## Lista de verificación posterior

- [ ] `GET /api/health` → `{"status":"ok"}`
- [ ] Login con cuenta real (`/login`) y navegación a `/mapa`
- [ ] Capas del mapa cargan (zonas, anomalías, alertas)
- [ ] Cron manual: `curl -H "Authorization: Bearer $CRON_SECRET" https://<proyecto>.vercel.app/api/jobs/scan`
- [ ] Ficha pública `/a/<uuid-de-alerta>` responde con Open Graph correcto
- [ ] Descargar PDF de inspección (requiere rol TECNICO/AUTORIDAD/ADMIN)
- [ ] Revisar logs en Vercel → Functions para errores de inicio

## Plan B: dos proyectos separados

Si Services da problemas (aún es beta), despliega dos proyectos independientes:
- **Proyecto `vigia-api`**: root `backend/`, framework FastAPI; dominio `vigia-api.vercel.app`.
- **Proyecto `vigia-web`**: root `frontend/`, framework Next.js; `API_INTERNAL_URL=https://vigia-api.vercel.app`; sin `services` en `vercel.json`.
- En `next.config.ts` el rewrite de `/api/:path*` apunta a `vigia-api.vercel.app` condicionado a `!process.env.VERCEL` → añadir rama para el dominio de la API externa.
- Ajustar `CORS_ORIGINS` en el backend para incluir el dominio del frontend.
