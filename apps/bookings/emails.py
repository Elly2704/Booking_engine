import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


def send_order_confirmation_email(order):
    """Send a payment confirmation; a mail failure is logged and never breaks checkout."""
    subject = _('Order #%(id)s') % {'id': order.id}
    message = _(
        'Hello, %(name)s!\n\nYour payment for order #%(id)s was successful.\n'
        'Thank you for using our booking service!'
    ) % {'name': order.first_name, 'id': order.id}

    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [order.email])
    except Exception:
        logger.exception('Failed to send confirmation email for order %s', order.id)
