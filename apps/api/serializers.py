from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import F
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.settings import api_settings

from apps.bookings.models import Booking, CartItem, Order, OrderItem
from apps.resources.models import Resource, ResourceCategory
from apps.users.forms import MAX_AVATAR_SIZE

User = get_user_model()


def active_resource_field():
    return serializers.PrimaryKeyRelatedField(
        queryset=Resource.objects.filter(is_active=True),
        source='resource',
        write_only=True,
    )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone', 'avatar']
        read_only_fields = ['id', 'username']

    def validate_avatar(self, avatar):
        if avatar and avatar.size > MAX_AVATAR_SIZE:
            raise serializers.ValidationError(_('File size must be less than 2 MB.'))
        return avatar


class ResourceCategorySerializer(serializers.ModelSerializer):
    resources_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ResourceCategory
        fields = ['id', 'name', 'slug', 'description', 'resources_count']


class ResourceCategoryShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceCategory
        fields = ['id', 'name', 'slug']


class ResourceSerializer(serializers.ModelSerializer):
    category = ResourceCategoryShortSerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ResourceCategory.objects.all(),
        source='category',
        write_only=True,
    )

    class Meta:
        model = Resource
        fields = [
            'id', 'category', 'category_id', 'name', 'slug', 'description',
            'price_per_hour', 'capacity', 'is_active', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ResourceShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resource
        fields = ['id', 'name', 'slug', 'price_per_hour']


class BookingSerializer(serializers.ModelSerializer):
    resource = ResourceShortSerializer(read_only=True)
    resource_id = active_resource_field()
    is_cancellable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'user', 'resource', 'resource_id', 'start_time', 'end_time',
            'status', 'is_cancellable', 'created_at',
        ]
        read_only_fields = ['id', 'user', 'status', 'created_at']

    def validate(self, attrs):
        if self.instance and not self.instance.is_cancellable:
            raise serializers.ValidationError(_('Only upcoming bookings can be changed.'))
        return attrs

    def save(self, **kwargs):
        try:
            return super().save(**kwargs)
        except DjangoValidationError as error:
            # Booking.save() runs full_clean(), so past dates and overlaps surface here.
            raise serializers.ValidationError({api_settings.NON_FIELD_ERRORS_KEY: error.messages})


class CartItemSerializer(serializers.ModelSerializer):
    resource = ResourceShortSerializer(read_only=True)
    resource_id = active_resource_field()
    total_price = serializers.DecimalField(max_digits=12, decimal_places=2, source='get_cost', read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'resource', 'resource_id', 'quantity', 'total_price', 'created_at']
        read_only_fields = ['id', 'created_at']

    def create(self, validated_data):
        """Adding a resource that is already in the cart increases its quantity."""
        quantity = validated_data.get('quantity', 1)
        item, created = CartItem.objects.get_or_create(
            user=validated_data['user'],
            resource=validated_data['resource'],
            defaults={'quantity': quantity},
        )
        if not created:
            CartItem.objects.filter(pk=item.pk).update(quantity=F('quantity') + quantity)
            item.refresh_from_db()
        return item

    def update(self, instance, validated_data):
        # A cart line always belongs to one resource; only its quantity can change.
        validated_data.pop('resource', None)
        return super().update(instance, validated_data)


class CartSummarySerializer(serializers.Serializer):
    items = CartItemSerializer(many=True)
    total_items = serializers.IntegerField()
    total_price = serializers.DecimalField(max_digits=12, decimal_places=2)


class OrderItemSerializer(serializers.ModelSerializer):
    resource = ResourceShortSerializer(read_only=True)
    total_price = serializers.DecimalField(max_digits=12, decimal_places=2, source='get_cost', read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'resource', 'price', 'quantity', 'total_price']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    total_cost = serializers.DecimalField(max_digits=12, decimal_places=2, source='get_total_cost', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'user', 'first_name', 'last_name', 'email', 'paid',
            'items', 'total_cost', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'user', 'paid', 'created_at', 'updated_at']

    def create(self, validated_data):
        """Turn the user's cart into an unpaid order, using current prices from the database."""
        with transaction.atomic():
            cart_items = list(
                CartItem.objects.select_for_update()
                .filter(user=validated_data['user'])
                .select_related('resource')
            )
            if not cart_items:
                raise serializers.ValidationError({api_settings.NON_FIELD_ERRORS_KEY: [_('Your cart is empty.')]})

            unavailable = [item.resource.name for item in cart_items if not item.resource.is_active]
            if unavailable:
                message = _('These resources are no longer available: %(names)s') % {'names': ', '.join(unavailable)}
                raise serializers.ValidationError({api_settings.NON_FIELD_ERRORS_KEY: [message]})

            order = Order.objects.create(**validated_data)
            OrderItem.objects.bulk_create(
                OrderItem(order=order, resource=item.resource, price=item.resource.price_per_hour, quantity=item.quantity)
                for item in cart_items
            )
            CartItem.objects.filter(pk__in=[item.pk for item in cart_items]).delete()
        return order
