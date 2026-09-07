from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from .models import Booking
from .forms import BookingForm
from apps.resources.models import Resource


class BookingListView(LoginRequiredMixin, ListView):
    model = Booking
    template_name = 'bookings/booking_list.html'
    context_object_name = 'bookings'

    def get_queryset(self):
        queryset = Booking.objects.filter(user=self.request.user)
        status = self.request.GET.get('status')
        resource = self.request.GET.get('resource')

        if status:
            queryset = queryset.filter(status=status)
        if resource:
            queryset = queryset.filter(resource_id=resource)

        return queryset


class BookingCreateView(LoginRequiredMixin, CreateView):
    model = Booking
    form_class = BookingForm
    template_name = 'bookings/booking_form.html'
    success_url = reverse_lazy('bookings:booking_list')

    def form_valid(self, form):
        resource = get_object_or_404(Resource, slug=self.kwargs['slug'])
        form.instance.user = self.request.user
        form.instance.resource = resource
        try:
            return super().form_valid(form)
        except ValidationError as e:
            form.add_error(None, e)
            return self.form_invalid(form)


class BookingCancelView(LoginRequiredMixin, UpdateView):
    model = Booking
    fields = []
    template_name = 'bookings/booking_confirm_cancel.html'
    success_url = reverse_lazy('bookings:booking_list')

    def form_valid(self, form):
        form.instance.status = 'cancelled'
        return super().form_valid(form)