import logging
from unittest import mock

import pytest
from django.urls import reverse

from apps.bookings.views import send_order_confirmation_email
from tests.factories import BookingFactory, OrderFactory, ResourceCategoryFactory, ResourceFactory, UserFactory

pytestmark = pytest.mark.django_db


class TestResourceViews:
    def test_list_shows_only_active(self, client, resource):
        ResourceFactory(name='Hidden Room', is_active=False)
        response = client.get(reverse('resources:resource_list'))
        assert response.status_code == 200
        names = [r.name for r in response.context['resources']]
        assert names == ['Blue Room']

    def test_list_search(self, client, resource):
        ResourceFactory(name='Conference Hall', description='Big')
        response = client.get(reverse('resources:resource_list'), {'q': 'conference'})
        assert [r.name for r in response.context['resources']] == ['Conference Hall']

    def test_list_category_filter(self, client, resource):
        other = ResourceFactory(category=ResourceCategoryFactory(slug='desks'))
        response = client.get(reverse('resources:resource_list'), {'category': other.category_id})
        assert list(response.context['resources']) == [other]

    def test_list_is_paginated(self, client):
        ResourceFactory.create_batch(8)
        response = client.get(reverse('resources:resource_list'))
        assert response.context['is_paginated'] is True
        assert len(response.context['resources']) == 6

    def test_detail(self, client, resource):
        response = client.get(reverse('resources:resource_detail', kwargs={'slug': resource.slug}))
        assert response.status_code == 200
        assert response.context['resource'] == resource

    def test_detail_404(self, client, db):
        assert client.get(reverse('resources:resource_detail', kwargs={'slug': 'missing'})).status_code == 404

    def test_create_requires_login(self, client, db):
        response = client.get(reverse('resources:resource_create'))
        assert response.status_code == 302
        assert reverse('users:login') in response.url

    def test_create_requires_permission(self, auth_client):
        assert auth_client.get(reverse('resources:resource_create')).status_code == 403

    def test_create_allowed_for_manager(self, manager_client):
        assert manager_client.get(reverse('resources:resource_create')).status_code == 200


class TestBookingViews:
    def test_list_requires_login(self, client, db):
        assert client.get(reverse('bookings:booking_list')).status_code == 302

    def test_list_shows_only_own_bookings(self, auth_client, booking):
        BookingFactory(resource=booking.resource, start_time=booking.end_time,
                       end_time=booking.end_time + (booking.end_time - booking.start_time))
        response = auth_client.get(reverse('bookings:booking_list'))
        assert list(response.context['bookings']) == [booking]

    def test_list_filter_by_status(self, auth_client, booking):
        response = auth_client.get(reverse('bookings:booking_list'), {'status': 'cancelled'})
        assert list(response.context['bookings']) == []

    def test_list_filter_by_resource(self, auth_client, booking):
        response = auth_client.get(reverse('bookings:booking_list'), {'resource': booking.resource_id})
        assert list(response.context['bookings']) == [booking]

    def test_cancel_view_cannot_be_used_anonymously(self, client, booking):
        response = client.post(reverse('bookings:booking_cancel', kwargs={'pk': booking.pk}))
        assert response.status_code == 302
        booking.refresh_from_db()
        assert booking.status == 'pending'


class TestCartAndPaymentViews:
    def test_cart_add_requires_post(self, client, resource):
        assert client.get(reverse('bookings:cart_add', args=[resource.id])).status_code == 405

    def test_cart_add_inactive_resource_404(self, client):
        resource = ResourceFactory(is_active=False)
        assert client.post(reverse('bookings:cart_add', args=[resource.id])).status_code == 404

    def test_cart_add_invalid_quantity_defaults_to_one(self, client, resource):
        client.post(reverse('bookings:cart_add', args=[resource.id]), {'quantity': 'abc'})
        assert client.session['cart'][str(resource.id)]['quantity'] == 1

    def test_cart_detail_empty(self, client, db):
        response = client.get(reverse('bookings:cart_detail'))
        assert response.status_code == 200
        assert 'Your cart is empty.' in response.content.decode()

    def test_order_create_with_empty_cart_redirects(self, client, db):
        response = client.get(reverse('bookings:order_create'), follow=True)
        assert response.redirect_chain[-1][0] == reverse('bookings:cart_detail')
        assert 'Your cart is empty.' in [str(m) for m in response.context['messages']]

    def test_order_create_prefills_user_data(self, auth_client, user, resource):
        auth_client.post(reverse('bookings:cart_add', args=[resource.id]))
        response = auth_client.get(reverse('bookings:order_create'))
        assert response.context['form'].initial['email'] == user.email

    def test_order_create_invalid_form_does_not_call_stripe(self, client, resource, stripe_session_create):
        client.post(reverse('bookings:cart_add', args=[resource.id]))
        response = client.post(reverse('bookings:order_create'), {'first_name': '', 'email': 'bad'})
        assert response.status_code == 200
        assert response.context['form'].errors
        stripe_session_create.assert_not_called()

    def test_payment_success_without_params_redirects(self, client, db):
        response = client.get(reverse('bookings:payment_success'))
        assert response.status_code == 302
        assert response.url == reverse('bookings:cart_detail')

    def test_payment_success_wrong_session_404(self, client, order):
        response = client.get(reverse('bookings:payment_success'), {'order_id': order.id, 'session_id': 'wrong'})
        assert response.status_code == 404

    def test_payment_cancel_shows_unpaid_order(self, client, order):
        response = client.get(reverse('bookings:payment_cancel'), {'order_id': order.id})
        assert response.context['order'] == order

    def test_payment_cancel_without_order(self, client, db):
        response = client.get(reverse('bookings:payment_cancel'))
        assert response.context['order'] is None


class TestConfirmationEmail:
    def test_email_is_sent(self, mailoutbox, order):
        send_order_confirmation_email(order)
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == [order.email]
        assert mailoutbox[0].subject == f'Order #{order.id}'

    def test_email_failure_is_logged(self, order, caplog):
        with mock.patch('apps.bookings.views.send_mail', side_effect=ConnectionError('smtp down')) as send:
            with caplog.at_level(logging.ERROR, logger='apps.bookings.views'):
                send_order_confirmation_email(order)
        send.assert_called_once()
        assert 'Failed to send email' in caplog.text


def test_request_timing_middleware_logs(client, db, caplog):
    with caplog.at_level(logging.INFO, logger='django'):
        client.get(reverse('resources:resource_list'))
    assert 'processed in' in caplog.text


def test_profile_requires_login(client, db):
    assert client.get(reverse('users:profile')).status_code == 302


def test_profile_edits_current_user(client, db):
    user = UserFactory()
    client.force_login(user)
    response = client.get(reverse('users:profile'))
    assert response.context['object'] == user


def test_order_factory_without_user():
    order = OrderFactory(user=None)
    assert order.first_name == 'Guest'
