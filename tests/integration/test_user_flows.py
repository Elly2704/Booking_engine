from datetime import timedelta
from unittest import mock

import pytest
import stripe
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils.html import escape
from django.utils import timezone

from apps.bookings.models import Booking, Order
from apps.resources.models import Resource
from apps.users.models import User
from tests.factories import ResourceFactory, UserFactory
from tests.unit.test_forms import GIF

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _local(dt):
    return timezone.localtime(dt).strftime('%Y-%m-%dT%H:%M')


def _register(client, username='alice', **extra):
    data = {
        'username': username,
        'email': f'{username}@example.com',
        'phone': '+380671234567',
        'password1': 'VeryStrongPass987',
        'password2': 'VeryStrongPass987',
    }
    data.update(extra)
    return client.post(reverse('users:register'), data)


def _login(client, username, password='VeryStrongPass987'):
    return client.post(reverse('users:login'), {'username': username, 'password': password})


def _book(client, resource, start, hours=2):
    return client.post(
        reverse('bookings:booking_create', kwargs={'slug': resource.slug}),
        {'start_time': _local(start), 'end_time': _local(start + timedelta(hours=hours))},
    )


def _checkout(client, resource, quantity=2, **data):
    client.post(reverse('bookings:cart_add', args=[resource.id]), {'quantity': quantity})
    payload = {'first_name': 'Olena', 'last_name': 'Koval', 'email': 'olena@example.com'}
    payload.update(data)
    return client.post(reverse('bookings:order_create'), payload)


class TestAccountFlows:
    def test_register_login_and_see_username(self, client):
        response = _register(client)
        assert response.status_code == 302
        assert response.url == reverse('users:login')

        response = _login(client, 'alice')
        assert response.url == reverse('resources:resource_list')

        page = client.get(reverse('resources:resource_list')).content.decode()
        assert 'alice' in page
        assert 'Log Out' in page

    def test_register_with_avatar(self, client):
        avatar = SimpleUploadedFile('me.gif', GIF, content_type='image/gif')
        _register(client, 'bob', avatar=avatar)
        user = User.objects.get(username='bob')
        assert user.avatar.name.startswith('avatars/')

    def test_register_with_duplicate_username_fails(self, client):
        UserFactory(username='alice')
        response = _register(client)
        assert response.status_code == 200
        assert 'username' in response.context['form'].errors
        assert User.objects.filter(username='alice').count() == 1

    def test_login_with_wrong_password(self, client):
        UserFactory(username='carol')
        response = _login(client, 'carol', 'wrong-password')
        assert response.status_code == 200
        assert '_auth_user_id' not in client.session

    def test_profile_update_then_logout(self, client):
        user = UserFactory(username='dave')
        _login(client, 'dave', 'StrongPass123!')

        response = client.post(reverse('users:profile'), {
            'username': 'dave', 'email': 'dave.new@example.com', 'phone': '+380000000000',
        })
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.email == 'dave.new@example.com'

        client.post(reverse('users:logout'))
        assert client.get(reverse('bookings:booking_list')).status_code == 302

    def test_anonymous_is_redirected_to_login_and_back(self, client):
        UserFactory(username='erin')
        response = client.get(reverse('bookings:booking_list'))
        assert response.url == f"{reverse('users:login')}?next={reverse('bookings:booking_list')}"

        response = client.post(response.url, {'username': 'erin', 'password': 'StrongPass123!'})
        assert response.url == reverse('bookings:booking_list')


