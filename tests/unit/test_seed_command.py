from io import StringIO

import pytest
from django.core.management import call_command

from apps.bookings.models import Booking, Order, OrderItem
from apps.resources.models import Resource, ResourceCategory
from apps.users.models import User

pytestmark = pytest.mark.django_db


def test_seed_data_creates_entities_for_every_model():
    out = StringIO()
    call_command('seed_data', stdout=out)
    for model in (User, ResourceCategory, Resource, Booking, Order, OrderItem):
        assert model.objects.count() == 5
    assert 'Done.' in out.getvalue()


def test_seed_data_can_run_twice():
    call_command('seed_data', count=3, stdout=StringIO())
    call_command('seed_data', count=3, stdout=StringIO())
    assert Resource.objects.count() == 6
    assert User.objects.first().check_password('StrongPass123!')
