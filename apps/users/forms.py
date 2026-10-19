from django import forms
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from .models import User

MAX_AVATAR_SIZE = 2 * 1024 * 1024


class UserFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar and avatar.size > MAX_AVATAR_SIZE:
            raise forms.ValidationError(_('File size must be less than 2 MB.'))
        return avatar


class CustomUserCreationForm(UserFormMixin, UserCreationForm):
    avatar = forms.ImageField(label=_('Avatar'), required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'phone', 'avatar')


class CustomUserChangeForm(UserFormMixin, UserChangeForm):
    password = None

    class Meta:
        model = User
        fields = ('username', 'email', 'phone', 'avatar')
