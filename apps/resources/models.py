from django.db import models
from django.utils.translation import gettext_lazy as _


class ResourceCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name=_("Category Name"))
    slug = models.SlugField(max_length=100, unique=True, verbose_name=_("URL Slug"))
    description = models.TextField(blank=True, verbose_name=_("Description"))

    class Meta:
        verbose_name = _("Resource Category")
        verbose_name_plural = _("Resource Categories")
        ordering = ['name']

    def __str__(self):
        return self.name


class Resource(models.Model):
    category = models.ForeignKey(
        ResourceCategory,
        on_delete=models.CASCADE,
        related_name='resources',
        verbose_name=_("Category")
    )
    name = models.CharField(max_length=150, verbose_name=_("Resource Name"))
    slug = models.SlugField(max_length=150, unique=True, verbose_name=_("URL Slug"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    price_per_hour = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("Price Per Hour")
    )
    capacity = models.PositiveIntegerField(default=1, verbose_name=_("Capacity (persons)"))
    is_active = models.BooleanField(default=True, verbose_name=_("Is Active"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))

    class Meta:
        verbose_name = _("Resource")
        verbose_name_plural = _("Resources")
        ordering = ['-created_at']

    def __str__(self):
        return self.name
