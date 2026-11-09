from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import invalidate_catalog
from .models import Resource, ResourceCategory


@receiver([post_save, post_delete], sender=Resource)
@receiver([post_save, post_delete], sender=ResourceCategory)
def invalidate_catalog_cache(**kwargs):
    # After commit, otherwise a concurrent reader could cache the old row under the new version.
    transaction.on_commit(invalidate_catalog, robust=True)
