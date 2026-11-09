import os

os.environ.setdefault('SECRET_KEY', 'test-secret-key-at-least-32-bytes-long')
os.environ['SENTRY_DSN'] = ''

from .settings import *

DEBUG = False

INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'debug_toolbar']
MIDDLEWARE = [m for m in MIDDLEWARE if m != 'debug_toolbar.middleware.DebugToolbarMiddleware']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

CELERY_BROKER_URL = 'memory://'
CELERY_TASK_ALWAYS_EAGER = True

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

LANGUAGE_CODE = 'en'

STRIPE_SECRET_KEY = 'sk_test_fake'
STRIPE_PUBLISHABLE_KEY = 'pk_test_fake'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'null': {'class': 'logging.NullHandler'}},
    'root': {'handlers': ['null'], 'level': 'CRITICAL'},
}
