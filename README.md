# Booking Engine

A Django web application for booking rooms, desks, studios and other resources by the hour.
Users browse a catalogue, reserve a time slot or buy hours through a cart with **Stripe Checkout**.
The interface is available in **Ukrainian and English**.

## Features

- **Resource catalogue** with categories, search, filters, pagination and per-category statistics
- **Bookings** with model-level validation: no past dates, no overlapping slots; users can cancel only their own upcoming bookings
- **Cart and payments**: session cart, order + Stripe Checkout Session created in a single transaction, idempotent payment confirmation, email receipt
- **Accounts**: registration with avatar and phone, login/logout, profile editing
- **Permissions**: only staff with model permissions can create, edit or delete resources
- **Async views** using the async ORM: availability check API, booking statistics API, order details, category statistics
- **Internationalization**: Ukrainian (default) and English with a language switcher
- **REST API** on Django REST Framework: JWT auth, pagination, filtering, throttling, Swagger docs, CORS
- **Caching** in Redis: API view cache, template fragments and low-level resource cache, invalidated by signals
- **Background jobs**: Celery for confirmation emails, daily reports and session cleanup, scheduled by Celery Beat
- **Production stack**: NGINX reverse proxy and static files, Gunicorn, Sentry error monitoring
- **Tests**: 274 pytest tests with ~99% coverage, Stripe and email are mocked

## Tech stack

| | |
|---|---|
| Backend | Python 3.12, Django 6.1 |
| Database | PostgreSQL 16 |
| Cache and broker | Redis 7 |
| Background jobs | Celery, Celery Beat |
| Payments | Stripe Checkout |
| API | Django REST Framework, Simple JWT, django-filter, drf-spectacular, django-cors-headers |
| Frontend | Django templates, Bootstrap 5 |
| Infrastructure | Docker, Docker Compose, NGINX, Gunicorn, Sentry |
| Testing | pytest, pytest-django, pytest-cov, factory-boy |

## Getting started

### With Docker

```bash
cp .env.example .env        # then set SECRET_KEY and your Stripe test keys
docker compose up --build
```

Migrations and `collectstatic` run automatically on start. Open <http://localhost:8000>.
The source code is baked into the image, so rebuild with `docker compose up --build -d` after code changes.

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_data            # demo data, 5 objects per model
```

Demo users created by `seed_data` use the password `StrongPass123!`.

### Locally

Requires Python 3.12, a running PostgreSQL and Redis.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
celery -A config worker --loglevel=info   # background jobs, in a separate terminal
celery -A config beat --loglevel=info     # periodic jobs, in a separate terminal
```

### Environment variables

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | Django secret key | required |
| `DEBUG` | Debug mode, also enables Django Debug Toolbar | `False` |
| `ALLOWED_HOSTS` | Comma-separated host list | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated origins allowed to call `/api/` | `http://localhost:3000,http://127.0.0.1:3000` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL connection | `booking_db`, `postgres`, empty, `localhost`, `5432` |
| `STRIPE_PUBLISHABLE_KEY`, `STRIPE_SECRET_KEY` | Stripe test keys | empty |
| `STRIPE_CURRENCY` | Checkout currency | `usd` |
| `REDIS_URL` | Redis server, without a database number (cache uses db 1, Celery uses db 0) | `redis://localhost:6379` |
| `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL` | Outgoing mail | console backend, `noreply@bookingengine.com` |
| `SENTRY_DSN` | Sentry project; monitoring is off when empty | empty |
| `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE` | Sentry environment name and tracing share | `development`, `0.1` |
| `NUM_PROXIES` | Reverse proxies in front of the app, used by throttling (Compose sets it to 1) | `0` |
| `HTTP_PORT` | Compose: public NGINX port | `8000` |
| `DB_PUBLISHED_PORT` | Compose: PostgreSQL port on `127.0.0.1` of the host | `5433` |

For test payments use the Stripe card `4242 4242 4242 4242` with any future date and CVC.

## Running tests

```bash
pytest
```

Tests use `config/settings_test.py` (in-memory SQLite, no external services), so no database or Stripe account is needed.

```text
tests/
├── factories.py        factory-boy factories for all models
├── conftest.py         shared fixtures and Stripe mocks
├── api/                REST API: JWT, permissions, filters, throttling, CORS, docs
├── unit/               models, forms, cart, views, async views, checkout, seed command
└── integration/        end-to-end user flows and i18n
```

