from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from apps.resources.models import Resource


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('confirmed', _('Confirmed')),
        ('cancelled', _('Cancelled')),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_('User')
    )
    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_('Resource')
    )
    start_time = models.DateTimeField(_('Start Time'))
    end_time = models.DateTimeField(_('End Time'))
    status = models.CharField(_('Status'), max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        db_table = 'bookings_booking'
        ordering = ['-created_at']
        verbose_name = _('Booking')
        verbose_name_plural = _('Bookings')

    def __str__(self):
        return f"{self.user.username} - {self.resource.name} ({self.status})"

    def clean(self):
        super().clean()

        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError(_("End time must be greater than start time."))

        if self.start_time and self.start_time < timezone.now():
            raise ValidationError(_("Cannot book resources in the past."))

        if self.resource_id and self.start_time and self.end_time:
            overlapping_bookings = Booking.objects.filter(
                resource=self.resource,
                status__in=['pending', 'confirmed']
            ).exclude(pk=self.pk).filter(
                start_time__lt=self.end_time,
                end_time__gt=self.start_time
            )

            if overlapping_bookings.exists():
                raise ValidationError(_("This resource is already booked for the selected time period."))

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_cancellable(self):
        return self.status != 'cancelled' and self.start_time > timezone.now()


class Order(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='orders',
        null=True, blank=True,
        verbose_name=_('User')
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
        related_name='items',
        on_delete=models.CASCADE,
        verbose_name=_('Order')
    )
    # Привязываем позицию заказа к конкретному ресурсу или бронированию (по вашей структуре)
    resource = models.ForeignKey(
        Resource,
        related_name='order_items',
        on_delete=models.CASCADE,
        null=True, blank=True,
        verbose_name=_('Resource')
    )
    price = models.DecimalField(_('Price'), max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(_('Quantity'), default=1)

    class Meta:
        verbose_name = _('Order Item')
        verbose_name_plural = _('Order Items')

    def __str__(self):
        return str(self.id)

    def get_cost(self):
        return self.price * self.quantity