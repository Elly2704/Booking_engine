from decimal import Decimal
from django.conf import settings
from apps.resources.models import Resource


class Cart:
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(settings.CART_SESSION_ID)
        if not cart:
            cart = self.session[settings.CART_SESSION_ID] = {}
        self.cart = cart

    def add(self, resource, quantity=1, override_quantity=False):
        resource_id = str(resource.id)
        if resource_id not in self.cart:
            self.cart[resource_id] = {
                'quantity': 0,
                'price': str(resource.price_per_hour),
            }

        if override_quantity:
            self.cart[resource_id]['quantity'] = quantity
        else:
            self.cart[resource_id]['quantity'] += quantity
        self.save()

    def save(self):
        self.session.modified = True

    def remove(self, resource):
        resource_id = str(resource.id)
        if resource_id in self.cart:
            del self.cart[resource_id]
            self.save()

    def __iter__(self):
        resource_ids = self.cart.keys()
        resources = Resource.objects.filter(id__in=resource_ids)
        cart = {key: dict(value) for key, value in self.cart.items()}

        for resource in resources:
            cart[str(resource.id)]['resource'] = resource

        for item in cart.values():
            if 'resource' not in item:
                continue
            item['price'] = Decimal(item['price'])
            item['total_price'] = item['price'] * item['quantity']
            yield item

    def __len__(self):
        return sum(item['quantity'] for item in self.cart.values())

    def get_total_price(self):
        return sum(Decimal(item['price']) * item['quantity'] for item in self.cart.values())

    def clear(self):
        self.session.pop(settings.CART_SESSION_ID, None)
        self.save()