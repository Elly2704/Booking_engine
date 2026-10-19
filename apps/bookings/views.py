import logging

import stripe
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.urls import reverse, reverse_lazy
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import ListView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from .models import Booking, Order, OrderItem
from .forms import BookingForm, CheckoutForm
from apps.resources.models import Resource
from .cart import Cart

stripe.api_key = settings.STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)


class BookingListView(LoginRequiredMixin, ListView):
    """Show the current user's bookings and orders.

    Supports optional ``?status=`` and ``?resource=`` query filters.
    Orders are prefetched with their items and resources to avoid N+1 queries.
    """
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
    """Create a booking for the resource identified by ``slug``.

    The user and resource are attached in ``form_valid``; model-level validation
    (past dates, overlaps) is surfaced as a non-field form error.
    """
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
    """Cancel one of the current user's upcoming bookings.

    GET renders a confirmation page, POST sets the status to ``cancelled``.
    Only the owner's future, not yet cancelled bookings are reachable; anything
    else returns 404, so other users' bookings cannot be cancelled by ``pk``.
    """
    model = Booking
    fields = []
    template_name = 'bookings/booking_confirm_cancel.html'
    success_url = reverse_lazy('bookings:booking_list')

    def get_queryset(self):
        return Booking.objects.filter(
            user=self.request.user,
            start_time__gt=timezone.now(),
        ).exclude(status='cancelled').select_related('resource')

    def form_valid(self, form):
        form.instance.status = 'cancelled'
        response = super().form_valid(form)
        messages.success(self.request, _('Booking for "%(name)s" has been cancelled.') % {
            'name': self.object.resource.name,
        })
        return response


def send_order_confirmation_email(order):
    """Send a payment confirmation email for ``order``.

    The text is translated into the active language. SMTP errors are logged and
    swallowed so a mail outage never breaks the payment flow.
    """
    subject = _('Order #%(id)s') % {'id': order.id}
    message = _(
        'Hello, %(name)s!\n\nYour payment for order #%(id)s was successful.\n'
        'Thank you for using our booking service!'
    ) % {'name': order.first_name, 'id': order.id}
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [order.email]

    try:
        send_mail(subject, message, from_email, recipient_list, fail_silently=False)
    except Exception as e:
        logger.error("Failed to send email: %s", e)


@require_POST
def cart_add(request, resource_id):
    """Add ``quantity`` hours of an active resource to the session cart (POST only).

    Invalid or missing quantity falls back to 1. Redirects to the cart page.
    """
    resource = get_object_or_404(Resource, id=resource_id, is_active=True)
    try:
        quantity = max(1, int(request.POST.get('quantity', 1)))
    except ValueError:
        quantity = 1
    Cart(request).add(resource, quantity=quantity)
    messages.success(request, _('"%(name)s" added to cart.') % {'name': resource.name})
    return redirect('bookings:cart_detail')


@require_POST
def cart_remove(request, resource_id):
    """Remove a resource from the session cart (POST only) and redirect to the cart."""
    resource = get_object_or_404(Resource, id=resource_id)
    Cart(request).remove(resource)
    return redirect('bookings:cart_detail')


def cart_detail(request):
    """Render the session cart with line totals and the overall price."""
    return render(request, 'bookings/cart_detail.html', {'cart': Cart(request)})


