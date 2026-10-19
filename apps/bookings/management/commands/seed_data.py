import random
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from faker import Faker

from tests.factories import (
    BookingFactory,
    OrderFactory,
    OrderItemFactory,
    ResourceCategoryFactory,
    ResourceFactory,
    UserFactory,
)

CATEGORY_NAMES = ['Meeting Rooms', 'Coworking', 'Studios', 'Event Halls', 'Sports', 'Equipment', 'Cabins']
RESOURCE_KINDS = ['Room', 'Desk', 'Studio', 'Hall', 'Court', 'Booth', 'Loft']
DEFAULT_PASSWORD = 'StrongPass123!'


class Command(BaseCommand):
    help = 'Fill the database with random users, resources, bookings and orders.'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=5)

    @transaction.atomic
    def handle(self, *args, count, **options):
        fake = Faker('uk_UA')
        suffix = lambda: uuid.uuid4().hex[:6]

        users = [
            UserFactory(
                username=f'{slugify(fake.user_name()) or "user"}_{suffix()}',
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                phone=fake.numerify('+38067#######'),
            )
            for _ in range(count)
        ]

        categories = []
        for name in random.sample(CATEGORY_NAMES, k=min(count, len(CATEGORY_NAMES))) + [None] * max(0, count - len(CATEGORY_NAMES)):
            name = name or fake.word().capitalize()
            categories.append(ResourceCategoryFactory(
                name=name,
                slug=f'{slugify(name)}-{suffix()}',
                description=fake.sentence(nb_words=8),
            ))

        resources = []
        for category in categories:
            name = f'{fake.city()} {random.choice(RESOURCE_KINDS)}'
            resources.append(ResourceFactory(
                category=category,
                name=name,
                slug=f'{slugify(name, allow_unicode=False) or "resource"}-{suffix()}',
                description=fake.paragraph(nb_sentences=3),
                price_per_hour=Decimal(random.randrange(10, 150)) + Decimal('0.00'),
                capacity=random.randint(1, 30),
            ))

        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        bookings = []
        for i, (user, resource) in enumerate(zip(users, resources)):
            start = now + timedelta(days=random.randint(1, 30), hours=random.randint(8, 18) + i * 100)
            bookings.append(BookingFactory(
                user=user,
                resource=resource,
                start_time=start,
                end_time=start + timedelta(hours=random.randint(1, 4)),
                status=random.choice(['pending', 'confirmed', 'cancelled']),
            ))

        orders, items = [], []
        for user in users:
            order = OrderFactory(user=user, paid=random.choice([True, False]), stripe_id=f'cs_test_{suffix()}')
            resource = random.choice(resources)
            items.append(OrderItemFactory(
                order=order,
                resource=resource,
                price=resource.price_per_hour,
                quantity=random.randint(1, 5),
            ))
            orders.append(order)

        summary = {
            'User': len(users), 'ResourceCategory': len(categories), 'Resource': len(resources),
            'Booking': len(bookings), 'Order': len(orders), 'OrderItem': len(items),
        }
        for model, created in summary.items():
            self.stdout.write(f'{model}: +{created}')
        self.stdout.write(self.style.SUCCESS(
            f'Done. Users: {", ".join(u.username for u in users)} (password: {DEFAULT_PASSWORD})'
        ))
