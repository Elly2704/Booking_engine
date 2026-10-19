from types import SimpleNamespace
from unittest import mock

import pytest
from django.contrib.auth.models import Permission
from django.utils import translation

from tests.factories import (
    BookingFactory,
    OrderFactory,
    OrderItemFactory,
    ResourceCategoryFactory,
    ResourceFactory,
    UserFactory,
)

PASSWORD = 'StrongPass123!'


@pytest.fixture(autouse=True)
def _media_and_language(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / 'media'
    with translation.override('en'):
        yield


@pytest.fixture
def password():
    return PASSWORD


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def manager(db):
    manager = UserFactory(username='manager')
    manager.user_permissions.add(*Permission.objects.filter(
        content_type__app_label='resources',
        codename__in=['add_resource', 'change_resource', 'delete_resource'],
    ))
    return manager


@pytest.fixture
def manager_client(client, manager):
    client.force_login(manager)
    return client


@pytest.fixture
def category(db):
    return ResourceCategoryFactory(name='Rooms', slug='rooms')


@pytest.fixture
def resource(category):
    return ResourceFactory(category=category, name='Blue Room', slug='blue-room')


@pytest.fixture
def booking(user, resource):
    return BookingFactory(user=user, resource=resource)


@pytest.fixture
def order(user):
    return OrderFactory(user=user)


@pytest.fixture
def order_with_items(order, resource):
    OrderItemFactory(order=order, resource=resource, price=resource.price_per_hour, quantity=3)
    return order


@pytest.fixture
def stripe_session_create():
    session = SimpleNamespace(id='cs_test_mocked', url='https://checkout.stripe.test/pay/cs_test_mocked')
    with mock.patch('apps.bookings.views.stripe.checkout.Session.create', return_value=session) as patched:
        yield patched


@pytest.fixture
def stripe_session_retrieve():
    with mock.patch(
        'apps.bookings.views.stripe.checkout.Session.retrieve',
        return_value=SimpleNamespace(payment_status='paid'),
    ) as patched:
        yield patched
