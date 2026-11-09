import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from tests.factories import UserFactory


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture(autouse=True)
def _reset_throttling():
    """Throttle counters live in the cache and must not leak between tests."""
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user_client(user):
    return _client_for(user)


@pytest.fixture
def other_user(db):
    return UserFactory(username='other')


@pytest.fixture
def other_client(other_user):
    return _client_for(other_user)


@pytest.fixture
def staff_user(db):
    return UserFactory(username='staff', is_staff=True)


@pytest.fixture
def staff_client(staff_user):
    return _client_for(staff_user)
