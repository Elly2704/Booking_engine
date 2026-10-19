from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Resource


class ResourceForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = ['category', 'name', 'slug', 'description', 'price_per_hour', 'capacity', 'is_active']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'price_per_hour': forms.NumberInput(attrs={'class': 'form-control'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_price_per_hour(self):
        price = self.cleaned_data.get('price_per_hour')
        if price is not None and price <= 0:
            raise forms.ValidationError(_('Price must be greater than zero.'))
        return price
