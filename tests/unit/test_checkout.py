from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest
from django.urls import reverse

from apps.bookings.models import Order, OrderItem

pytestmark = pytest.mark.django_db


def _checkout(client, resource):
    client.post(reverse('bookings:cart_add', args=[resource.id]), {'quantity': 2})
    return client.post(reverse('bookings:order_create'), {'first_name': 'Olena', 'email': 'olena@example.com'})


class TestOrderCreate:
    def test_uses_current_database_price(self, client, resource, stripe_session_create):
        client.post(reverse('bookings:cart_add', args=[resource.id]), {'quantity': 2})
        resource.price_per_hour = Decimal('99.90')
        resource.save()

        client.post(reverse('bookings:order_create'), {'first_name': 'Olena', 'email': 'olena@example.com'})

        assert OrderItem.objects.get().price == Decimal('99.90')
        line_item = stripe_session_create.call_args.kwargs['line_items'][0]
        assert line_item['price_data']['unit_amount'] == 9990

    def test_inactive_resource_in_cart_blocks_checkout(self, client, resource, stripe_session_create):
        client.post(reverse('bookings:cart_add', args=[resource.id]))
        resource.is_active = False
        resource.save()

        response = client.post(
            reverse('bookings:order_create'),
            {'first_name': 'Olena', 'email': 'olena@example.com'},
            follow=True,
        )

        assert response.redirect_chain[-1][0] == reverse('bookings:cart_detail')
        assert f'These resources are no longer available: {resource.name}' in [
            str(m) for m in response.context['messages']
        ]
        stripe_session_create.assert_not_called()
        assert Order.objects.count() == 0

    def test_currency_comes_from_settings(self, client, resource, stripe_session_create, settings):
        settings.STRIPE_CURRENCY = 'eur'
        _checkout(client, resource)
        assert stripe_session_create.call_args.kwargs['line_items'][0]['price_data']['currency'] == 'eur'


class TestPaymentSuccess:
    def test_concurrent_confirmation_sends_single_email(
        self, client, resource, stripe_session_create, mailoutbox, django_capture_on_commit_callbacks
    ):
        _checkout(client, resource)
        order = Order.objects.get()

        def paid_by_parallel_request(session_id):
            Order.objects.filter(pk=order.pk).update(paid=True)
            return SimpleNamespace(payment_status='paid')

        with mock.patch('apps.bookings.views.stripe.checkout.Session.retrieve', side_effect=paid_by_parallel_request):
            with django_capture_on_commit_callbacks(execute=True):
                response = client.get(reverse('bookings:payment_success'), {
                    'order_id': order.id, 'session_id': order.stripe_id,
                })

        assert response.status_code == 200
        assert mailoutbox == []

    def test_email_is_sent_only_after_commit(
        self, client, resource, stripe_session_create, stripe_session_retrieve, mailoutbox,
        django_capture_on_commit_callbacks,
    ):
        _checkout(client, resource)
        order = Order.objects.get()

        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            client.get(reverse('bookings:payment_success'), {'order_id': order.id, 'session_id': order.stripe_id})

        assert len(callbacks) == 1
        assert mailoutbox == []
        callbacks[0]()
        assert len(mailoutbox) == 1
