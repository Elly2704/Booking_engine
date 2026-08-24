from django.db import models


class ResourceCategory(models.Model):
    name = models.CharField(max_length=100, verbose_name="Category Name")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="URL Slug")
    description = models.TextField(blank=True, verbose_name="Description")

    class Meta:
        verbose_name = "Resource Category"
        verbose_name_plural = "Resource Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


class Resource(models.Model):
    category = models.ForeignKey(
        ResourceCategory,
        on_delete=models.CASCADE,
        related_name='resources',
        verbose_name="Category"
    )
    name = models.CharField(max_length=150, verbose_name="Resource Name")
    slug = models.SlugField(max_length=150, unique=True, verbose_name="URL Slug")
    description = models.TextField(blank=True, verbose_name="Description")
    price_per_hour = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name="Price Per Hour"
    )
    capacity = models.PositiveIntegerField(default=1, verbose_name="Capacity (persons)")
    is_active = models.BooleanField(default=True, verbose_name="Is Active")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    class Meta:
        verbose_name = "Resource"
        verbose_name_plural = "Resources"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.capacity} capacity)"
