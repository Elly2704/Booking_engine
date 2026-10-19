import asyncio
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.bookings import views as booking_views
from apps.resources import views as resource_views
from tests.factories import BookingFactory, OrderFactory, OrderItemFactory, ResourceFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('view', [
    booking_views.resource_availability,
    booking_views.booking_stats,
    booking_views.order_detail,
    resource_views.category_stats,
])
def test_views_are_coroutines(view):
    assert asyncio.iscoroutinefunction(view)


class TestResourceAvailability:
    def _url(self, resource):
        return reverse('bookings:resource_availability', kwargs={'slug': resource.slug})

    def test_free_slot(self, client, resource):
        start = timezone.now() + timedelta(days=3)
        response = client.get(self._url(resource), {
            'start': start.isoformat(), 'end': (start + timedelta(hours=1)).isoformat(),
        })
        assert response.status_code == 200
        assert response.json()['available'] is True

    def test_booked_slot(self, client, booking):
        response = client.get(self._url(booking.resource), {
            'start': (booking.start_time + timedelta(minutes=15)).isoformat(),
            'end': (booking.end_time + timedelta(minutes=15)).isoformat(),
        })
        assert response.json()['available'] is False

    def test_naive_datetimes_are_accepted(self, client, resource):
        response = client.get(self._url(resource), {'start': '2099-01-01T10:00', 'end': '2099-01-01T12:00'})
        assert response.status_code == 200
        assert response.json()['available'] is True

    def test_missing_params(self, client, resource):
        response = client.get(self._url(resource))
        assert response.status_code == 400
        assert 'required' in response.json()['error']

    def test_end_before_start(self, client, resource):
        response = client.get(self._url(resource), {'start': '2099-01-01T12:00', 'end': '2099-01-01T10:00'})
        assert response.status_code == 400

    def test_unknown_resource(self, client, db):
        response = client.get(reverse('bookings:resource_availability', kwargs={'slug': 'nope'}))
        assert response.status_code == 404

    def test_post_not_allowed(self, client, resource):
        assert client.post(self._url(resource)).status_code == 405


class TestBookingStats:
    def test_requires_login(self, client, db):
        response = client.get(reverse('bookings:booking_stats'))
        assert response.status_code == 302

    def test_counts(self, auth_client, user, resource):
        start = timezone.now() + timedelta(days=1)
        BookingFactory(user=user, resource=resource, start_time=start, end_time=start + timedelta(hours=1))
        BookingFactory(user=user, resource=resource, start_time=start + timedelta(hours=2),
                       end_time=start + timedelta(hours=3), status='confirmed')
        BookingFactory(user=user, resource=resource, start_time=start + timedelta(hours=4),
                       end_time=start + timedelta(hours=5), status='cancelled')
        BookingFactory(resource=resource, start_time=start + timedelta(hours=6), end_time=start + timedelta(hours=7))
        OrderFactory(user=user, paid=True)
        OrderFactory(user=user, paid=False)

        data = auth_client.get(reverse('bookings:booking_stats')).json()

        assert data['total'] == 3
        assert data['pending'] == 1
        assert data['confirmed'] == 1
        assert data['cancelled'] == 1
        assert data['paid_orders'] == 1
        assert [b['status'] for b in data['upcoming']] == ['pending', 'confirmed']
        assert data['upcoming'][0]['resource'] == resource.name


class TestOrderDetail:
    def test_own_order(self, auth_client, order_with_items):
        response = auth_client.get(reverse('bookings:order_detail', kwargs={'pk': order_with_items.pk}))
        assert response.status_code == 200
        assert response.context['total'] == order_with_items.get_total_cost()
        assert len(response.context['items']) == 1

    def test_foreign_order_404(self, auth_client):
        order = OrderFactory(user=UserFactory())
        assert auth_client.get(reverse('bookings:order_detail', kwargs={'pk': order.pk})).status_code == 404

    def test_requires_login(self, client, order):
        assert client.get(reverse('bookings:order_detail', kwargs={'pk': order.pk})).status_code == 302


class TestCategoryStats:
    def test_aggregates_active_resources(self, client, category):
        ResourceFactory(category=category, price_per_hour=10)
        ResourceFactory(category=category, price_per_hour=30)
        ResourceFactory(category=category, price_per_hour=1000, is_active=False)

        response = client.get(reverse('resources:category_stats'))

        assert response.status_code == 200
        stats = {c.name: c for c in response.context['categories']}
        assert stats['Rooms'].total_resources == 2
        assert stats['Rooms'].avg_price == 20
        assert response.context['total_active'] == 2
        assert '2 active resources in total.' in response.content.decode()

    def test_empty(self, client, db):
        response = client.get(reverse('resources:category_stats'))
        assert 'No categories found.' in response.content.decode()
