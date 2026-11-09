from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.api.permissions import IsOwnerOrReadOnly
from apps.bookings.models import Booking
from tests.factories import BookingFactory, ResourceFactory, UserFactory

pytestmark = pytest.mark.django_db

LIST_URL = reverse('api:booking-list')


def detail_url(booking):
    return reverse('api:booking-detail', args=[booking.pk])


def cancel_url(booking):
    return reverse('api:booking-cancel', args=[booking.pk])


def payload(resource, start_in_days=3, hours=2):
    start = timezone.now() + timedelta(days=start_in_days)
    return {
        'resource_id': resource.pk,
        'start_time': start.isoformat(),
        'end_time': (start + timedelta(hours=hours)).isoformat(),
    }


def test_bookings_require_authentication(api_client):
    assert api_client.get(LIST_URL).status_code == 401


def test_create_booking_assigns_current_user(user_client, user, resource):
    response = user_client.post(LIST_URL, payload(resource))

    assert response.status_code == 201
    assert response.data['resource']['slug'] == resource.slug
    assert Booking.objects.get(pk=response.data['id']).user == user


def test_client_cannot_set_owner_or_status(user_client, user, other_user, resource):
    response = user_client.post(LIST_URL, {**payload(resource), 'user': other_user.pk, 'status': 'confirmed'})

    assert response.status_code == 201
    booking = Booking.objects.get(pk=response.data['id'])
    assert booking.user == user
    assert booking.status == Booking.Status.PENDING


def test_cannot_book_in_the_past(user_client, resource):
    response = user_client.post(LIST_URL, payload(resource, start_in_days=-1))
    assert response.status_code == 400
    assert 'non_field_errors' in response.data


def test_end_time_must_be_after_start_time(user_client, resource):
    response = user_client.post(LIST_URL, payload(resource, hours=-1))
    assert response.status_code == 400


def test_overlapping_booking_is_rejected(user_client, other_user, resource):
    start = timezone.now() + timedelta(days=3)
    BookingFactory(user=other_user, resource=resource, start_time=start, end_time=start + timedelta(hours=2))

    response = user_client.post(LIST_URL, {
        'resource_id': resource.pk,
        'start_time': (start + timedelta(hours=1)).isoformat(),
        'end_time': (start + timedelta(hours=3)).isoformat(),
    })

    assert response.status_code == 400
    assert 'already booked' in response.data['non_field_errors'][0]


def test_cannot_book_inactive_resource(user_client):
    response = user_client.post(LIST_URL, payload(ResourceFactory(is_active=False)))
    assert response.status_code == 400
    assert 'resource_id' in response.data


def test_list_contains_only_own_bookings(user_client, booking, other_user):
    BookingFactory(user=other_user)
    response = user_client.get(LIST_URL)
    assert [row['id'] for row in response.data['results']] == [booking.pk]


def test_staff_sees_all_bookings(staff_client, booking, other_user):
    BookingFactory(user=other_user)
    assert staff_client.get(LIST_URL).data['count'] == 2


def test_filter_bookings_by_status(user_client, user, booking):
    cancelled = BookingFactory(user=user, status=Booking.Status.CANCELLED)
    response = user_client.get(LIST_URL, {'status': 'cancelled'})
    assert [row['id'] for row in response.data['results']] == [cancelled.pk]


def test_foreign_booking_is_not_found(other_client, booking):
    assert other_client.get(detail_url(booking)).status_code == 404
    assert other_client.patch(detail_url(booking), {}).status_code == 404


def test_owner_can_reschedule_booking(user_client, booking):
    new_end = booking.start_time + timedelta(hours=5)
    response = user_client.patch(detail_url(booking), {'end_time': new_end.isoformat()})
    assert response.status_code == 200
    booking.refresh_from_db()
    assert booking.end_time == new_end


def test_invalid_reschedule_returns_400(user_client, booking):
    new_end = booking.start_time - timedelta(hours=1)
    response = user_client.patch(detail_url(booking), {'end_time': new_end.isoformat()})
    assert response.status_code == 400


def test_staff_can_read_but_not_edit_foreign_booking(staff_client, booking):
    assert staff_client.get(detail_url(booking)).status_code == 200
    assert staff_client.patch(detail_url(booking), {}).status_code == 403
    assert staff_client.post(cancel_url(booking)).status_code == 403


def test_owner_can_cancel_upcoming_booking(user_client, booking):
    response = user_client.post(cancel_url(booking))
    assert response.status_code == 200
    assert response.data['status'] == Booking.Status.CANCELLED
    assert response.data['is_cancellable'] is False


def test_cannot_cancel_twice(user_client, booking):
    user_client.post(cancel_url(booking))
    assert user_client.post(cancel_url(booking)).status_code == 400


def test_only_staff_can_delete_booking(user_client, staff_client, booking):
    assert user_client.delete(detail_url(booking)).status_code == 403
    assert staff_client.delete(detail_url(booking)).status_code == 204


@pytest.mark.parametrize(('method', 'is_owner', 'allowed'), [
    ('GET', False, True),
    ('PATCH', True, True),
    ('PATCH', False, False),
    ('DELETE', False, False),
])
def test_is_owner_or_read_only(method, is_owner, allowed):
    owner, stranger = UserFactory.build(pk=1), UserFactory.build(pk=2)
    request = SimpleNamespace(method=method, user=owner if is_owner else stranger)
    obj = SimpleNamespace(user_id=owner.pk)
    assert IsOwnerOrReadOnly().has_object_permission(request, None, obj) is allowed
