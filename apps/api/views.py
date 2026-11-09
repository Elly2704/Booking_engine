from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.decorators.vary import vary_on_headers
from drf_spectacular.utils import extend_schema
from rest_framework import serializers as drf_serializers
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from apps.bookings.models import Booking, CartItem, Order
from apps.resources.cache import cache_catalog_page
from apps.resources.models import Resource, ResourceCategory

from . import serializers
from .filters import BookingFilter, OrderFilter, ResourceFilter
from .permissions import IsOwnerOrReadOnly

User = get_user_model()


class PublicReadAdminWriteMixin:
    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return [IsAdminUser()]

    # Staff see inactive resources and browsers get HTML, so the cache must vary on both headers.
    @method_decorator(cache_catalog_page)
    @method_decorator(vary_on_headers('Authorization', 'Accept'))
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class OwnedQuerysetMixin:
    """Regular users work with their own objects only; staff can see everyone's."""

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self, 'swagger_fake_view', False):
            return queryset.none()
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)


class AdminDestroyMixin:
    def get_permissions(self):
        if self.action == 'destroy':
            return [IsAdminUser()]
        return super().get_permissions()


class ResourceCategoryViewSet(PublicReadAdminWriteMixin, viewsets.ModelViewSet):
    queryset = ResourceCategory.objects.annotate(
        resources_count=Count('resources', filter=Q(resources__is_active=True)),
    ).order_by('name')
    serializer_class = serializers.ResourceCategorySerializer
    filterset_fields = ['slug']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'resources_count']


class ResourceViewSet(PublicReadAdminWriteMixin, viewsets.ModelViewSet):
    queryset = Resource.objects.select_related('category')
    serializer_class = serializers.ResourceSerializer
    filterset_class = ResourceFilter
    search_fields = ['name', 'description', 'category__name']
    ordering_fields = ['name', 'price_per_hour', 'capacity', 'created_at']

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(is_active=True)


class BookingViewSet(AdminDestroyMixin, OwnedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Booking.objects.select_related('resource')
    serializer_class = serializers.BookingSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    filterset_class = BookingFilter
    search_fields = ['resource__name']
    ordering_fields = ['start_time', 'end_time', 'created_at']

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @extend_schema(request=None, responses=serializers.BookingSerializer)
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        if not booking.is_cancellable:
            raise drf_serializers.ValidationError({'detail': _('This booking cannot be cancelled.')})
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=['status'])
        return Response(self.get_serializer(booking).data)


class CartItemViewSet(viewsets.ModelViewSet):
    """The cart of the current user: every user, including staff, sees only their own."""

    queryset = CartItem.objects.select_related('resource')
    serializer_class = serializers.CartItemSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']
    ordering_fields = ['created_at', 'quantity']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return super().get_queryset().none()
        return super().get_queryset().filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @extend_schema(responses=serializers.CartSummarySerializer)
    @action(detail=False, methods=['get'])
    def summary(self, request):
        items = list(self.get_queryset())
        data = {
            'items': items,
            'total_items': sum(item.quantity for item in items),
            'total_price': sum(item.get_cost() for item in items),
        }
        return Response(serializers.CartSummarySerializer(data, context=self.get_serializer_context()).data)

    @extend_schema(request=None, responses={status.HTTP_204_NO_CONTENT: None})
    @action(detail=False, methods=['delete'])
    def clear(self, request):
        self.get_queryset().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrderViewSet(AdminDestroyMixin, OwnedQuerysetMixin, viewsets.ModelViewSet):
    """POST creates an unpaid order from the current user's cart and empties the cart."""

    queryset = Order.objects.prefetch_related('items__resource')
    serializer_class = serializers.OrderSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    filterset_class = OrderFilter
    search_fields = ['first_name', 'last_name', 'email']
    ordering_fields = ['created_at', 'updated_at']

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = serializers.UserSerializer
    queryset = User.objects.order_by('id')
    search_fields = ['username', 'email']
    ordering_fields = ['username', 'date_joined']

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return super().get_queryset().none()
        if self.request.user.is_staff:
            return super().get_queryset()
        return super().get_queryset().filter(pk=self.request.user.pk)

    @action(detail=False, methods=['get', 'patch'])
    def me(self, request):
        if request.method == 'GET':
            return Response(self.get_serializer(request.user).data)

        serializer = self.get_serializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