## Project structure

```text
apps/
├── users/        custom User model (phone, avatar), registration, profile
├── resources/    categories and resources, catalogue, CRUD, statistics
├── bookings/     bookings, cart, orders, Stripe checkout, emails, async API, seed_data
└── api/          REST API: serializers, viewsets, filters, permissions, routes
config/           settings, URL configuration, Celery app
nginx/            reverse proxy configuration
locale/           uk and en translations
templates/        base layout
static/           styles
```

## URLs

| URL | Description |
|---|---|
| `/` | Resource catalogue (`?q=`, `?category=`) |
| `/<slug>/` | Resource page |
| `/create/`, `/<slug>/update/`, `/<slug>/delete/` | Resource management (requires permissions) |
| `/stats/categories/` | Category statistics (async) |
| `/users/register/`, `/users/login/`, `/users/profile/` | Account |
| `/bookings/` | My bookings and orders |
| `/bookings/create/<slug>/` | Book a resource |
| `/bookings/<pk>/cancel/` | Cancel an upcoming booking |
| `/bookings/cart/` | Cart |
| `/bookings/order/create/` | Checkout, redirects to Stripe |
| `/bookings/orders/<pk>/` | Order details (async) |
| `/bookings/availability/<slug>/?start=&end=` | JSON: is the resource free in this period (async) |
| `/bookings/stats/` | JSON: the current user's booking statistics (async) |
| `/admin/` | Django admin |

## REST API

Interactive documentation is at `/api/docs/` (Swagger UI), the OpenAPI schema at `/api/schema/`.
Lists are paginated by 20 items. Throttling: 100 requests/hour for anonymous users, 1000/hour for authenticated ones.

```bash
curl -X POST localhost:8000/api/auth/token/ -H 'Content-Type: application/json' \
     -d '{"username": "...", "password": "..."}'
curl localhost:8000/api/bookings/ -H 'Authorization: Bearer <access>'
```

| Endpoint | Access | Filters and notes |
|---|---|---|
| `POST /api/auth/token/`, `/refresh/`, `/verify/` | public | JWT obtain, refresh, verify |
| `/api/categories/` | read: public, write: staff | `?slug=`, `?search=`, `?ordering=` |
| `/api/resources/` | read: public, write: staff | `?category=<slug>`, `?min_price=`, `?max_price=`, `?min_capacity=`, `?is_active=`, `?search=`, `?ordering=` |
| `/api/bookings/` | owner, staff read-only, delete: staff | `?status=`, `?resource=`, `?start_after=`, `?start_before=` |
| `POST /api/bookings/<id>/cancel/` | owner | Cancels an upcoming booking |
| `/api/cart/` | owner | `POST` with an existing resource increases its quantity |
| `GET /api/cart/summary/`, `DELETE /api/cart/clear/` | owner | Items with totals; empty the cart |
| `/api/orders/` | owner, staff read-only, delete: staff | `POST` creates an unpaid order from the cart; `?paid=`, `?created_after=`, `?created_before=` |
| `/api/users/`, `/api/users/me/` | authenticated | Users see only themselves, staff see everyone; `me` supports `PATCH` |

The API cart is stored in the database per user, because JWT clients have no session; it is separate from the session cart of the website.

## Infrastructure

`docker compose up` starts `db`, `redis`, `web` (Gunicorn), `celery`, `celery-beat` and `nginx`. NGINX is the only public entry point: it serves `/static/` and `/media/` and proxies everything else to Gunicorn.

**Caching.** Public API lists use the view cache, resource cards on the catalogue page use template fragments, and the resource page uses the low-level cache. All keys include a catalog version; saving or deleting a resource or a category replaces that version through signals after the transaction commits.

**Celery tasks** (`apps/bookings/tasks.py`):

| Task | When |
|---|---|
| `send_order_confirmation` | After a payment is confirmed, in the customer's language, with retries on mail errors |
| `generate_daily_report` | Daily at 00:30 UTC, writes `reports/report_<date>.csv` |
| `clear_expired_sessions` | Daily at 03:00 UTC |

## Translations

After changing translatable strings:

```bash
python manage.py makemessages -l uk -l en --ignore=.venv --ignore=tests
python manage.py compilemessages --ignore=.venv
```