class TestBookingFlows:
    def test_browse_book_and_see_in_list(self, auth_client, resource):
        detail = auth_client.get(reverse('resources:resource_detail', kwargs={'slug': resource.slug}))
        assert 'Book This Resource' in detail.content.decode()

        response = _book(auth_client, resource, timezone.now() + timedelta(days=2))
        assert response.url == reverse('bookings:booking_list')

        page = auth_client.get(reverse('bookings:booking_list'))
        assert [b.resource for b in page.context['bookings']] == [resource]
        assert 'Pending' in page.content.decode()

    def test_overlapping_booking_is_rejected(self, client, resource):
        start = timezone.now() + timedelta(days=2)
        first, second = UserFactory(), UserFactory()

        client.force_login(first)
        _book(client, resource, start)

        client.force_login(second)
        response = _book(client, resource, start + timedelta(hours=1))
        assert response.status_code == 200
        assert 'already booked' in response.content.decode()
        assert Booking.objects.count() == 1

    def test_cancel_booking_frees_the_slot(self, auth_client, resource):
        start = timezone.now() + timedelta(days=2)
        _book(auth_client, resource, start)
        booking = Booking.objects.get()
        availability_url = reverse('bookings:resource_availability', kwargs={'slug': resource.slug})
        params = {'start': start.isoformat(), 'end': (start + timedelta(hours=1)).isoformat()}

        assert auth_client.get(availability_url, params).json()['available'] is False

        response = auth_client.post(reverse('bookings:booking_cancel', kwargs={'pk': booking.pk}))
        assert response.url == reverse('bookings:booking_list')
        booking.refresh_from_db()
        assert booking.status == 'cancelled'

        assert auth_client.get(availability_url, params).json()['available'] is True
        stats = auth_client.get(reverse('bookings:booking_stats')).json()
        assert stats['cancelled'] == 1
        assert stats['upcoming'] == []


class TestCheckoutFlows:
    def test_guest_checkout_redirects_to_stripe(self, client, resource, stripe_session_create):
        response = _checkout(client, resource, quantity=3)

        assert response.status_code == 303
        assert response.url == 'https://checkout.stripe.test/pay/cs_test_mocked'
        order = Order.objects.get()
        assert order.user is None
        assert order.stripe_id == 'cs_test_mocked'
        assert order.get_total_cost() == resource.price_per_hour * 3

        kwargs = stripe_session_create.call_args.kwargs
        assert kwargs['line_items'][0]['quantity'] == 3
        assert kwargs['line_items'][0]['price_data']['unit_amount'] == int(resource.price_per_hour * 100)
        assert kwargs['customer_email'] == 'olena@example.com'
        assert kwargs['client_reference_id'] == str(order.id)

    def test_full_paid_flow_sends_email_and_clears_cart(
        self, auth_client, user, resource, stripe_session_create, stripe_session_retrieve, mailoutbox,
        django_capture_on_commit_callbacks,
    ):
        _checkout(auth_client, resource)
        order = Order.objects.get()
        assert order.user == user

        with django_capture_on_commit_callbacks(execute=True):
            response = auth_client.get(reverse('bookings:payment_success'), {
                'order_id': order.id, 'session_id': order.stripe_id,
            })

        assert response.status_code == 200
        assert 'Payment Successful' in response.content.decode()
        order.refresh_from_db()
        assert order.paid is True
        assert 'cart' not in auth_client.session
        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ['olena@example.com']
        stripe_session_retrieve.assert_called_once_with('cs_test_mocked')

        orders_page = auth_client.get(reverse('bookings:booking_list'))
        assert list(orders_page.context['orders']) == [order]
        detail = auth_client.get(reverse('bookings:order_detail', kwargs={'pk': order.pk}))
        assert 'Paid' in detail.content.decode()

    def test_success_page_is_idempotent(
        self, client, resource, stripe_session_create, stripe_session_retrieve, mailoutbox,
        django_capture_on_commit_callbacks,
    ):
        _checkout(client, resource)
        order = Order.objects.get()
        params = {'order_id': order.id, 'session_id': order.stripe_id}

        with django_capture_on_commit_callbacks(execute=True):
            client.get(reverse('bookings:payment_success'), params)
            client.get(reverse('bookings:payment_success'), params)

        assert stripe_session_retrieve.call_count == 1
        assert len(mailoutbox) == 1

    def test_unpaid_session_keeps_order_unpaid(self, client, resource, stripe_session_create, mailoutbox):
        _checkout(client, resource)
        order = Order.objects.get()

        with mock.patch('apps.bookings.views.stripe.checkout.Session.retrieve',
                        return_value=mock.Mock(payment_status='unpaid')):
            response = client.get(reverse('bookings:payment_success'), {
                'order_id': order.id, 'session_id': order.stripe_id,
            })

        assert 'Payment Cancelled' in response.content.decode()
        order.refresh_from_db()
        assert order.paid is False
        assert len(client.session['cart']) == 1
        assert mailoutbox == []

    def test_stripe_error_rolls_back_order(self, client, resource):
        error = stripe.error.CardError('Your card was declined.', None, 'card_declined')
        with mock.patch('apps.bookings.views.stripe.checkout.Session.create', side_effect=error):
            response = _checkout(client, resource)

        assert response.status_code == 200
        assert Order.objects.count() == 0
        assert 'Payment error: Your card was declined.' in response.content.decode()
        assert len(client.session['cart']) == 1

    def test_unexpected_error_rolls_back_order(self, client, resource):
        with mock.patch('apps.bookings.views.stripe.checkout.Session.create', side_effect=RuntimeError('boom')):
            response = _checkout(client, resource)

        assert Order.objects.count() == 0
        assert 'Could not create order. Please try again.' in response.content.decode()

    def test_stripe_error_while_verifying_payment(self, client, resource, stripe_session_create):
        _checkout(client, resource)
        order = Order.objects.get()

        with mock.patch('apps.bookings.views.stripe.checkout.Session.retrieve',
                        side_effect=stripe.error.APIConnectionError('timeout')):
            response = client.get(reverse('bookings:payment_success'), {
                'order_id': order.id, 'session_id': order.stripe_id,
            }, follow=True)

        assert response.redirect_chain[-1][0] == reverse('bookings:cart_detail')
        assert 'Could not verify payment.' in response.content.decode()
        order.refresh_from_db()
        assert order.paid is False

    def test_cancelled_payment_keeps_cart(self, client, resource, stripe_session_create):
        _checkout(client, resource)
        order = Order.objects.get()

        response = client.get(reverse('bookings:payment_cancel'), {'order_id': order.id})

        assert f'#{order.id}' in response.content.decode()
        cart_page = client.get(reverse('bookings:cart_detail'))
        assert len(cart_page.context['cart']) == 2

    def test_add_and_remove_from_cart(self, client, resource):
        response = client.post(reverse('bookings:cart_add', args=[resource.id]), {'quantity': 2}, follow=True)
        assert escape(f'"{resource.name}" added to cart.') in response.content.decode()
        assert response.context['cart'].get_total_price() == resource.price_per_hour * 2

        client.post(reverse('bookings:cart_remove', args=[resource.id]))
        assert len(client.get(reverse('bookings:cart_detail')).context['cart']) == 0


