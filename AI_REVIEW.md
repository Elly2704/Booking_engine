# AI Code Review

Code review трьох найскладніших views проєкту **Booking Engine** (`apps/bookings/views.py`),
виконаний за допомогою **Claude (Anthropic, Claude Code CLI)**.

Для кожного view наведено оригінальний код, рекомендації AI з рішенням (✅ застосовано / ❌ відхилено,
з поясненням) і фінальний код. Кожне застосоване виправлення покрите регресійним тестом у
`tests/unit/test_review_fixes.py`. Промпти, які використовувались, наведені в [AI_PROMPTS.md](AI_PROMPTS.md).

| # | View | Знайдено | Застосовано | Відхилено |
|---|------|---------|-------------|-----------|
| 1 | `BookingCancelView` | 4 | 3 | 1 |
| 2 | `order_create` | 6 | 3 | 3 |
| 3 | `payment_success` | 6 | 2 | 4 |

---

## 1. `BookingCancelView`

Скасування бронювання: GET показує сторінку підтвердження, POST змінює статус на `cancelled`.

### Оригінальний код

```python
class BookingCancelView(LoginRequiredMixin, UpdateView):
    model = Booking
    fields = []
    template_name = 'bookings/booking_confirm_cancel.html'
    success_url = reverse_lazy('bookings:booking_list')

    def form_valid(self, form):
        form.instance.status = 'cancelled'
        return super().form_valid(form)
```

### Рекомендації AI

| # | Проблема | Серйозність | Рішення |
|---|----------|-------------|---------|
| 1.1 | **IDOR.** `UpdateView` з `model = Booking` шукає об'єкт серед *усіх* бронювань. Будь-який залогінений користувач може скасувати чуже бронювання, підставивши його `pk` в URL. Перевірено тестом: чужий користувач отримав `302`, бронювання стало `cancelled`. | 🔴 Критична | ✅ Додано `get_queryset()` з фільтром `user=self.request.user`. Чужі бронювання тепер повертають `404`. |
| 1.2 | Можна повторно «скасувати» вже скасоване бронювання, а також бронювання, яке вже почалося або минуло. | 🟡 Середня | ✅ Queryset виключає `cancelled` і бронювання з `start_time <= now`. У модель додано властивість `Booking.is_cancellable`, і шаблон показує кнопку «Скасувати» лише коли вона має сенс. |
| 1.3 | Після скасування користувач не отримує жодного зворотного зв'язку. | 🟢 Низька | ✅ Додано перекладене flash-повідомлення. |
| 1.4 | `UpdateView` з `fields = []` виглядає як хак, краще замінити на окремий `View` з `post()`. | 🟢 Стиль | ❌ Відхилено. `UpdateView` уже дає GET-сторінку підтвердження, CSRF-захищений POST і `get_object()` з 404. Переписування додасть код без зміни поведінки. |

### Фінальний код

```python
class BookingCancelView(LoginRequiredMixin, UpdateView):
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
```

---

## 2. `order_create`

Оформлення замовлення: валідація форми, створення `Order` + `OrderItem` і Stripe Checkout Session в одній транзакції.

### Оригінальний код

```python
def order_create(request):
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

            return HttpResponseRedirect(checkout_session.url, status=303)

        except stripe.error.StripeError as e:
            logger.error("Stripe error: %s", e)
            messages.error(request, _('Payment error: %(error)s') % {'error': e.user_message or e})
        except Exception:
            logger.exception("Order creation failed")
            messages.error(request, _('Could not create order. Please try again.'))

    return render(request, 'bookings/order_create.html', {'cart': cart, 'form': form})
```

### Рекомендації AI

