from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.resources.models import Resource


class BookingQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status__in=Booking.ACTIVE_STATUSES)

    def overlapping(self, start, end):
        return self.active().filter(start_time__lt=end, end_time__gt=start)


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        CONFIRMED = 'confirmed', _('Confirmed')
        CANCELLED = 'cancelled', _('Cancelled')

    ACTIVE_STATUSES = [Status.PENDING, Status.CONFIRMED]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_('User'),
    )
    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_('Resource'),
    )
    start_time = models.DateTimeField(_('Start Time'))
    end_time = models.DateTimeField(_('End Time'))
    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    objects = BookingQuerySet.as_manager()

    class Meta:
        db_table = 'bookings_booking'
        ordering = ['-created_at']
        verbose_name = _('Booking')
        verbose_name_plural = _('Bookings')

    def __str__(self):
        return f'{self.user.username} - {self.resource.name} ({self.status})'

    def clean(self):
        super().clean()

        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError(_('End time must be greater than start time.'))

        if self.start_time and self.start_time < timezone.now():
            raise ValidationError(_('Cannot book resources in the past.'))

        if self.resource_id and self.start_time and self.end_time:
            conflicts = (
                Booking.objects.filter(resource_id=self.resource_id)
                .overlapping(self.start_time, self.end_time)
                .exclude(pk=self.pk)
            )
            if conflicts.exists():
                raise ValidationError(_('This resource is already booked for the selected time period.'))

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_cancellable(self):
        return self.status != self.Status.CANCELLED and self.start_time > timezone.now()


class Order(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders',
        null=True,
        blank=True,
        verbose_name=_('User'),
    )
    first_name = models.CharField(_('First Name'), max_length=50)
    last_name = models.CharField(_('Last Name'), max_length=50)
    email = models.EmailField(_('Email'))
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)
    paid = models.BooleanField(_('Paid'), default=False)
    stripe_id = models.CharField(_('Stripe ID'), max_length=250, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Order')
        verbose_name_plural = _('Orders')

    def __str__(self):
        return _('Order %(id)s') % {'id': self.id}

    def get_total_cost(self):
        return sum(item.get_cost() for item in self.items.all())


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_('Order'),
    )
    resource = models.ForeignKey(
        Resource,
        on_delete=models.SET_NULL,
        related_name='order_items',
        null=True,
        blank=True,
        verbose_name=_('Resource'),
    )
    price = models.DecimalField(_('Price'), max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(_('Quantity'), default=1)

    class Meta:
        verbose_name = _('Order Item')
        verbose_name_plural = _('Order Items')

    def __str__(self):
        return f'{self.quantity} × {self.resource or "—"}'

    def get_cost(self):
        return self.price * self.quantity
