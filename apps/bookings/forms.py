from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Booking


class DateTimeLocalInput(forms.DateTimeInput):
    input_type = 'datetime-local'

    def __init__(self, attrs=None):
        super().__init__(attrs={'class': 'form-control', **(attrs or {})}, format='%Y-%m-%dT%H:%M')


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['start_time', 'end_time']
        widgets = {
            'start_time': DateTimeLocalInput(),
            'end_time': DateTimeLocalInput(),
        }


class CheckoutForm(forms.Form):
    first_name = forms.CharField(
        label=_('First Name'),
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    last_name = forms.CharField(
        label=_('Last Name'),
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    email = forms.EmailField(
        label=_('Email'),
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
    )
