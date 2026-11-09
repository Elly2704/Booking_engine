import csv
from datetime import timedelta
from decimal import Decimal
from smtplib import SMTPException
from unittest import mock

import pytest
from django.conf import settings as django_settings
from django.contrib.sessions.models import Session
from django.urls import reverse
from django.utils import timezone
from kombu.exceptions import OperationalError

from apps.bookings.models import Booking
from apps.bookings.tasks import clear_expired_sessions, generate_daily_report, send_order_confirmation
from config.celery import app
from tests.factories import BookingFactory, OrderFactory, OrderItemFactory

pytestmark = pytest.mark.django_db


def read_report(path):
    with open(path, newline='', encoding='utf-8') as report:
        return dict(csv.reader(report))


def test_confirmation_is_sent(order, mailoutbox):
    send_order_confirmation.delay(order.id)
    assert mailoutbox[0].to == [order.email]


def test_confirmation_uses_the_language_of_the_customer(order, mailoutbox):
    send_order_confirmation.delay(order.id, 'uk')
    assert mailoutbox[0].subject == f'Замовлення #{order.id}'


def test_confirmation_is_retried_on_smtp_failure(order):
    with mock.patch('apps.bookings.emails.send_mail', side_effect=SMTPException('down')) as send:
        result = send_order_confirmation.apply(args=[order.id])
    assert result.failed()
    assert send.call_count == send_order_confirmation.max_retries + 1


def test_daily_report_counts_only_requested_day(user, resource, settings):
    today = timezone.localdate().isoformat()
    BookingFactory(user=user, resource=resource)
    paid = OrderFactory(user=user, paid=True)
    OrderItemFactory(order=paid, resource=resource, price=Decimal('10.00'), quantity=3)
    OrderItemFactory(order=OrderFactory(user=user, paid=False), resource=resource)

    path = generate_daily_report(today)

    assert path.startswith(str(settings.REPORTS_DIR))
    report = read_report(path)
    assert report['date'] == today
    assert report['bookings_total'] == '1'
    assert report['paid_orders'] == '1'
    assert Decimal(report['revenue']) == Decimal('30.00')


def test_daily_report_defaults_to_yesterday(db):
    yesterday = timezone.localdate() - timedelta(days=1)
    assert read_report(generate_daily_report())['date'] == yesterday.isoformat()


def test_daily_report_counts_cancelled_bookings(user, resource):
    BookingFactory(user=user, resource=resource, status=Booking.Status.CANCELLED)
    report = read_report(generate_daily_report(timezone.localdate().isoformat()))
    assert report['bookings_cancelled'] == '1'


def test_clear_expired_sessions_keeps_active_ones(db):
    now = timezone.now()
    Session.objects.create(session_key='expired', session_data='x', expire_date=now - timedelta(days=1))
    Session.objects.create(session_key='active', session_data='x', expire_date=now + timedelta(days=1))

    clear_expired_sessions()

    assert list(Session.objects.values_list('session_key', flat=True)) == ['active']


def test_periodic_tasks_are_registered():
    app.loader.import_default_modules()
    for entry in django_settings.CELERY_BEAT_SCHEDULE.values():
        assert entry['task'] in app.tasks


def test_broker_failure_does_not_break_payment_page(
    client, order_with_items, stripe_session_retrieve, django_capture_on_commit_callbacks,
):
    order_with_items.stripe_id = 'cs_test_broker'
    order_with_items.save()

    with mock.patch('apps.bookings.tasks.send_order_confirmation.delay', side_effect=OperationalError('no broker')):
        with django_capture_on_commit_callbacks(execute=True):
            response = client.get(
                reverse('bookings:payment_success'),
                {'order_id': order_with_items.id, 'session_id': 'cs_test_broker'},
            )

    assert response.status_code == 200
    order_with_items.refresh_from_db()
    assert order_with_items.paid is True