def order_create(request):
    """Checkout: validate contact data, create the order and redirect to Stripe.

    Prices are taken from the database at checkout time, not from the session,
    and checkout is refused if a cart item has been deactivated. The order, its
    items and the Stripe Checkout Session are created in one transaction, so a
    Stripe error leaves no orphan order. Responds with a 303 redirect to Stripe.
    """
    cart = Cart(request)
    if len(cart) == 0:
        messages.warning(request, _('Your cart is empty.'))
        return redirect('bookings:cart_detail')

    initial = {}
    if request.user.is_authenticated:
        initial = {
            'first_name': request.user.first_name or request.user.username,
            'last_name': request.user.last_name,
            'email': request.user.email,
        }
    form = CheckoutForm(request.POST or None, initial=initial)

    if request.method == 'POST' and form.is_valid():
        first_name = form.cleaned_data['first_name']
        last_name = form.cleaned_data['last_name']
        email = form.cleaned_data['email']

        inactive = [item['resource'].name for item in cart if not item['resource'].is_active]
        if inactive:
            messages.error(request, _('These resources are no longer available: %(names)s') % {
                'names': ', '.join(inactive),
            })
            return redirect('bookings:cart_detail')

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
                    price = resource.price_per_hour

                    OrderItem.objects.create(
                        order=order,
                        resource=resource,
                        price=price,
                        quantity=quantity
                    )

                    line_items.append({
                        'price_data': {
                            'currency': settings.STRIPE_CURRENCY,
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

            return HttpResponseRedirect(checkout_session.url, status=303)

        except stripe.error.StripeError as e:
            logger.error("Stripe error: %s", e)
            messages.error(request, _('Payment error: %(error)s') % {'error': e.user_message or e})
        except Exception:
            logger.exception("Order creation failed")
            messages.error(request, _('Could not create order. Please try again.'))

    return render(request, 'bookings/order_create.html', {'cart': cart, 'form': form})


def payment_success(request):
    """Handle the Stripe success redirect and mark the order as paid.

    The order is looked up by both ``order_id`` and ``session_id``. Payment status
    is verified with Stripe, then the order row is locked with
    ``select_for_update`` so concurrent requests cannot confirm it twice. The
    confirmation email is sent only after the transaction commits.
    """
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
            messages.error(request, _('Could not verify payment.'))
            return redirect('bookings:cart_detail')

        if session.payment_status != 'paid':
            messages.warning(request, _('Payment has not been completed yet.'))
            return render(request, 'bookings/cancel.html', {'order': order})

        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            if not order.paid:
                order.paid = True
                order.save(update_fields=['paid', 'updated_at'])
                transaction.on_commit(lambda: send_order_confirmation_email(order))
        Cart(request).clear()

    return render(request, 'bookings/success.html', {'order': order})


def payment_cancel(request):
    """Render the cancelled-payment page; the cart is kept so the user can retry."""
    order = None
    order_id = request.GET.get('order_id')
    if order_id:
        order = Order.objects.filter(id=order_id, paid=False).first()
    return render(request, 'bookings/cancel.html', {'order': order})


@require_GET
async def resource_availability(request, slug):
    """Async JSON API: check whether a resource is free for a time range.

    Query params ``start`` and ``end`` are ISO datetimes (naive values are treated
    as the current time zone). Returns ``{"available": bool, ...}``, 400 for bad
    input and 404 for an unknown or inactive resource.
    """
    resource = await Resource.objects.filter(slug=slug, is_active=True).afirst()
    if resource is None:
        return JsonResponse({'error': _('Resource not found.')}, status=404)

    start = parse_datetime(request.GET.get('start', ''))
    end = parse_datetime(request.GET.get('end', ''))
    if not start or not end:
        return JsonResponse({'error': _('Parameters "start" and "end" are required.')}, status=400)
    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    if timezone.is_naive(end):
        end = timezone.make_aware(end)
    if start >= end:
        return JsonResponse({'error': _('End time must be greater than start time.')}, status=400)

    is_booked = await Booking.objects.filter(
        resource=resource,
        status__in=['pending', 'confirmed'],
        start_time__lt=end,
        end_time__gt=start,
    ).aexists()

    return JsonResponse({
        'resource': resource.slug,
        'start': start.isoformat(),
        'end': end.isoformat(),
        'available': not is_booked,
    })


@login_required
@require_GET
async def booking_stats(request):
    """Async JSON API: booking counters per status, paid orders and the next 5 bookings.

    Requires authentication; all queries use the async ORM.
    """
    user = await request.auser()
    stats = await Booking.objects.filter(user=user).aaggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='pending')),
        confirmed=Count('id', filter=Q(status='confirmed')),
        cancelled=Count('id', filter=Q(status='cancelled')),
    )
    paid_orders = await Order.objects.filter(user=user, paid=True).acount()
    upcoming = [
        {
            'id': booking.id,
            'resource': booking.resource.name,
            'start_time': booking.start_time.isoformat(),
            'end_time': booking.end_time.isoformat(),
            'status': booking.status,
        }
        async for booking in Booking.objects.filter(
            user=user,
            start_time__gte=timezone.now(),
        ).exclude(status='cancelled').select_related('resource').order_by('start_time')[:5]
    ]
    return JsonResponse({**stats, 'paid_orders': paid_orders, 'upcoming': upcoming})


@login_required
async def order_detail(request, pk):
    """Async view: show one of the current user's orders with its items and total.

    Returns 404 for orders that belong to someone else.
    """
    user = await request.auser()
    order = await Order.objects.filter(pk=pk, user=user).afirst()
    if order is None:
        raise Http404(_('Order not found.'))
    items = [item async for item in order.items.select_related('resource')]
    total = sum((item.get_cost() for item in items), 0)
    return await sync_to_async(render)(request, 'bookings/order_detail.html', {
        'order': order,
        'items': items,
        'total': total,
    })
