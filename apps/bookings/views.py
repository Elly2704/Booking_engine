import logging

import stripe
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, ListView, UpdateView

from apps.resources.models import Resource

from .cart import Cart
from .emails import send_order_confirmation_email
from .forms import BookingForm, CheckoutForm
from .models import Booking, Order, OrderItem

stripe.api_key = settings.STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)

Status = Booking.Status


class BookingListView(LoginRequiredMixin, ListView):
    template_name = 'bookings/booking_list.html'
    context_object_name = 'bookings'

    def get_queryset(self):
        queryset = Booking.objects.filter(user=self.request.user).select_related('resource')

        status = self.request.GET.get('status')
        if status in Status.values:
            queryset = queryset.filter(status=status)

        resource = self.request.GET.get('resource')
        if resource and resource.isdigit():
            queryset = queryset.filter(resource_id=resource)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['orders'] = Order.objects.filter(user=self.request.user).prefetch_related('items__resource')
        return context


class BookingCreateView(LoginRequiredMixin, CreateView):
    form_class = BookingForm
    template_name = 'bookings/booking_form.html'
    success_url = reverse_lazy('bookings:booking_list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.resource = get_object_or_404(Resource, slug=self.kwargs['slug'], is_active=True)
        try:
            return super().form_valid(form)
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)


class BookingCancelView(LoginRequiredMixin, UpdateView):
    """Only the owner's upcoming, not yet cancelled bookings can be cancelled; anything else is a 404."""

    fields = []
    template_name = 'bookings/booking_confirm_cancel.html'
    success_url = reverse_lazy('bookings:booking_list')

    def get_queryset(self):
        return (
            Booking.objects.filter(user=self.request.user, start_time__gt=timezone.now())
            .exclude(status=Status.CANCELLED)
            .select_related('resource')
        )

    def form_valid(self, form):
        form.instance.status = Status.CANCELLED
        response = super().form_valid(form)
        messages.success(
            self.request,
            _('Booking for "%(name)s" has been cancelled.') % {'name': self.object.resource.name},
        )
        return response


@require_POST
def cart_add(request, resource_id):
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
    resource = get_object_or_404(Resource, id=resource_id)
    Cart(request).remove(resource)
    return redirect('bookings:cart_detail')


def cart_detail(request):
    return render(request, 'bookings/cart_detail.html', {'cart': Cart(request)})


def _checkout_initial(user):
    if not user.is_authenticated:
        return {}
    return {
        'first_name': user.first_name or user.username,
        'last_name': user.last_name,
        'email': user.email,
    }


def _create_checkout_session(request, order, line_items):
    success_url = request.build_absolute_uri(reverse('bookings:payment_success'))
    cancel_url = request.build_absolute_uri(reverse('bookings:payment_cancel'))
    return stripe.checkout.Session.create(
        mode='payment',
        line_items=line_items,
        customer_email=order.email,
        client_reference_id=str(order.id),
        billing_address_collection='auto',
        name_collection={'individual': {'enabled': False}},
        phone_number_collection={'enabled': False},
        success_url=f'{success_url}?session_id={{CHECKOUT_SESSION_ID}}&order_id={order.id}',
        cancel_url=f'{cancel_url}?order_id={order.id}',
    )


