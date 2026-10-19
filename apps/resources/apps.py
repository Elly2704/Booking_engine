from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ResourcesConfig(AppConfig):
    name = 'apps.resources'
    verbose_name = _('Resources')
