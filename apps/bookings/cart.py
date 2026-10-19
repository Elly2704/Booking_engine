from django.conf import settings

from apps.resources.models import Resource


class Cart:
    """Session cart that stores resource ids and hours; prices always come from the database."""

    def __init__(self, request):
        self.session = request.session
        self.cart = self.session.setdefault(settings.CART_SESSION_ID, {})

    def add(self, resource, quantity=1, override_quantity=False):
        key = str(resource.id)
        current = 0 if override_quantity else self.cart.get(key, {}).get('quantity', 0)
        self.cart[key] = {'quantity': current + quantity}
        self.save()

    def remove(self, resource):
        if self.cart.pop(str(resource.id), None) is not None:
            self.save()

    def clear(self):
        self.session.pop(settings.CART_SESSION_ID, None)
        self.cart = {}
        self.save()

    def save(self):
        self.session.modified = True

    def __iter__(self):
        resources = Resource.objects.filter(id__in=self.cart.keys())
        for resource in resources:
            quantity = self.cart[str(resource.id)]['quantity']
            yield {
                'resource': resource,
                'quantity': quantity,
                'price': resource.price_per_hour,
                'total_price': resource.price_per_hour * quantity,
            }

    def __len__(self):
        return sum(item['quantity'] for item in self.cart.values())

    def get_total_price(self):
        return sum(item['total_price'] for item in self)
