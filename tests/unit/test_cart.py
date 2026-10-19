from decimal import Decimal

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory

from apps.bookings.cart import Cart
from tests.factories import ResourceFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def cart_request():
    request = RequestFactory().get('/')
    request.session = SessionStore()
    return request


def test_add_and_len(cart_request, resource):
    cart = Cart(cart_request)
    cart.add(resource, quantity=2)
    cart.add(resource, quantity=3)
    assert len(cart) == 5


def test_override_quantity(cart_request, resource):
    cart = Cart(cart_request)
    cart.add(resource, quantity=2)
    cart.add(resource, quantity=1, override_quantity=True)
    assert len(cart) == 1


def test_total_price_and_iteration(cart_request):
    first = ResourceFactory(price_per_hour=Decimal('10.00'))
    second = ResourceFactory(price_per_hour=Decimal('2.50'))
    cart = Cart(cart_request)
    cart.add(first, quantity=2)
    cart.add(second, quantity=4)
    assert cart.get_total_price() == Decimal('30.00')
    items = {item['resource'].pk: item for item in cart}
    assert items[first.pk]['total_price'] == Decimal('20.00')


def test_remove_and_clear(cart_request, resource):
    cart = Cart(cart_request)
    cart.add(resource)
    cart.remove(resource)
    assert len(cart) == 0
    cart.add(resource)
    cart.clear()
    assert 'cart' not in cart_request.session


def test_iteration_skips_deleted_resources(cart_request, resource):
    cart = Cart(cart_request)
    cart.add(resource)
    resource.delete()
    assert list(cart) == []


def test_prices_follow_database(cart_request, resource):
    cart = Cart(cart_request)
    cart.add(resource, quantity=2)
    resource.price_per_hour = Decimal('40.00')
    resource.save()
    assert cart.get_total_price() == Decimal('80.00')
