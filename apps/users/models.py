from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    phone = models.CharField(_("Phone"), max_length=20, blank=True, null=True)
    avatar = models.ImageField(_("Avatar"), upload_to='avatars/', blank=True, null=True)

    class Meta:
        db_table = 'users_user'
        verbose_name = _("User")
        verbose_name_plural = _("Users")
