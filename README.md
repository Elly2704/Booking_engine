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
- **Tests**: 145 pytest tests with ~99% coverage, Stripe and email are mocked

## Tech stack

| | |
|---|---|
| Backend | Python 3.12, Django 6.1 |
| Database | PostgreSQL 16 |
| Payments | Stripe Checkout |
| Frontend | Django templates, Bootstrap 5 |
| Infrastructure | Docker, Docker Compose |
| Testing | pytest, pytest-django, pytest-cov, factory-boy |

## Getting started

### With Docker

```bash
cp .env.example .env        # then set SECRET_KEY and your Stripe test keys
docker compose up --build
```

Migrations run automatically on start. Open <http://localhost:8000>.

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_data            # demo data, 5 objects per model
```

Demo users created by `seed_data` use the password `StrongPass123!`.

### Locally

Requires Python 3.12 and a running PostgreSQL.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

### Environment variables

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | Django secret key | required |
| `DEBUG` | Debug mode, also enables Django Debug Toolbar | `False` |
| `ALLOWED_HOSTS` | Comma-separated host list | `localhost,127.0.0.1` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL connection | `booking_db`, `postgres`, empty, `localhost`, `5432` |
| `STRIPE_PUBLISHABLE_KEY`, `STRIPE_SECRET_KEY` | Stripe test keys | empty |
| `STRIPE_CURRENCY` | Checkout currency | `usd` |

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
├── unit/               models, forms, cart, views, async views, checkout, seed command
└── integration/        end-to-end user flows and i18n
```

## Project structure

```text
apps/
├── users/        custom User model (phone, avatar), registration, profile
├── resources/    categories and resources, catalogue, CRUD, statistics
└── bookings/     bookings, cart, orders, Stripe checkout, emails, async API, seed_data
config/           settings and URL configuration
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

## Translations

After changing translatable strings:

```bash
python manage.py makemessages -l uk -l en --ignore=.venv --ignore=tests
python manage.py compilemessages --ignore=.venv
```
