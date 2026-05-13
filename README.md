# Nexus Analytics Backend

Django backend for the real-time analytics and reporting platform. It provides multi-tenant authentication, organizations, API keys, ingestion, dashboards, analytics, alerts, reports, billing, health checks, Celery background jobs, and Channels WebSockets.

## Setup Instructions

Prerequisites:

- Python 3.13
- PostgreSQL 16, or Docker Compose from the repository root
- Redis 7 if running Celery and Channels with Redis locally

Create and activate a virtual environment:

```cmd
cd backend
python -m venv .venv
.venv\Scripts\activate
```

Install dependencies:

```cmd
python -m pip install -r requirements.txt
```

Create the local environment file:

```cmd
copy .env.example .env
```

Run database migrations and seed demo data:

```cmd
python manage.py migrate
python manage.py seed_demo
```

Start the development server:

```cmd
python manage.py runserver 8000
```

The API will be available at `http://localhost:8000/api/v1`.

Run validation checks:

```cmd
python manage.py check
set DJANGO_SETTINGS_MODULE=config.settings.test&& python manage.py makemigrations --check --dry-run
set DJANGO_SETTINGS_MODULE=config.settings.test&& python -m pytest -q
```

### Optional Redis, Celery, And WebSockets

Local development defaults to in-memory Celery and channel layers when `DJANGO_USE_REDIS=False`. To use Redis-backed realtime and background workers, set `DJANGO_USE_REDIS=True`, start Redis, then run these in separate terminals:

```cmd
python -m celery -A config worker --loglevel=info
python -m celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

For ASGI/Daphne locally:

```cmd
daphne -b 0.0.0.0 -p 8000 config.asgi:application
```

### Docker Compose

From the repository root:

```cmd
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_demo
```

Compose starts Postgres, Redis, Daphne, Celery worker, and Celery Beat.

## Architecture Overview

- `config/` contains Django settings, URL routing, ASGI/WSGI entry points, Celery configuration, and websocket routing.
- `accounts/` contains the custom user model, authentication endpoints, profile/settings endpoints, and demo seed command.
- `organizations/` contains tenant organization, membership, invitation, and role management.
- `api_keys/` manages hashed API keys used for ingestion access.
- `ingestion/` handles single-event ingestion, batch ingestion, CSV uploads, webhooks, schemas, validation, and normalization tasks.
- `dashboards/` provides dashboard, widget, template, public dashboard, and dashboard data APIs.
- `analytics/` computes traffic source, product usage, and revenue analytics.
- `alerts/` contains alert rule APIs, alert history, alert evaluation tasks, mute/resolve/reactivate flows, and realtime notifications.
- `reports/` contains report schedules, report runs, report generation tasks, and downloadable HTML report artifacts.
- `billing/` exposes usage, invoice, and subscription-style billing summary APIs.
- `realtime/` contains Channels consumers and JWT websocket authentication middleware.
- `common/` contains shared authentication, tenancy, permissions, throttling, exception handling, middleware, and realtime helpers.
- `tests/` contains pytest coverage for backend behavior.

The backend is a multi-tenant Django REST Framework API. Normal authenticated requests use JWT access tokens and resolve the active organization through membership. Ingestion requests use raw API keys or webhook source secrets to resolve the organization. Realtime messages are organization-scoped and delivered over JWT-authenticated WebSockets.

## Environment Variables

Copy `backend/.env.example` to `backend/.env` before running locally.

```env
DJANGO_SECRET_KEY=dev-only-change-this-secret-key-32-characters-minimum
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0
DATABASE_URL=postgres://analytics:analytics@localhost:5432/analytics
REDIS_URL=redis://localhost:6379/0
DJANGO_USE_REDIS=False
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
JWT_ACCESS_MINUTES=15
JWT_REFRESH_DAYS=7
JWT_REFRESH_COOKIE_SECURE=False
JWT_REFRESH_COOKIE_SAMESITE=Lax
```

| Variable | Required | Description |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Yes | Django signing secret. Use a strong unique value outside development. |
| `DJANGO_DEBUG` | No | Enables Django debug mode. Defaults to `False` in base settings; local settings force debug on. |
| `DJANGO_ALLOWED_HOSTS` | No | Comma-separated allowed hostnames. Defaults to `localhost`, `127.0.0.1`, and `0.0.0.0`. |
| `DATABASE_URL` | No | PostgreSQL connection string. Defaults to `postgres://analytics:analytics@localhost:5432/analytics`. |
| `REDIS_URL` | No | Redis URL used for cache, Channels, Celery broker, and Celery result backend when Redis is enabled. |
| `DJANGO_USE_REDIS` | No | In local settings, switches cache, Channels, and Celery from in-memory backends to Redis-backed services. |
| `CORS_ALLOWED_ORIGINS` | No | Comma-separated frontend origins allowed to call the API with credentials. |
| `JWT_ACCESS_MINUTES` | No | Access token lifetime in minutes. Defaults to `15`. |
| `JWT_REFRESH_DAYS` | No | Refresh token lifetime in days. Defaults to `7`. |
| `JWT_REFRESH_COOKIE_SECURE` | No | Controls whether the refresh cookie requires HTTPS. Defaults to secure when debug is off. |
| `JWT_REFRESH_COOKIE_SAMESITE` | No | SameSite policy for the refresh cookie. Defaults to `Lax`. |
| `CELERY_TASK_ALWAYS_EAGER` | No | Forces Celery tasks to run synchronously when set to true. Local settings enable eager mode when Redis is disabled. |
| `DJANGO_LOG_LEVEL` | No | Root logging level. Defaults to `INFO`. |

## Key Local URLs

- API root: `http://localhost:8000/api/v1`
- Health: `http://localhost:8000/api/v1/health/`
- Events websocket: `ws://localhost:8000/ws/events/?token=<ACCESS_TOKEN>`
- Alerts websocket: `ws://localhost:8000/ws/alerts/?token=<ACCESS_TOKEN>`
- Dashboards websocket: `ws://localhost:8000/ws/dashboards/?token=<ACCESS_TOKEN>`
