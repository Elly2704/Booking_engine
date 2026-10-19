# Booking Engine

Веб-застосунок для онлайн-бронювання ресурсів (переговорні, коворкінг, студії, зали) на **Django 6.1**.
Користувачі переглядають каталог, бронюють ресурс на конкретний час або купують години через кошик
з оплатою **Stripe Checkout**. Інтерфейс доступний українською та англійською.

## Можливості

- **Каталог ресурсів**: категорії, пошук, пагінація, статистика по категоріях.
- **Бронювання**: перевірка дат і перетинів на рівні моделі, список своїх бронювань, скасування майбутніх бронювань (тільки власних).
- **Кошик і оплата**: кошик у сесії, замовлення і Stripe Checkout Session в одній транзакції, підтвердження оплати із захистом від подвійної обробки, лист-підтвердження.
- **Користувачі**: реєстрація з аватаром і телефоном, вхід/вихід, редагування профілю.
- **Права доступу**: створювати, редагувати й видаляти ресурси можуть лише користувачі з відповідними permissions.
- **Async views** з async ORM: перевірка доступності, статистика бронювань, деталі замовлення, статистика категорій.
- **i18n**: українська (за замовчуванням) і англійська, перемикач мови в шапці сайту.

## Стек

| Шар | Технології |
|-----|-----------|
| Backend | Python 3.12, Django 6.1, python-decouple |
| БД | PostgreSQL 16 (у тестах — SQLite in-memory) |
| Платежі | Stripe Checkout (`stripe` 16) |
| Frontend | Django templates, Bootstrap 5 |
| Інфраструктура | Docker, docker compose |
| Тести | pytest, pytest-django, pytest-cov, factory-boy, Faker, unittest.mock |
| Dev | django-debug-toolbar |

## Структура проєкту

```text
apps/
  users/        кастомна модель User (phone, avatar), реєстрація, профіль
  resources/    ResourceCategory, Resource, CRUD, async статистика категорій
  bookings/     Booking, Order, OrderItem, кошик (cart.py), Stripe, async API,
                management-команда seed_data
config/         settings.py, settings_test.py, urls.py, middleware (час обробки запиту)
locale/         uk/ та en/ — .po і .mo файли перекладів
templates/      base.html
tests/          factories.py, conftest.py, unit/, integration/
```

## Запуск через Docker

1. Створіть `.env` у корені проєкту:

   ```env
   DEBUG=True
   SECRET_KEY=your-secret-key
   DB_NAME=booking_db
   DB_USER=postgres
   DB_PASSWORD=postgres
   DB_HOST=db
   DB_PORT=5432
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_CURRENCY=usd
   ```

2. Запустіть контейнери, застосуйте міграції і створіть адміністратора:

   ```bash
   docker compose up -d --build
   docker compose exec web python manage.py migrate
   docker compose exec web python manage.py createsuperuser
   ```

3. За бажанням заповніть базу тестовими даними (по 5 записів кожної моделі, пароль користувачів `StrongPass123!`):

   ```bash
   docker compose exec web python manage.py seed_data
   docker compose exec web python manage.py seed_data --count 10
   ```

Сайт: <http://localhost:8000>, адмінка: <http://localhost:8000/admin/>.

