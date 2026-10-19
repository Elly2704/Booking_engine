from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone, translation

from apps.bookings.models import Booking
from tests.factories import (
    BookingFactory,
    OrderFactory,
    OrderItemFactory,
    ResourceCategoryFactory,
    ResourceFactory,
)

pytestmark = pytest.mark.django_db


class TestResourceModels:
    def test_category_str(self):
        # Generated with AI, reviewed and modified
        assert str(ResourceCategoryFactory(name='Halls')) == 'Halls'

    def test_resource_str_includes_capacity(self):
        # Generated with AI, reviewed and modified
        resource = ResourceFactory(name='Studio', capacity=8)
        assert str(resource) == 'Studio (8 capacity)'

    def test_resource_defaults(self, category):
        # Generated with AI, reviewed and modified
        resource = category.resources.create(name='Desk', slug='desk', price_per_hour=Decimal('5.00'))
        assert resource.is_active is True
        assert resource.capacity == 1

    def test_categories_ordered_by_name(self):
        # Generated with AI, reviewed and modified
        ResourceCategoryFactory(name='Zeta', slug='zeta')
        ResourceCategoryFactory(name='Alpha', slug='alpha')
        from apps.resources.models import ResourceCategory
        assert list(ResourceCategory.objects.values_list('name', flat=True)) == ['Alpha', 'Zeta']

    def test_verbose_name_is_translated(self):
        # Generated with AI, reviewed and modified
        from apps.resources.models import Resource
        with translation.override('uk'):
            assert str(Resource._meta.verbose_name) == 'Ресурс'
            assert str(Resource._meta.get_field('price_per_hour').verbose_name) == 'Ціна за годину'


class TestBookingModel:
    def test_str(self, booking):
        # Generated with AI, reviewed and modified
        assert str(booking) == f'{booking.user.username} - {booking.resource.name} (pending)'

    def test_end_before_start_is_invalid(self, user, resource):
        # Generated with AI, reviewed and modified
        start = timezone.now() + timedelta(days=1)
        with pytest.raises(ValidationError, match='End time must be greater than start time'):
            BookingFactory(user=user, resource=resource, start_time=start, end_time=start - timedelta(hours=1))

    def test_booking_in_past_is_invalid(self, user, resource):
        # Generated with AI, reviewed and modified
        start = timezone.now() - timedelta(days=1)
        with pytest.raises(ValidationError, match='Cannot book resources in the past'):
            BookingFactory(user=user, resource=resource, start_time=start)

    def test_overlapping_booking_is_invalid(self, booking):
        # Generated with AI, reviewed and modified
        with pytest.raises(ValidationError, match='already booked'):
            BookingFactory(
                resource=booking.resource,
                start_time=booking.start_time + timedelta(minutes=30),
                end_time=booking.end_time + timedelta(hours=1),
            )

    def test_overlap_with_cancelled_booking_is_allowed(self, booking):
        # Generated with AI, reviewed and modified
        booking.status = 'cancelled'
        booking.save()
        new = BookingFactory(resource=booking.resource, start_time=booking.start_time, end_time=booking.end_time)
        assert new.pk is not None

    def test_adjacent_bookings_are_allowed(self, booking):
        # Generated with AI, reviewed and modified
        new = BookingFactory(
            resource=booking.resource,
            start_time=booking.end_time,
            end_time=booking.end_time + timedelta(hours=1),
        )
        assert Booking.objects.filter(resource=booking.resource).count() == 2
        assert new.start_time == booking.end_time

    def test_resaving_existing_booking_does_not_conflict_with_itself(self, booking):
        # Generated with AI, reviewed and modified
        booking.status = 'confirmed'
        booking.save()
        booking.refresh_from_db()
        assert booking.status == 'confirmed'

    def test_same_time_on_other_resource_is_allowed(self, booking):
        # Generated with AI, reviewed and modified
        other = BookingFactory(start_time=booking.start_time, end_time=booking.end_time)
        assert other.resource != booking.resource

    def test_future_pending_booking_is_cancellable(self, booking):
        # Generated with AI, reviewed and modified
        assert booking.is_cancellable is True

    def test_cancelled_booking_is_not_cancellable(self, booking):
        # Generated with AI, reviewed and modified
        booking.status = 'cancelled'
        assert booking.is_cancellable is False

    def test_started_booking_is_not_cancellable(self, booking):
        # Generated with AI, reviewed and modified
        booking.start_time = timezone.now() - timedelta(minutes=1)
        assert booking.is_cancellable is False

    def test_status_display_is_translated(self, booking):
        # Generated with AI, reviewed and modified
        with translation.override('uk'):
            assert booking.get_status_display() == 'Очікує'
        with translation.override('en'):
            assert booking.get_status_display() == 'Pending'


class TestOrderModels:
    def test_order_str(self, order):
        # Generated with AI, reviewed and modified
        assert str(order) == f'Order {order.id}'

    def test_order_str_uk(self, order):
        # Generated with AI, reviewed and modified
        with translation.override('uk'):
            assert str(order) == f'Замовлення {order.id}'

    def test_order_item_cost(self):
        # Generated with AI, reviewed and modified
        item = OrderItemFactory(price=Decimal('12.50'), quantity=4)
        assert item.get_cost() == Decimal('50.00')

    def test_order_total_cost(self, order):
        # Generated with AI, reviewed and modified
        OrderItemFactory(order=order, price=Decimal('10.00'), quantity=2)
        OrderItemFactory(order=order, price=Decimal('7.50'), quantity=1)
        assert order.get_total_cost() == Decimal('27.50')

    def test_empty_order_total_is_zero(self):
        # Generated with AI, reviewed and modified
        assert OrderFactory(user=None).get_total_cost() == 0
