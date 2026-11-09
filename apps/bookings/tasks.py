import csv
import logging
from datetime import date, datetime, time, timedelta
from smtplib import SMTPException

from celery import shared_task
from django.conf import settings
from django.core.management import call_command
from django.db.models import DecimalField, F, Sum
from django.utils import timezone, translation

from .emails import send_order_confirmation_email
from .models import Booking, Order, OrderItem

logger = logging.getLogger(__name__)


@shared_task(autoretry_for=(SMTPException, OSError), retry_backoff=True, max_retries=3)
def send_order_confirmation(order_id, language=settings.LANGUAGE_CODE):
    order = Order.objects.get(pk=order_id)
    with translation.override(language):
        send_order_confirmation_email(order)


@shared_task
def generate_daily_report(day=None):
    """Write bookings and paid orders of a day (yesterday by default) to a CSV file and return its path."""
    report_day = date.fromisoformat(day) if day else timezone.localdate() - timedelta(days=1)
    start = timezone.make_aware(datetime.combine(report_day, time.min))
    period = {'created_at__gte': start, 'created_at__lt': start + timedelta(days=1)}

    bookings = Booking.objects.filter(**period)
    paid_orders = Order.objects.filter(paid=True, **period)
    revenue = OrderItem.objects.filter(order__in=paid_orders).aggregate(
        total=Sum(F('price') * F('quantity'), output_field=DecimalField(max_digits=14, decimal_places=2)),
    )['total'] or 0

    rows = [
        ('date', report_day.isoformat()),
        ('bookings_total', bookings.count()),
        ('bookings_cancelled', bookings.filter(status=Booking.Status.CANCELLED).count()),
        ('paid_orders', paid_orders.count()),
        ('revenue', revenue),
    ]

    settings.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = settings.REPORTS_DIR / f'report_{report_day.isoformat()}.csv'
    with path.open('w', newline='', encoding='utf-8') as report:
        csv.writer(report).writerows([('metric', 'value'), *rows])

    logger.info('Daily report written to %s', path)
    return str(path)


@shared_task
def clear_expired_sessions():
    call_command('clearsessions')
