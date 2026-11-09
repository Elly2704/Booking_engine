from decimal import Decimal

import pytest
from django.urls import reverse

from tests.factories import ResourceFactory

pytestmark = pytest.mark.django_db

API_LIST_URL = reverse('api:resource-list')


def test_api_list_is_view_cached(api_client, resource, django_assert_num_queries):
    assert api_client.get(API_LIST_URL).data['count'] == 1
    with django_assert_num_queries(0):
        assert api_client.get(API_LIST_URL).status_code == 200


def test_api_list_cache_is_dropped_on_change(api_client, staff_client, resource, django_capture_on_commit_callbacks):
    api_client.get(API_LIST_URL)

    with django_capture_on_commit_callbacks(execute=True):
        response = staff_client.patch(
            reverse('api:resource-detail', args=[resource.pk]),
            {'price_per_hour': '77.00'},
        )
    assert response.status_code == 200

    fresh = api_client.get(API_LIST_URL).json()
    assert Decimal(fresh['results'][0]['price_per_hour']) == Decimal('77.00')


def test_api_cache_does_not_leak_staff_view_to_public(api_client, staff_client):
    ResourceFactory(is_active=False)
    assert staff_client.get(API_LIST_URL, HTTP_AUTHORIZATION='Bearer staff').data['count'] == 1
    assert api_client.get(API_LIST_URL).data['count'] == 0


def test_api_cache_separates_json_and_browsable(api_client, resource):
    api_client.get(API_LIST_URL, HTTP_ACCEPT='text/html')
    response = api_client.get(API_LIST_URL, HTTP_ACCEPT='application/json')
    assert response['Content-Type'].startswith('application/json')
