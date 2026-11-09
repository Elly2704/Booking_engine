from decimal import Decimal

import pytest
from django.urls import reverse

from apps.bookings.models import CartItem, Order
from tests.factories import CartItemFactory, OrderFactory, OrderItemFactory, ResourceFactory

pytestmark = pytest.mark.django_db

CART_URL = reverse('api:cart-list')
SUMMARY_URL = reverse('api:cart-summary')
CLEAR_URL = reverse('api:cart-clear')
ORDERS_URL = reverse('api:order-list')
CONTACTS = {'first_name': 'Ann', 'last_name': 'Lee', 'email': 'ann@example.com'}


def cart_item_url(item):
    return reverse('api:cart-detail', args=[item.pk])


def order_url(order):
    return reverse('api:order-detail', args=[order.pk])


def test_cart_requires_authentication(api_client):
    assert api_client.get(CART_URL).status_code == 401


def test_add_resource_to_cart(user_client, user, resource):
    response = user_client.post(CART_URL, {'resource_id': resource.pk, 'quantity': 3})

    assert response.status_code == 201
    assert response.data['resource']['id'] == resource.pk
    assert Decimal(response.data['total_price']) == resource.price_per_hour * 3
    assert CartItem.objects.get().user == user


def test_adding_same_resource_increases_quantity(user_client, user, resource):
    CartItemFactory(user=user, resource=resource, quantity=2)

    response = user_client.post(CART_URL, {'resource_id': resource.pk, 'quantity': 3})

    assert response.status_code == 201
    assert response.data['quantity'] == 5
    assert CartItem.objects.count() == 1


def test_cannot_add_inactive_resource(user_client):
    response = user_client.post(CART_URL, {'resource_id': ResourceFactory(is_active=False).pk})
    assert response.status_code == 400


def test_quantity_must_be_positive(user_client, resource):
    response = user_client.post(CART_URL, {'resource_id': resource.pk, 'quantity': 0})
    assert response.status_code == 400
    assert 'quantity' in response.data


def test_update_quantity_keeps_resource(user_client, user, resource):
    item = CartItemFactory(user=user, resource=resource)
    response = user_client.patch(cart_item_url(item), {'quantity': 7, 'resource_id': ResourceFactory().pk})

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.quantity == 7
    assert item.resource == resource


def test_remove_cart_item(user_client, user):
    item = CartItemFactory(user=user)
    assert user_client.delete(cart_item_url(item)).status_code == 204
    assert not CartItem.objects.exists()


def test_cart_is_private_even_for_staff(staff_client, user):
    item = CartItemFactory(user=user)
    assert staff_client.get(CART_URL).data['count'] == 0
    assert staff_client.get(cart_item_url(item)).status_code == 404


def test_cart_summary_totals(user_client, user):
    CartItemFactory(user=user, resource=ResourceFactory(price_per_hour=Decimal('10.00')), quantity=2)
    CartItemFactory(user=user, resource=ResourceFactory(price_per_hour=Decimal('5.50')), quantity=1)

    response = user_client.get(SUMMARY_URL)

    assert response.status_code == 200
    assert len(response.data['items']) == 2
    assert response.data['total_items'] == 3
    assert Decimal(response.data['total_price']) == Decimal('25.50')


def test_empty_cart_summary(user_client):
    response = user_client.get(SUMMARY_URL)
    assert response.data['total_items'] == 0
    assert Decimal(response.data['total_price']) == 0


def test_clear_removes_only_own_items(user_client, user, other_user):
    CartItemFactory(user=user)
    foreign = CartItemFactory(user=other_user)

    assert user_client.delete(CLEAR_URL).status_code == 204
    assert list(CartItem.objects.all()) == [foreign]


def test_create_order_from_cart(user_client, user, resource):
    CartItemFactory(user=user, resource=resource, quantity=4)

    response = user_client.post(ORDERS_URL, CONTACTS)

    assert response.status_code == 201
    assert response.data['user'] == user.pk
    assert response.data['paid'] is False
    assert response.data['items'][0]['resource']['id'] == resource.pk
    assert response.data['items'][0]['quantity'] == 4
    assert Decimal(response.data['total_cost']) == resource.price_per_hour * 4
    assert not CartItem.objects.filter(user=user).exists()


def test_create_order_uses_current_price(user_client, user, resource):
    CartItemFactory(user=user, resource=resource, quantity=1)
    resource.price_per_hour = Decimal('99.00')
    resource.save()

    response = user_client.post(ORDERS_URL, CONTACTS)

    assert Decimal(response.data['items'][0]['price']) == Decimal('99.00')


def test_create_order_with_empty_cart_fails(user_client):
    response = user_client.post(ORDERS_URL, CONTACTS)
    assert response.status_code == 400
    assert not Order.objects.exists()


def test_create_order_with_unavailable_resource_keeps_cart(user_client, user):
    CartItemFactory(user=user, resource=ResourceFactory(is_active=False, name='Gone'))

    response = user_client.post(ORDERS_URL, CONTACTS)

    assert response.status_code == 400
    assert 'Gone' in response.data['non_field_errors'][0]
    assert not Order.objects.exists()
    assert CartItem.objects.filter(user=user).exists()


def test_create_order_requires_contacts(user_client, user):
    CartItemFactory(user=user)
    response = user_client.post(ORDERS_URL, {'first_name': 'Ann'})
    assert response.status_code == 400
    assert set(response.data) == {'email'}


def test_client_cannot_mark_order_as_paid(user_client, order):
    response = user_client.patch(order_url(order), {'paid': True})
    assert response.status_code == 200
    order.refresh_from_db()
    assert order.paid is False


def test_owner_can_update_contacts(user_client, order):
    response = user_client.patch(order_url(order), {'email': 'new@example.com'})
    assert response.status_code == 200
    assert response.data['email'] == 'new@example.com'


def test_order_list_is_limited_to_owner_and_nests_items(user_client, order_with_items, other_user):
    OrderFactory(user=other_user)

    response = user_client.get(ORDERS_URL)

    assert response.data['count'] == 1
    assert Decimal(response.data['results'][0]['total_cost']) == order_with_items.get_total_cost()


def test_order_list_has_no_n_plus_one(user_client, user, django_assert_max_num_queries):
    for _ in range(5):
        OrderItemFactory.create_batch(2, order=OrderFactory(user=user))

    with django_assert_max_num_queries(5):
        response = user_client.get(ORDERS_URL)

    assert response.data['count'] == 5


def test_filter_orders_by_paid(user_client, user, order):
    paid = OrderFactory(user=user, paid=True)
    response = user_client.get(ORDERS_URL, {'paid': 'true'})
    assert [row['id'] for row in response.data['results']] == [paid.pk]


def test_foreign_order_is_not_found(other_client, order):
    assert other_client.get(order_url(order)).status_code == 404


def test_staff_can_read_but_not_edit_foreign_order(staff_client, order):
    assert staff_client.get(order_url(order)).status_code == 200
    assert staff_client.patch(order_url(order), {'email': 'x@example.com'}).status_code == 403


def test_only_staff_can_delete_order(user_client, staff_client, order):
    assert user_client.delete(order_url(order)).status_code == 403
    assert staff_client.delete(order_url(order)).status_code == 204
