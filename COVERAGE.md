# Coverage Report

Згенеровано 2026-10-19 за допомогою `pytest-cov`. Вимога ДЗ: ≥ 60% для моделей, на яких генерувались тести.

## Моделі (тести згенеровані AI, `tests/unit/test_models.py`)

```bash
.venv/bin/pytest tests/unit/test_models.py -o addopts="" --cov-config=/dev/null \
  --cov=apps.bookings.models --cov=apps.resources.models --cov=apps.users.models --cov-branch --cov-report=term-missing
```

```text
Name                       Stmts   Miss Branch BrPart  Cover   Missing
----------------------------------------------------------------------
apps/bookings/models.py       66      1      8      1    97%   51->exit, 123
apps/resources/models.py      27      0      0      0   100%
apps/users/models.py          10      0      0      0   100%
----------------------------------------------------------------------
TOTAL                        103      1      8      1    98%
```

## Увесь проєкт (`.venv/bin/pytest`, 137 тестів)

```text
Name                                             Stmts   Miss Branch BrPart  Cover   Missing
--------------------------------------------------------------------------------------------
apps/__init__.py                                     0      0      0      0   100%
apps/bookings/__init__.py                            0      0      0      0   100%
apps/bookings/admin.py                              17      0      0      0   100%
apps/bookings/apps.py                                3      0      0      0   100%
apps/bookings/cart.py                               44      0     14      1    98%   33->exit
apps/bookings/forms.py                              13      0      0      0   100%
apps/bookings/management/__init__.py                 0      0      0      0   100%
apps/bookings/management/commands/__init__.py        0      0      0      0   100%
apps/bookings/management/commands/seed_data.py      45      0     10      0   100%
apps/bookings/models.py                             66      1      8      0    99%   123
apps/bookings/urls.py                                4      0      0      0   100%
apps/bookings/views.py                             198      0     36      0   100%
apps/resources/__init__.py                           0      0      0      0   100%
apps/resources/admin.py                             21      0      0      0   100%
apps/resources/apps.py                               3      0      0      0   100%
apps/resources/forms.py                             13      0      2      0   100%
apps/resources/models.py                            27      0      0      0   100%
apps/resources/urls.py                               4      0      0      0   100%
apps/resources/views.py                             48      0      4      0   100%
apps/users/__init__.py                               0      0      0      0   100%
apps/users/admin.py                                  9      0      0      0   100%
apps/users/apps.py                                   4      0      0      0   100%
apps/users/forms.py                                 24      0      6      0   100%
apps/users/models.py                                10      0      0      0   100%
apps/users/urls.py                                   4      0      0      0   100%
apps/users/views.py                                 23      0      0      0   100%
config/__init__.py                                   0      0      0      0   100%
config/middleware.py                                12      0      0      0   100%
config/settings.py                                  37      0      0      0   100%
config/urls.py                                      10      3      4      2    64%   15-16, 21
--------------------------------------------------------------------------------------------
TOTAL                                              639      4     84      3    99%
```

HTML-звіт генерується в `htmlcov/index.html` при кожному запуску `pytest`. Папка в `.gitignore`, тому звіт зафіксовано в цьому файлі.
