from functools import wraps
from uuid import uuid4

from django.core.cache import cache
from django.views.decorators.cache import cache_page

from .models import Resource

CATALOG_CACHE_TIMEOUT = 60 * 15
CATALOG_VERSION_KEY = 'catalog:version'


def get_catalog_version():
    """Current generation of the catalog; it is part of every catalog cache key."""
    return cache.get_or_set(CATALOG_VERSION_KEY, lambda: uuid4().hex, timeout=None)


def invalidate_catalog():
    """Switch to a new generation: all older entries become unreachable and expire on their own."""
    cache.set(CATALOG_VERSION_KEY, uuid4().hex, timeout=None)


def get_resource_detail(slug):
    """Active resource with its category, or None."""
    return cache.get_or_set(
        f'catalog:{get_catalog_version()}:resource:{slug}',
        lambda: Resource.objects.filter(slug=slug, is_active=True).select_related('category').first(),
        timeout=CATALOG_CACHE_TIMEOUT,
    )


def cache_catalog_page(view):
    """``cache_page`` whose entries are dropped together with the rest of the catalog."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        cached_view = cache_page(CATALOG_CACHE_TIMEOUT, key_prefix=f'catalog:{get_catalog_version()}')(view)
        return cached_view(request, *args, **kwargs)

    return wrapper
