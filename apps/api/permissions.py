from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsOwnerOrReadOnly(BasePermission):
    """Anyone who can see the object may read it, only its owner may change it.

    Staff can see every booking and order, but cannot act on behalf of their owners.
    """

    def has_object_permission(self, request, view, obj):
        return request.method in SAFE_METHODS or obj.user_id == request.user.pk
