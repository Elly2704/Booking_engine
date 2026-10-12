from django.contrib import admin
from .models import Booking, Order, OrderItem


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'resource', 'start_time', 'end_time', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'resource__name')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    raw_id_fields = ['resource']
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'first_name', 'last_name', 'email', 'paid', 'created_at')
    list_filter = ('paid', 'created_at')
    search_fields = ('first_name', 'last_name', 'email')
    inlines = [OrderItemInline]