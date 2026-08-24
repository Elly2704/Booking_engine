from django.contrib import admin
from .models import ResourceCategory, Resource


class ResourceInline(admin.TabularInline):
    model = Resource
    extra = 1
    prepopulated_fields = {'slug': ('name',)}


@admin.register(ResourceCategory)
class ResourceCategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'slug')
    list_display_links = ('id', 'name')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ResourceInline]


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'category',
        'price_per_hour',
        'capacity',
        'is_active',
        'created_at'
    )

    list_display_links = ('id', 'name')
    list_filter = ('category', 'is_active', 'created_at')
    search_fields = ('name', 'description')
    list_editable = ('price_per_hour', 'is_active')
    prepopulated_fields = {'slug': ('name',)}
