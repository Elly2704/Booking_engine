from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone, translation

from apps.bookings.forms import BookingForm, CheckoutForm
from apps.resources.forms import ResourceForm
from apps.users.forms import CustomUserChangeForm, CustomUserCreationForm
from tests.factories import TINY_GIF, ResourceFactory

pytestmark = pytest.mark.django_db


def _dt(delta):
    return (timezone.localtime() + delta).strftime('%Y-%m-%dT%H:%M')


class TestBookingForm:
    def test_valid(self):
        form = BookingForm(data={'start_time': _dt(timedelta(days=1)), 'end_time': _dt(timedelta(days=1, hours=2))})
        assert form.is_valid(), form.errors

    def test_end_before_start(self):
        form = BookingForm(data={'start_time': _dt(timedelta(days=1, hours=2)), 'end_time': _dt(timedelta(days=1))})
        assert not form.is_valid()
        assert 'End time must be greater than start time.' in form.non_field_errors()

    def test_past_start(self):
        form = BookingForm(data={'start_time': _dt(-timedelta(days=1)), 'end_time': _dt(timedelta(hours=1))})
        assert not form.is_valid()
        assert 'Cannot book resources in the past.' in form.non_field_errors()

    def test_required_fields(self):
        form = BookingForm(data={})
        assert not form.is_valid()
        assert set(form.errors) == {'start_time', 'end_time'}

    def test_labels_are_translated(self):
        with translation.override('uk'):
            form = BookingForm()
            assert str(form.fields['start_time'].label) == 'Час початку'


class TestResourceForm:
    def _data(self, category, **overrides):
        data = {
            'category': category.pk,
            'name': 'Green Room',
            'slug': 'green-room',
            'description': 'Quiet room',
            'price_per_hour': '30.00',
            'capacity': 6,
            'is_active': True,
        }
        data.update(overrides)
        return data

    def test_valid(self, category):
        form = ResourceForm(data=self._data(category))
        assert form.is_valid(), form.errors

    def test_non_positive_price(self, category):
        form = ResourceForm(data=self._data(category, price_per_hour='0'))
        assert not form.is_valid()
        assert form.errors['price_per_hour'] == ['Price must be greater than zero.']

    def test_duplicate_slug(self, category):
        ResourceFactory(slug='green-room')
        form = ResourceForm(data=self._data(category))
        assert not form.is_valid()
        assert 'slug' in form.errors

    def test_widgets_have_bootstrap_classes(self):
        form = ResourceForm()
        assert form.fields['name'].widget.attrs['class'] == 'form-control'
        assert form.fields['category'].widget.attrs['class'] == 'form-select'


class TestUserForms:
    def _data(self, **overrides):
        data = {
            'username': 'newuser',
            'email': 'new@example.com',
            'phone': '+380501112233',
            'password1': 'VeryStrongPass987',
            'password2': 'VeryStrongPass987',
        }
        data.update(overrides)
        return data

    def test_creation_valid(self):
        form = CustomUserCreationForm(data=self._data())
        assert form.is_valid(), form.errors
        user = form.save()
        assert user.check_password('VeryStrongPass987')
        assert user.phone == '+380501112233'

    def test_creation_password_mismatch(self):
        form = CustomUserCreationForm(data=self._data(password2='Different987xyz'))
        assert not form.is_valid()
        assert 'password2' in form.errors

    def test_creation_fields_have_form_control(self):
        form = CustomUserCreationForm()
        assert all(f.widget.attrs.get('class') == 'form-control' for f in form.fields.values())

    def test_avatar_small_is_accepted(self):
        avatar = SimpleUploadedFile('a.gif', TINY_GIF, content_type='image/gif')
        form = CustomUserCreationForm(data=self._data(), files={'avatar': avatar})
        assert form.is_valid(), form.errors

    def test_avatar_too_large(self):
        avatar = SimpleUploadedFile('a.gif', TINY_GIF + b'\x00' * (3 * 1024 * 1024), content_type='image/gif')
        form = CustomUserCreationForm(data=self._data(), files={'avatar': avatar})
        assert not form.is_valid()
        assert form.errors['avatar'] == ['File size must be less than 2 MB.']

    def test_change_form(self, user):
        form = CustomUserChangeForm(
            data={'username': user.username, 'email': 'changed@example.com', 'phone': '123'},
            instance=user,
        )
        assert form.is_valid(), form.errors
        form.save()
        user.refresh_from_db()
        assert user.email == 'changed@example.com'


class TestCheckoutForm:
    def test_valid_without_last_name(self):
        form = CheckoutForm(data={'first_name': 'Ivan', 'email': 'ivan@example.com'})
        assert form.is_valid()

    def test_invalid_email(self):
        form = CheckoutForm(data={'first_name': 'Ivan', 'email': 'not-an-email'})
        assert not form.is_valid()
        assert 'email' in form.errors

    def test_first_name_required(self):
        form = CheckoutForm(data={'email': 'ivan@example.com'})
        assert not form.is_valid()
        assert 'first_name' in form.errors