## Локальний запуск без Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# у .env вкажіть DB_HOST=localhost і запущений PostgreSQL
python manage.py migrate
python manage.py runserver
```

## Тести і coverage

```bash
.venv/bin/pytest
```

- 137 тестів: unit (моделі, форми, кошик, views, async views, виправлення після code review, seed_data) та integration (повні сценарії користувача, i18n).
- Тести використовують `config.settings_test`: SQLite in-memory, без debug toolbar, пошта в `mailoutbox`.
- Stripe завжди мокається (`unittest.mock.patch`), тож реальні запити до Stripe не відправляються.
- Поріг покриття `--cov-fail-under=70`, поточне покриття **99%**. HTML-звіт: `htmlcov/index.html`, зведення: [COVERAGE.md](COVERAGE.md).

## Інтернаціоналізація

Переклади лежать у `locale/<lang>/LC_MESSAGES/django.po`. Після зміни текстів:

```bash
python manage.py makemessages -l uk -l en --ignore=.venv --ignore=tests
python manage.py compilemessages --ignore=.venv
```

Мова визначається з сесії/cookie (перемикач у шапці, `POST /i18n/setlang/`) або із заголовка `Accept-Language`.

## URL

| URL | Опис |
|-----|------|
| `/` | Каталог ресурсів (`?q=`, `?category=`) |
| `/<slug>/` | Сторінка ресурсу |
| `/create/`, `/<slug>/update/`, `/<slug>/delete/` | CRUD ресурсів (потрібні permissions) |
| `/stats/categories/` | **async** — статистика по категоріях |
| `/users/register/`, `/users/login/`, `/users/logout/`, `/users/profile/` | Акаунт |
| `/bookings/` | Мої бронювання і замовлення |
| `/bookings/create/<slug>/` | Забронювати ресурс |
| `/bookings/<pk>/cancel/` | Скасувати своє майбутнє бронювання |
| `/bookings/cart/`, `/bookings/cart/add/<id>/`, `/bookings/cart/remove/<id>/` | Кошик |
| `/bookings/order/create/` | Оформлення замовлення, редирект на Stripe |
| `/bookings/payment/success/`, `/bookings/payment/cancel/` | Повернення зі Stripe |
| `/bookings/orders/<pk>/` | **async** — деталі замовлення |
| `/bookings/availability/<slug>/?start=&end=` | **async JSON** — чи вільний ресурс |
| `/bookings/stats/` | **async JSON** — статистика бронювань користувача |
| `/i18n/setlang/` | Зміна мови |

## AI Usage

Під час розробки використовувався **Claude Code** (CLI-агент Anthropic). Агент працював прямо в репозиторії:
читав код, запускав тести і вносив зміни, а кожен результат перевірявся вручну.

**Для чого використовувався AI:**

| Задача | Результат |
|--------|-----------|
| Code review 3 views (`BookingCancelView`, `order_create`, `payment_success`) | Знайдено і виправлено IDOR (скасування чужих бронювань), застарілу ціну з сесії, оплату деактивованих ресурсів, race condition з подвійним листом. Частину рекомендацій відхилено з поясненням. Деталі: [AI_REVIEW.md](AI_REVIEW.md) |
| Генерація тестів для моделей `Booking`, `Order`/`OrderItem`, `Resource`/`ResourceCategory` | 22 тести з позначкою `# Generated with AI, reviewed and modified`, покриття моделей 98% |
| Docstrings | Для всіх views у `apps/*/views.py` |
| README | Цей файл |
| i18n, async views, тестова інфраструктура (ДЗ 24.1) | Переклади uk/en, 4 async views, factory-boy фабрики, моки Stripe і пошти |
| DevOps | Діагностика Docker-мережі, команда `seed_data`, виправлення sequence у PostgreSQL |

**Основні промпти:**

- *Code review:* «Зроби code review цього Django view. Шукай: проблеми безпеки (IDOR), race conditions і транзакційність, коректність грошових розрахунків, обробку помилок Stripe/SMTP, граничні випадки. Для кожної знахідки вкажи серйозність і виправлення. Підтверди проблему тестом перед виправленням.»
- *Тести:* «Згенеруй pytest-django тести для моделей Booking, Order/OrderItem, Resource/ResourceCategory: `__str__`, defaults, ordering, валідація `clean()`, розрахунки вартості, переклади. Використовуй фабрики з `tests/factories.py`.»
- *Docstrings:* «Напиши docstrings для всіх views: що робить, методи і параметри, права доступу, поведінка у крайніх випадках.»
- *README:* «Згенеруй README на основі коду проєкту, включно з секцією AI Usage.»

Повний список промптів: [AI_PROMPTS.md](AI_PROMPTS.md).

**Що варто знати про роботу з AI:** не всі рекомендації були правильними. Наприклад, AI вважав, що
`int(price * 100)` обрізає копійки, хоча `price` має тип `Decimal` і похибки немає. Тому кожна знахідка
спочатку перевірялась тестом, а вже потім застосовувалась або відхилялась.
