from unittest import mock

import pytest
from django.urls import reverse
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

pytestmark = pytest.mark.django_db

RESOURCES_URL = reverse('api:resource-list')
ALLOWED_ORIGIN = 'http://localhost:3000'


def preflight(api_client, origin):
    return api_client.options(
        RESOURCES_URL,
        HTTP_ORIGIN=origin,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
    )


def test_anonymous_requests_are_throttled(api_client):
    with mock.patch.object(AnonRateThrottle, 'THROTTLE_RATES', {'anon': '2/minute'}):
        codes = [api_client.get(RESOURCES_URL).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_authenticated_requests_are_throttled(user_client):
    with mock.patch.object(UserRateThrottle, 'THROTTLE_RATES', {'user': '1/minute'}):
        codes = [user_client.get(RESOURCES_URL).status_code for _ in range(2)]
    assert codes == [200, 429]


def test_cors_allows_configured_origin(api_client):
    response = preflight(api_client, ALLOWED_ORIGIN)
    assert response['Access-Control-Allow-Origin'] == ALLOWED_ORIGIN


def test_cors_rejects_unknown_origin(api_client):
    assert 'Access-Control-Allow-Origin' not in preflight(api_client, 'https://evil.example')


def test_cors_applies_only_to_api(client):
    response = client.get(reverse('resources:resource_list'), HTTP_ORIGIN=ALLOWED_ORIGIN)
    assert 'Access-Control-Allow-Origin' not in response


def test_swagger_docs_are_available(api_client):
    response = api_client.get('/api/docs/')
    assert response.status_code == 200
    assert 'swagger' in response.content.decode().lower()


def test_schema_describes_all_endpoints(api_client):
    response = api_client.get(reverse('api:schema'), {'format': 'json'})

    assert response.status_code == 200
    paths = response.json()['paths']
    for path in ('resources', 'categories', 'bookings', 'orders', 'cart', 'users'):
        assert f'/api/{path}/' in paths
    assert '/api/auth/token/' in paths