| # | Проблема | Серйозність | Рішення |
|---|----------|-------------|---------|
| 2.1 | **Застаріла ціна.** Ціна береться з сесії (`item['price']`), куди вона записалась у момент додавання в кошик. Якщо адміністратор змінить ціну, клієнт заплатить стару. | 🔴 Висока | ✅ Ціна береться з БД на момент оформлення: `price = resource.price_per_hour`. |
| 2.2 | Деактивований ресурс (`is_active=False`), який уже лежить у кошику, усе одно можна оплатити. | 🟡 Середня | ✅ Перед створенням замовлення перевіряється `is_active`. Якщо є неактивні ресурси, користувача повертає в кошик з повідомленням, Stripe не викликається. |
| 2.3 | Валюта `'usd'` захардкожена. | 🟢 Низька | ✅ Винесено в `settings.STRIPE_CURRENCY` (читається з `.env`, за замовчуванням `usd`). |
| 2.4 | `int(price * 100)` може обрізати копійки через похибку float. | — | ❌ Хибна тривога. `price` має тип `Decimal` з 2 знаками після коми (`DecimalField(decimal_places=2)`), тому `price * 100` завжди точне ціле. Перевірено тестом: `99.90 → 9990`. |
| 2.5 | Мережевий виклик Stripe усередині `transaction.atomic()` тримає транзакцію БД відкритою на час HTTP-запиту. | 🟡 Середня | ❌ Відхилено свідомо. Саме завдяки цьому помилка Stripe відкочує замовлення, і в БД не лишається «сиротами» неоплачених `Order` (покрито тестом `test_stripe_error_rolls_back_order`). При поточному навантаженні короткий запит до Stripe прийнятний. Альтернатива (створити замовлення, потім викликати Stripe і вручну видаляти при помилці) складніша і крихкіша. |
| 2.6 | Широкий `except Exception`. | 🟢 Стиль | ❌ Залишено як останній рубіж: помилка логується з повним traceback (`logger.exception`), а користувач бачить зрозуміле повідомлення замість 500. |

### Фінальний код

```python
def order_create(request):
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
```

---

## 3. `payment_success`

Обробка редиректу Stripe після оплати: перевірка статусу, позначення замовлення оплаченим, лист-підтвердження.

### Оригінальний код

```python
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
            messages.error(request, _('Could not verify payment.'))
            return redirect('bookings:cart_detail')

        if session.payment_status != 'paid':
            messages.warning(request, _('Payment has not been completed yet.'))
            return render(request, 'bookings/cancel.html', {'order': order})

        order.paid = True
        order.save()
        Cart(request).clear()
        send_order_confirmation_email(order)

    return render(request, 'bookings/success.html', {'order': order})
```

### Рекомендації AI

| # | Проблема | Серйозність | Рішення |
|---|----------|-------------|---------|
| 3.1 | **Race condition.** Два одночасні запити (подвійне оновлення сторінки, повтор від браузера) обидва бачать `paid=False`, обидва проходять перевірку і відправляють **два листи**. | 🟡 Середня | ✅ Рядок замовлення блокується через `select_for_update()` у транзакції з повторною перевіркою `paid`. Покрито тестом, який імітує паралельний запит. |
| 3.2 | Лист відправляється до фіксації транзакції. Якщо збереження впаде, клієнт отримає лист про оплату, якої в БД немає. | 🟡 Середня | ✅ Відправка через `transaction.on_commit()`. Також `save(update_fields=[...])`, щоб не перезаписувати інші поля. |
| 3.3 | Не перевіряється, що `session.client_reference_id == order.id`. | — | ❌ Надлишково. Замовлення вже шукається за парою `id` + `stripe_id=session_id`, а сесію ми отримуємо від Stripe за тим самим `session_id` з нашим секретним ключем. Підмінити зв'язок неможливо. |
| 3.4 | Не перевіряється, що `session.amount_total` дорівнює сумі замовлення. | — | ❌ Сума формується на сервері в `order_create` і передається в Stripe напряму, клієнт не може її змінити. |
| 3.5 | Сторінку успіху може відкрити будь-хто, хто знає посилання. | 🟢 Низька | ❌ `session_id` — довгий випадковий ідентифікатор Stripe, тобто посилання працює як секретний токен. Так само гості (без акаунту) бачать своє замовлення. |
| 3.6 | Відправляти лист у фоні (Celery) замість синхронно в запиті. | 🟢 Низька | ❌ Поза межами проєкту: немає брокера повідомлень. Помилки SMTP уже перехоплюються і логуються, тому оплату вони не ламають. |

### Фінальний код

```python
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
```

---

## Перевірка

```bash
.venv/bin/pytest tests/unit/test_review_fixes.py -v
```

10 регресійних тестів на виправлення з цього рев'ю. Усього в проєкті 137 тестів, усі проходять.
Docstrings у фінальному коді вище прибрані для стислості, у репозиторії вони є.
