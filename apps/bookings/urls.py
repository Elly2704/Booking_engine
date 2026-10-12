from django.urls import path
from . import views

app_name = 'bookings'

urlpatterns = [
    path('', views.BookingListView.as_view(), name='booking_list'),
    path('create/<slug:slug>/', views.BookingCreateView.as_view(), name='booking_create'),
    path('<int:pk>/cancel/', views.BookingCancelView.as_view(), name='booking_cancel'),
    path('cart/', views.cart_detail, name='cart_detail'),
    path('cart/add/<int:resource_id>/', views.cart_add, name='cart_add'),
    path('cart/remove/<int:resource_id>/', views.cart_remove, name='cart_remove'),
    path('order/create/', views.order_create, name='order_create'),
    path('payment/success/', views.payment_success, name='payment_success'),
    path('payment/cancel/', views.payment_cancel, name='payment_cancel'),
]