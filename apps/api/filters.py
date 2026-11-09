import django_filters

from apps.bookings.models import Booking, Order
from apps.resources.models import Resource


class ResourceFilter(django_filters.FilterSet):
    category = django_filters.CharFilter(field_name='category__slug')
    min_price = django_filters.NumberFilter(field_name='price_per_hour', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='price_per_hour', lookup_expr='lte')
    min_capacity = django_filters.NumberFilter(field_name='capacity', lookup_expr='gte')

    class Meta:
        model = Resource
        fields = ['category', 'min_price', 'max_price', 'min_capacity', 'is_active']


class BookingFilter(django_filters.FilterSet):
    start_after = django_filters.IsoDateTimeFilter(field_name='start_time', lookup_expr='gte')
    start_before = django_filters.IsoDateTimeFilter(field_name='start_time', lookup_expr='lte')

    class Meta:
        model = Booking
        fields = ['status', 'resource', 'start_after', 'start_before']


class OrderFilter(django_filters.FilterSet):
    created_after = django_filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_before = django_filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = Order
        fields = ['paid', 'created_after', 'created_before']
