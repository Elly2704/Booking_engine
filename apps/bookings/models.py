from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.resources.models import Resource


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    resource = models.ForeignKey(
        Resource,
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bookings_booking'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.resource.name} ({self.status})"

    def clean(self):
        super().clean()

        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError("End time must be greater than start time.")

        if self.start_time and self.start_time < timezone.now():
            raise ValidationError("Cannot book resources in the past.")

        if self.resource_id and self.start_time and self.end_time:
            overlapping_bookings = Booking.objects.filter(
                resource=self.resource,
                status__in=['pending', 'confirmed']
            ).exclude(pk=self.pk).filter(
                start_time__lt=self.end_time,
                end_time__gt=self.start_time
            )

            if overlapping_bookings.exists():
                raise ValidationError("This resource is already booked for the selected time period.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)