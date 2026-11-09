import pytest
from django.urls import reverse

from apps.resources.cache import get_catalog_version, get_resource_detail, invalidate_catalog
from apps.resources.models import Resource
from tests.factories import ResourceFactory

pytestmark = pytest.mark.django_db

API_LIST_URL = reverse('api:resource-list')


def detail_url(resource):
    return reverse('resources:resource_detail', kwargs={'slug': resource.slug})


def test_resource_detail_is_served_from_cache(resource, django_assert_num_queries):
    get_resource_detail(resource.slug)
    with django_assert_num_queries(0):
        cached = get_resource_detail(resource.slug)
    assert cached == resource
    assert cached.category.slug == resource.category.slug


def test_missing_resource_returns_none(db):
    assert get_resource_detail('nope') is None


def test_inactive_resource_is_not_cached_as_available():
    hidden = ResourceFactory(is_active=False)
    assert get_resource_detail(hidden.slug) is None


def test_detail_page_uses_low_level_cache(client, resource, django_assert_num_queries):
    assert client.get(detail_url(resource)).status_code == 200
    with django_assert_num_queries(0):
        assert client.get(detail_url(resource)).status_code == 200


def test_detail_page_of_unknown_resource_is_404(client, db):
    assert client.get(reverse('resources:resource_detail', kwargs={'slug': 'nope'})).status_code == 404


def test_saving_resource_invalidates_cache(resource, django_capture_on_commit_callbacks):
    get_resource_detail(resource.slug)

    with django_capture_on_commit_callbacks(execute=True):
        resource.name = 'Renamed'
        resource.save()

    assert get_resource_detail(resource.slug).name == 'Renamed'


def test_deleting_resource_invalidates_cache(resource, django_capture_on_commit_callbacks):
    get_resource_detail(resource.slug)

    with django_capture_on_commit_callbacks(execute=True):
        Resource.objects.get(pk=resource.pk).delete()

    assert get_resource_detail(resource.slug) is None


def test_saving_category_invalidates_nested_data(resource, django_capture_on_commit_callbacks):
    get_resource_detail(resource.slug)

    with django_capture_on_commit_callbacks(execute=True):
        resource.category.name = 'New Name'
        resource.category.save()

    assert get_resource_detail(resource.slug).category.name == 'New Name'


def test_invalidation_waits_for_commit(resource, django_capture_on_commit_callbacks):
    version = get_catalog_version()

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        resource.save()

    assert get_catalog_version() == version
    assert len(callbacks) == 1


def test_slug_change_does_not_keep_old_url_alive(resource, django_capture_on_commit_callbacks):
    old_slug = resource.slug
    get_resource_detail(old_slug)

    with django_capture_on_commit_callbacks(execute=True):
        resource.slug = 'moved'
        resource.save()

    assert get_resource_detail(old_slug) is None


def test_list_fragment_is_refreshed_after_invalidation(client, resource):
    assert 'Blue Room' in client.get(reverse('resources:resource_list')).content.decode()

    Resource.objects.filter(pk=resource.pk).update(name='Red Room')
    page = client.get(reverse('resources:resource_list')).content.decode()
    assert 'Blue Room' in page and 'Red Room' not in page

    invalidate_catalog()
    page = client.get(reverse('resources:resource_list')).content.decode()
    assert 'Red Room' in page


def test_list_fragment_depends_on_language(client, resource):
    client.get(reverse('resources:resource_list'), HTTP_ACCEPT_LANGUAGE='en')
    page = client.get(reverse('resources:resource_list'), HTTP_ACCEPT_LANGUAGE='uk').content.decode()
    assert '/год' in page
