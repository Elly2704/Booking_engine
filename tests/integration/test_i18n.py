import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import translation

from apps.bookings.views import send_order_confirmation_email

pytestmark = pytest.mark.django_db


def test_languages_configured():
    assert [code for code, _ in settings.LANGUAGES] == ['uk', 'en']
    assert 'django.middleware.locale.LocaleMiddleware' in settings.MIDDLEWARE


def test_compiled_catalog_is_loaded():
    with translation.override('uk'):
        assert translation.gettext('Your cart is empty.') == 'Ваш кошик порожній.'


def test_accept_language_header_selects_ukrainian(client, resource):
    response = client.get(reverse('resources:resource_list'), HTTP_ACCEPT_LANGUAGE='uk')
    page = response.content.decode()
    assert response.headers['Content-Language'] == 'uk'
    assert 'Система бронювання' in page
    assert '<html lang="uk">' in page
    assert '$25,00/год' in page


def test_accept_language_header_selects_english(client, resource):
    response = client.get(reverse('resources:resource_list'), HTTP_ACCEPT_LANGUAGE='en')
    assert 'Booking Engine' in response.content.decode()
    assert '$25.00/hr' in response.content.decode()


def test_switch_language_via_set_language(client, resource):
    detail_url = reverse('resources:resource_detail', kwargs={'slug': resource.slug})

    response = client.post(reverse('set_language'), {'language': 'uk', 'next': detail_url})
    assert response.status_code == 302
    assert response.url == detail_url

    page = client.get(detail_url).content.decode()
    assert 'Додати до кошика' in page

    client.post(reverse('set_language'), {'language': 'en', 'next': detail_url})
    assert 'Add to Cart' in client.get(detail_url).content.decode()


def test_flash_message_translated(client, resource):
    response = client.post(
        reverse('bookings:cart_add', args=[resource.id]),
        follow=True,
        HTTP_ACCEPT_LANGUAGE='uk',
    )
    assert f'«{resource.name}» додано до кошика.' in response.content.decode()


def test_form_errors_translated(auth_client, resource):
    response = auth_client.post(
        reverse('bookings:booking_create', kwargs={'slug': resource.slug}),
        {'start_time': '2099-01-01T12:00', 'end_time': '2099-01-01T10:00'},
        HTTP_ACCEPT_LANGUAGE='uk',
    )
    assert 'Час завершення має бути пізнішим за час початку.' in response.content.decode()


def test_api_errors_translated(client, resource):
    response = client.get(
        reverse('bookings:resource_availability', kwargs={'slug': resource.slug}),
        HTTP_ACCEPT_LANGUAGE='uk',
    )
    assert response.json()['error'] == "Параметри «start» та «end» обов'язкові."


def test_plural_forms_in_ukrainian(client, category):
    from tests.factories import ResourceFactory
    ResourceFactory.create_batch(5, category=category)
    page = client.get(reverse('resources:category_stats'), HTTP_ACCEPT_LANGUAGE='uk').content.decode()
    assert 'Усього 5 активних ресурсів.' in page


def test_confirmation_email_in_active_language(order, mailoutbox):
    with translation.override('uk'):
        send_order_confirmation_email(order)
    assert mailoutbox[0].subject == f'Замовлення #{order.id}'
    assert 'пройшла успішно' in mailoutbox[0].body
