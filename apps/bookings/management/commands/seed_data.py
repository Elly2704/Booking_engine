import random
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from faker import Faker

from apps.bookings.models import Booking, Order, OrderItem
from apps.resources.models import Resource, ResourceCategory
from apps.users.models import User

DEMO_PASSWORD = 'StrongPass123!'
CATEGORIES = ['Meeting Rooms', 'Coworking', 'Studios', 'Event Halls', 'Sports Courts']
RESOURCE_KINDS = ['Room', 'Desk', 'Studio', 'Hall', 'Court', 'Booth', 'Loft']


def unique_suffix():
    return uuid.uuid4().hex[:6]


class Command(BaseCommand):
    help = 'Fill the database with demo users, resources, bookings and orders.'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=5, help='How many objects of each model to create.')

    @transaction.atomic
    def handle(self, *args, count, **options):
        self.fake = Faker(['uk_UA', 'en_US'])

        users = [self.create_user() for _ in range(count)]
        categories = [self.create_category(i) for i in range(count)]
        resources = [self.create_resource(category) for category in categories]
        bookings = [self.create_booking(user, resource, i) for i, (user, resource) in enumerate(zip(users, resources))]
        orders = [self.create_order(user, random.choice(resources)) for user in users]

        for model, objects in [
            (User, users), (ResourceCategory, categories), (Resource, resources),
            (Booking, bookings), (Order, orders), (OrderItem, orders),
        ]:
            self.stdout.write(f'{model.__name__}: +{len(objects)}')

        usernames = ', '.join(user.username for user in users)
        self.stdout.write(self.style.SUCCESS(f'Done. Users: {usernames} (password: {DEMO_PASSWORD})'))

    def create_user(self):
        first_name, last_name = self.fake['uk_UA'].first_name(), self.fake['uk_UA'].last_name()
        username = f'{slugify(self.fake["en_US"].user_name())}_{unique_suffix()}'
        return User.objects.create_user(
            username=username,
            email=f'{username}@example.com',
            password=DEMO_PASSWORD,
            first_name=first_name,
            last_name=last_name,
            phone=self.fake.numerify('+38067#######'),
        )

    def create_category(self, index):
        name = CATEGORIES[index % len(CATEGORIES)]
        return ResourceCategory.objects.create(
            name=name,
            slug=f'{slugify(name)}-{unique_suffix()}',
            description=self.fake['en_US'].sentence(nb_words=8),
        )

    def create_resource(self, category):
        name = f'{self.fake["en_US"].city()} {random.choice(RESOURCE_KINDS)}'
        return Resource.objects.create(
            category=category,
            name=name,
            slug=f'{slugify(name)}-{unique_suffix()}',
            description=self.fake['en_US'].paragraph(nb_sentences=3),
            price_per_hour=Decimal(random.randrange(10, 150)),
            capacity=random.randint(1, 30),
        )

    def create_booking(self, user, resource, index):
        day = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=index + 1)
        start = day + timedelta(hours=random.randint(9, 17))
        return Booking.objects.create(
            user=user,
            resource=resource,
            start_time=start,
            end_time=start + timedelta(hours=random.randint(1, 3)),
            status=random.choice(Booking.ACTIVE_STATUSES),
        )

    def create_order(self, user, resource):
        order = Order.objects.create(
            user=user,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            paid=random.choice([True, False]),
            stripe_id=f'cs_test_{unique_suffix()}',
        )
        OrderItem.objects.create(
            order=order,
            resource=resource,
            price=resource.price_per_hour,
            quantity=random.randint(1, 5),
        )
        return order
