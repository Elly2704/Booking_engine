from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from apps.bookings.models import Booking, Order, OrderItem
from apps.resources.models import Resource, ResourceCategory
from apps.users.models import User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f'user{n}')
    email = factory.LazyAttribute(lambda o: f'{o.username}@example.com')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    phone = factory.Faker('numerify', text='+380#########')
    password = factory.django.Password('StrongPass123!')


class ResourceCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ResourceCategory
        django_get_or_create = ('slug',)

    name = factory.Sequence(lambda n: f'Category {n}')
    slug = factory.Sequence(lambda n: f'category-{n}')
    description = factory.Faker('sentence')


class ResourceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Resource

    category = factory.SubFactory(ResourceCategoryFactory)
    name = factory.Sequence(lambda n: f'Meeting Room {n}')
    slug = factory.Sequence(lambda n: f'meeting-room-{n}')
    description = factory.Faker('paragraph')
    price_per_hour = Decimal('25.00')
    capacity = 4
    is_active = True


class BookingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Booking

    user = factory.SubFactory(UserFactory)
    resource = factory.SubFactory(ResourceFactory)
    start_time = factory.LazyFunction(lambda: timezone.now() + timedelta(days=1))
    end_time = factory.LazyAttribute(lambda o: o.start_time + timedelta(hours=2))
    status = 'pending'


class OrderFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    first_name = factory.LazyAttribute(lambda o: o.user.first_name if o.user else 'Guest')
    last_name = factory.LazyAttribute(lambda o: o.user.last_name if o.user else '')
    email = factory.LazyAttribute(lambda o: o.user.email if o.user else 'guest@example.com')
    paid = False
    stripe_id = factory.Sequence(lambda n: f'cs_test_{n}')


class OrderItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OrderItem

    order = factory.SubFactory(OrderFactory)
    resource = factory.SubFactory(ResourceFactory)
    price = factory.LazyAttribute(lambda o: o.resource.price_per_hour)
    quantity = 2