def order_create(request):
    """Create an order from the cart and redirect to Stripe Checkout.

    Prices are read from the database at checkout time. The order, its items and the
    Stripe session are created in a single transaction, so a Stripe error leaves no
    unpaid orphan order behind.
    """
    cart = Cart(request)
    if not len(cart):
        messages.warning(request, _('Your cart is empty.'))
        return redirect('bookings:cart_detail')

    form = CheckoutForm(request.POST or None, initial=_checkout_initial(request.user))
    if request.method != 'POST' or not form.is_valid():
        return render(request, 'bookings/order_create.html', {'cart': cart, 'form': form})

    items = list(cart)
    unavailable = [item['resource'].name for item in items if not item['resource'].is_active]
    if unavailable:
        messages.error(
            request,
            _('These resources are no longer available: %(names)s') % {'names': ', '.join(unavailable)},
        )
        return redirect('bookings:cart_detail')

    try:
        with transaction.atomic():
            order = Order.objects.create(
                user=request.user if request.user.is_authenticated else None,
                **form.cleaned_data,
            )

            line_items = []
            for item in items:
                resource, quantity = item['resource'], item['quantity']
                OrderItem.objects.create(
                    order=order,
                    resource=resource,
                    price=resource.price_per_hour,
                    quantity=quantity,
                )
                line_items.append({
                    'price_data': {
                        'currency': settings.STRIPE_CURRENCY,
                        'unit_amount': int(resource.price_per_hour * 100),
                        'product_data': {'name': resource.name},
                    },
                    'quantity': quantity,
                })

            session = _create_checkout_session(request, order, line_items)
            order.stripe_id = session.id
            order.save(update_fields=['stripe_id'])
    except stripe.error.StripeError as error:
        logger.error('Stripe error: %s', error)
        messages.error(request, _('Payment error: %(error)s') % {'error': error.user_message or error})
    except Exception:
        logger.exception('Order creation failed')
        messages.error(request, _('Could not create order. Please try again.'))
    else:
        return HttpResponseRedirect(session.url, status=303)

    return render(request, 'bookings/order_create.html', {'cart': cart, 'form': form})


def payment_success(request):
    """Confirm the payment with Stripe and mark the order as paid exactly once.

    The order row is locked with ``select_for_update`` so parallel requests cannot
    confirm it twice, and the email is sent only after the transaction commits.
    """
    order_id = request.GET.get('order_id')
    session_id = request.GET.get('session_id')
    if not (order_id and session_id):
        return redirect('bookings:cart_detail')

    order = get_object_or_404(Order, id=order_id, stripe_id=session_id)
    if order.paid:
        return render(request, 'bookings/success.html', {'order': order})

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as error:
        logger.error('Stripe error: %s', error)
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
    order_id = request.GET.get('order_id', '')
    order = Order.objects.filter(id=order_id, paid=False).first() if order_id.isdigit() else None
    return render(request, 'bookings/cancel.html', {'order': order})


@require_GET
async def resource_availability(request, slug):
    """JSON: is the resource free between ``?start=`` and ``?end=`` (ISO datetimes)?"""
    resource = await Resource.objects.filter(slug=slug, is_active=True).afirst()
    if resource is None:
        return JsonResponse({'error': _('Resource not found.')}, status=404)

    start = parse_datetime(request.GET.get('start', ''))
    end = parse_datetime(request.GET.get('end', ''))
    if not start or not end:
        return JsonResponse({'error': _('Parameters "start" and "end" are required.')}, status=400)

    start = start if timezone.is_aware(start) else timezone.make_aware(start)
    end = end if timezone.is_aware(end) else timezone.make_aware(end)
    if start >= end:
        return JsonResponse({'error': _('End time must be greater than start time.')}, status=400)

    is_booked = await resource.bookings.overlapping(start, end).aexists()
    return JsonResponse({
        'resource': resource.slug,
        'start': start.isoformat(),
        'end': end.isoformat(),
        'available': not is_booked,
    })


@login_required
@require_GET
async def booking_stats(request):
    """JSON: the user's booking counters by status, paid orders and the next 5 bookings."""
    user = await request.auser()
    bookings = Booking.objects.filter(user=user)

    stats = await bookings.aaggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status=Status.PENDING)),
        confirmed=Count('id', filter=Q(status=Status.CONFIRMED)),
        cancelled=Count('id', filter=Q(status=Status.CANCELLED)),
    )
    paid_orders = await Order.objects.filter(user=user, paid=True).acount()

    upcoming_bookings = (
        bookings.active()
        .filter(start_time__gte=timezone.now())
        .select_related('resource')
        .order_by('start_time')[:5]
    )
    upcoming = [
        {
            'id': booking.id,
            'resource': booking.resource.name,
            'start_time': booking.start_time.isoformat(),
            'end_time': booking.end_time.isoformat(),
            'status': booking.status,
        }
        async for booking in upcoming_bookings
    ]

    return JsonResponse({**stats, 'paid_orders': paid_orders, 'upcoming': upcoming})


@login_required
async def order_detail(request, pk):
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
