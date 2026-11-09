from django.conf import settings
from django.core.mail import send_mail
from django.utils.translation import gettext as _


def send_order_confirmation_email(order):
    subject = _('Order #%(id)s') % {'id': order.id}
    message = _(
        'Hello, %(name)s!\n\nYour payment for order #%(id)s was successful.\n'
        'Thank you for using our booking service!'
    ) % {'name': order.first_name, 'id': order.id}

    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [order.email])
