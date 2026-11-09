"""Rules that must hold the same way in every entry point: website, API and admin."""
from decimal import Decimal
from pathlib import Path
from unittest import mock

import pytest
from django.conf import settings as django_settings
from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from apps.bookings.cart import Cart
from apps.bookings.models import Booking, Order
from apps.resources.models import RESERVED_SLUGS
from apps.users.forms import MAX_AVATAR_SIZE
from tests.factories import BookingFactory, CartItemFactory, ResourceFactory, TINY_GIF, UserFactory

pytestmark = pytest.mark.django_db

RESOURCES_URL = reverse('api:resource-list')


def resource_payload(category, **overrides):
    return {
        'category_id': category.pk, 'name': 'New', 'slug': 'new-one',
        'price_per_hour': '10.00', 'capacity': 2, **overrides,
    }


@pytest.fixture
def staff_api(db):
    client = APIClient()
    client.force_authenticate(UserFactory(username='boss', is_staff=True))
    return client


@pytest.mark.parametrize('price', ['0.00', '-5.00'])
def test_api_rejects_non_positive_price(staff_api, category, price):
    response = staff_api.post(RESOURCES_URL, resource_payload(category, price_per_hour=price))
    assert response.status_code == 400
    assert 'price_per_hour' in response.data


def test_api_rejects_zero_capacity(staff_api, category):
    response = staff_api.post(RESOURCES_URL, resource_payload(category, capacity=0))
    assert response.status_code == 400


@pytest.mark.parametrize('slug', sorted(RESERVED_SLUGS))
def test_reserved_slug_is_rejected(staff_api, category, slug):
    response = staff_api.post(RESOURCES_URL, resource_payload(category, slug=slug))
    assert response.status_code == 400
    assert 'slug' in response.data


def test_model_validation_covers_price():
    resource = ResourceFactory.build(category=None, price_per_hour=Decimal('0'))
    with pytest.raises(ValidationError) as error:
        resource.clean_fields(exclude=['category'])
    assert 'price_per_hour' in error.value.message_dict


def test_order_survives_user_deletion(order):
    order.user.delete()
    order.refresh_from_db()
    assert order.user is None


def test_order_last_name_is_optional_in_api(user, resource):
    CartItemFactory(user=user, resource=resource)
    client = APIClient()
    client.force_authenticate(user)
    response = client.post(reverse('api:order-list'), {'first_name': 'Ann', 'email': 'ann@example.com'})
    assert response.status_code == 201


def test_session_cart_ignores_deleted_resources(rf, resource):
    request = rf.get('/')
    request.session = SessionStore()
    cart = Cart(request)
    cart.add(resource, quantity=3)
    assert len(cart) == 3

    resource.delete()

    assert len(cart) == 0


def test_checkout_with_only_deleted_resources_creates_no_order(client, resource, stripe_session_create):
    client.post(reverse('bookings:cart_add', args=[resource.id]))
    resource.delete()

    response = client.post(
        reverse('bookings:order_create'),
        {'first_name': 'A', 'last_name': 'B', 'email': 'a@example.com'},
    )

    assert response.status_code == 302
    assert not Order.objects.exists()
    stripe_session_create.assert_not_called()


def test_booking_save_locks_the_resource(user, resource):
    booking = BookingFactory.build(user=user, resource=resource)
    with mock.patch('apps.bookings.models.Resource.objects.select_for_update') as lock:
        booking.save()
    lock.assert_called_once()


def test_api_refuses_to_reschedule_cancelled_booking(user, resource):
    booking = BookingFactory(user=user, resource=resource, status=Booking.Status.CANCELLED)
    client = APIClient()
    client.force_authenticate(user)

    response = client.patch(reverse('api:booking-detail', args=[booking.pk]), {'end_time': booking.end_time})

    assert response.status_code == 400
    assert 'non_field_errors' in response.data


def test_api_enforces_avatar_size_limit(user):
    client = APIClient()
    client.force_authenticate(user)
    big = SimpleUploadedFile('a.gif', TINY_GIF + b'0' * MAX_AVATAR_SIZE, content_type='image/gif')

    response = client.patch(reverse('api:user-me'), {'avatar': big}, format='multipart')

    assert response.status_code == 400
    assert 'avatar' in response.data


def test_api_root_is_public(db):
    assert APIClient().get('/api/').status_code == 200



def test_nginx_body_limit_is_above_avatar_limit():
    conf = (Path(django_settings.BASE_DIR) / 'nginx' / 'default.conf').read_text()
    limit = next(line for line in conf.splitlines() if 'client_max_body_size' in line).split()[1].rstrip(';m')
    assert int(limit) * 1024 * 1024 > MAX_AVATAR_SIZE
