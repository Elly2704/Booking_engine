from django.urls import path
from . import views

app_name = 'bookings'

urlpatterns = [
    path('', views.BookingListView.as_view(), name='booking_list'),
    path('create/<slug:slug>/', views.BookingCreateView.as_view(), name='booking_create'),
    path('<int:pk>/cancel/', views.BookingCancelView.as_view(), name='booking_cancel'),
]