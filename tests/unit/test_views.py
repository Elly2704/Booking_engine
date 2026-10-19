import logging
from datetime import timedelta
from unittest import mock

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bookings.emails import send_order_confirmation_email
from apps.bookings.models import Booking
from tests.factories import BookingFactory, ResourceCategoryFactory, ResourceFactory, UserFactory

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
        with mock.patch('apps.bookings.emails.send_mail', side_effect=ConnectionError('smtp down')) as send:
            with caplog.at_level(logging.ERROR, logger='apps.bookings.emails'):
                send_order_confirmation_email(order)
        send.assert_called_once()
        assert 'Failed to send confirmation email' in caplog.text


def test_profile_requires_login(client, db):
    assert client.get(reverse('users:profile')).status_code == 302


def test_profile_edits_current_user(client, db):
    user = UserFactory()
    client.force_login(user)
    response = client.get(reverse('users:profile'))
    assert response.context['object'] == user


class TestBookingCancelAccess:
    def _cancel(self, client, booking):
        return client.post(reverse('bookings:booking_cancel', kwargs={'pk': booking.pk}))

    def test_cannot_cancel_foreign_booking(self, auth_client):
        foreign = BookingFactory(user=UserFactory())
        assert self._cancel(auth_client, foreign).status_code == 404
        foreign.refresh_from_db()
        assert foreign.status == 'pending'

    def test_cannot_open_foreign_cancel_page(self, auth_client):
        foreign = BookingFactory(user=UserFactory())
        assert auth_client.get(reverse('bookings:booking_cancel', kwargs={'pk': foreign.pk})).status_code == 404

    def test_cannot_cancel_twice(self, auth_client, booking):
        Booking.objects.filter(pk=booking.pk).update(status='cancelled')
        assert self._cancel(auth_client, booking).status_code == 404

    def test_cannot_cancel_started_booking(self, auth_client, booking):
        Booking.objects.filter(pk=booking.pk).update(
            start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=1),
        )
        assert self._cancel(auth_client, booking).status_code == 404

    def test_own_booking_cancel_shows_message(self, auth_client, booking):
        response = auth_client.post(reverse('bookings:booking_cancel', kwargs={'pk': booking.pk}), follow=True)
        booking.refresh_from_db()
        assert booking.status == 'cancelled'
        assert f'Booking for "{booking.resource.name}" has been cancelled.' in [
            str(m) for m in response.context['messages']
        ]


class TestInputHardening:
    def test_booking_list_ignores_invalid_filters(self, auth_client, booking):
        response = auth_client.get(reverse('bookings:booking_list'), {'status': 'unknown', 'resource': 'abc'})
        assert response.status_code == 200
        assert list(response.context['bookings']) == [booking]

    def test_resource_list_ignores_invalid_category(self, client, resource):
        response = client.get(reverse('resources:resource_list'), {'category': 'abc'})
        assert list(response.context['resources']) == [resource]

    def test_payment_cancel_ignores_invalid_order_id(self, client, db):
        response = client.get(reverse('bookings:payment_cancel'), {'order_id': 'abc'})
        assert response.status_code == 200
        assert response.context['order'] is None

    def test_inactive_resource_detail_is_404(self, client):
        resource = ResourceFactory(is_active=False)
        assert client.get(reverse('resources:resource_detail', kwargs={'slug': resource.slug})).status_code == 404

    def test_inactive_resource_cannot_be_booked(self, auth_client):
        resource = ResourceFactory(is_active=False)
        response = auth_client.post(
            reverse('bookings:booking_create', kwargs={'slug': resource.slug}),
            {'start_time': '2099-01-01T10:00', 'end_time': '2099-01-01T12:00'},
        )
        assert response.status_code == 404
        assert not Booking.objects.exists()


class TestCatalogueContext:
    def test_categories_available_for_filter(self, client, category):
        response = client.get(reverse('resources:resource_list'))
        assert list(response.context['categories']) == [category]

    def test_pagination_keeps_filters(self, client, category):
        ResourceFactory.create_batch(7, category=category, name='Room')
        page = client.get(reverse('resources:resource_list'), {'q': 'Room', 'category': category.id}).content.decode()
        assert f'?q=Room&category={category.id}&page=2' in page
