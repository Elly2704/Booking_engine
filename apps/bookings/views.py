import logging

import stripe
from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from .models import Booking, Order, OrderItem
from .forms import BookingForm
from apps.resources.models import Resource
from .cart import Cart

stripe.api_key = settings.STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['orders'] = Order.objects.filter(user=self.request.user).prefetch_related('items__resource')
        return context


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


def send_order_confirmation_email(order):
    subject = f'Order #{order.id}'
    message = f'Hello, {order.first_name}!\n\nYour payment for order #{order.id} was successful.\nThank you for using our booking service!'
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [order.email]

    try:
        send_mail(subject, message, from_email, recipient_list, fail_silently=False)
    except Exception as e:
        logger.error("Failed to send email: %s", e)


@require_POST
def cart_add(request, resource_id):
    resource = get_object_or_404(Resource, id=resource_id, is_active=True)
    try:
        quantity = max(1, int(request.POST.get('quantity', 1)))
    except ValueError:
        quantity = 1
    Cart(request).add(resource, quantity=quantity)
    messages.success(request, f'"{resource.name}" added to cart.')
    return redirect('bookings:cart_detail')


@require_POST
def cart_remove(request, resource_id):
    resource = get_object_or_404(Resource, id=resource_id)
    Cart(request).remove(resource)
    return redirect('bookings:cart_detail')


def cart_detail(request):
    return render(request, 'bookings/cart_detail.html', {'cart': Cart(request)})


def order_create(request):
    cart = Cart(request)
    if len(cart) == 0:
        messages.warning(request, 'Your cart is empty.')
        return redirect('bookings:cart_detail')

    if request.method == 'POST':
        first_name = request.POST.get('first_name') or (request.user.username if request.user.is_authenticated else 'Guest')
        last_name = request.POST.get('last_name', '')
        email = request.POST.get('email') or (request.user.email if request.user.is_authenticated else '')

        try:
            with transaction.atomic():
                order = Order.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    first_name=first_name,
                    last_name=last_name,
                    email=email
                )

                line_items = []
                for item in cart:
                    resource = item['resource']
                    quantity = item['quantity']
                    price = item['price']

                    OrderItem.objects.create(
                        order=order,
                        resource=resource,
                        price=price,
                        quantity=quantity
                    )

                    line_items.append({
                        'price_data': {
                            'currency': 'usd',
                            'unit_amount': int(price * 100),
                            'product_data': {
                                'name': resource.name,
                            },
                        },
                        'quantity': quantity,
                    })

                success_url = request.build_absolute_uri(reverse('bookings:payment_success'))
                cancel_url = request.build_absolute_uri(reverse('bookings:payment_cancel'))
                checkout_session = stripe.checkout.Session.create(
                    line_items=line_items,
                    mode='payment',
                    # Minimal payment form: no billing address, name, or phone collection
                    billing_address_collection='auto',
                    name_collection={'individual': {'enabled': False}},
                    phone_number_collection={'enabled': False},
                    customer_email=email or None,
                    client_reference_id=str(order.id),
                    success_url=success_url + f'?session_id={{CHECKOUT_SESSION_ID}}&order_id={order.id}',
                    cancel_url=cancel_url + f'?order_id={order.id}',
                )

                order.stripe_id = checkout_session.id
                order.save()

            return redirect(checkout_session.url, code=303)

        except stripe.error.StripeError as e:
            logger.error("Stripe error: %s", e)
            messages.error(request, f'Payment error: {e.user_message or e}')
        except Exception as e:
            logger.exception("Order creation failed")
            messages.error(request, 'Could not create order. Please try again.')

    return render(request, 'bookings/order_create.html', {'cart': cart})


def payment_success(request):
    order_id = request.GET.get('order_id')
    session_id = request.GET.get('session_id')
    if not (order_id and session_id):
        return redirect('bookings:cart_detail')

    order = get_object_or_404(Order, id=order_id, stripe_id=session_id)

    if not order.paid:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except stripe.error.StripeError as e:
            logger.error("Stripe error: %s", e)
            messages.error(request, 'Could not verify payment.')
            return redirect('bookings:cart_detail')

        if session.payment_status != 'paid':
            messages.warning(request, 'Payment has not been completed yet.')
            return render(request, 'bookings/cancel.html', {'order': order})

        order.paid = True
        order.save()
        Cart(request).clear()
        send_order_confirmation_email(order)

    return render(request, 'bookings/success.html', {'order': order})


def payment_cancel(request):
    order = None
    order_id = request.GET.get('order_id')
    if order_id:
        order = Order.objects.filter(id=order_id, paid=False).first()
    return render(request, 'bookings/cancel.html', {'order': order})