class TestResourceManagementFlows:
    def test_manager_creates_updates_and_deletes_resource(self, manager_client, category):
        response = manager_client.post(reverse('resources:resource_create'), {
            'category': category.pk, 'name': 'Loft', 'slug': 'loft', 'description': 'Open space',
            'price_per_hour': '40.00', 'capacity': 20, 'is_active': True,
        })
        assert response.url == reverse('resources:resource_list')
        assert Resource.objects.filter(slug='loft').exists()

        response = manager_client.post(reverse('resources:resource_update', kwargs={'slug': 'loft'}), {
            'category': category.pk, 'name': 'Loft XL', 'slug': 'loft', 'description': 'Bigger',
            'price_per_hour': '55.00', 'capacity': 30, 'is_active': True,
        })
        assert response.url == reverse('resources:resource_detail', kwargs={'slug': 'loft'})
        assert Resource.objects.get(slug='loft').name == 'Loft XL'

        response = manager_client.post(reverse('resources:resource_delete', kwargs={'slug': 'loft'}))
        assert response.url == reverse('resources:resource_list')
        assert not Resource.objects.filter(slug='loft').exists()

    def test_regular_user_cannot_manage_resources(self, auth_client, resource):
        assert auth_client.post(reverse('resources:resource_update', kwargs={'slug': resource.slug})).status_code == 403
        assert auth_client.post(reverse('resources:resource_delete', kwargs={'slug': resource.slug})).status_code == 403
        assert Resource.objects.filter(pk=resource.pk).exists()

    def test_deactivated_resource_disappears_from_catalog_and_stats(self, manager_client, category):
        resource = ResourceFactory(category=category, name='Old Room')
        assert resource in manager_client.get(reverse('resources:resource_list')).context['resources']

        manager_client.post(reverse('resources:resource_update', kwargs={'slug': resource.slug}), {
            'category': category.pk, 'name': resource.name, 'slug': resource.slug,
            'price_per_hour': resource.price_per_hour, 'capacity': resource.capacity,
        })

        assert resource not in manager_client.get(reverse('resources:resource_list')).context['resources']
        stats = manager_client.get(reverse('resources:category_stats')).context
        assert stats['total_active'] == 0
