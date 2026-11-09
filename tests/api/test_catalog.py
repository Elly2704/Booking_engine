from decimal import Decimal

import pytest
from django.urls import reverse

from apps.resources.models import Resource, ResourceCategory
from tests.factories import ResourceCategoryFactory, ResourceFactory

pytestmark = pytest.mark.django_db

CATEGORIES_URL = reverse('api:category-list')
RESOURCES_URL = reverse('api:resource-list')


def resource_url(resource):
    return reverse('api:resource-detail', args=[resource.pk])


def names(response):
    return [row['name'] for row in response.data['results']]


def test_categories_are_public_and_count_only_active_resources(api_client, category):
    ResourceFactory(category=category)
    ResourceFactory(category=category, is_active=False)

    response = api_client.get(CATEGORIES_URL)

    assert response.status_code == 200
    assert response.data['results'][0]['resources_count'] == 1


@pytest.mark.parametrize(('client_fixture', 'expected'), [
    ('api_client', 401),
    ('user_client', 403),
    ('staff_client', 201),
])
def test_only_staff_can_create_categories(request, client_fixture, expected):
    client = request.getfixturevalue(client_fixture)
    response = client.post(CATEGORIES_URL, {'name': 'Studios', 'slug': 'studios'})
    assert response.status_code == expected


def test_category_slug_must_be_unique(staff_client, category):
    response = staff_client.post(CATEGORIES_URL, {'name': 'Copy', 'slug': category.slug})
    assert response.status_code == 400
    assert 'slug' in response.data


def test_staff_can_delete_category(staff_client, category):
    response = staff_client.delete(reverse('api:category-detail', args=[category.pk]))
    assert response.status_code == 204
    assert not ResourceCategory.objects.filter(pk=category.pk).exists()


def test_resource_list_nests_category(api_client, resource):
    row = api_client.get(RESOURCES_URL).data['results'][0]
    assert row['category']['slug'] == resource.category.slug
    assert 'category_id' not in row


def test_inactive_resources_are_hidden_from_public(api_client):
    hidden = ResourceFactory(is_active=False)
    assert api_client.get(RESOURCES_URL).data['count'] == 0
    assert api_client.get(resource_url(hidden)).status_code == 404


def test_staff_can_see_inactive_resources(staff_client):
    ResourceFactory(is_active=False)
    assert staff_client.get(RESOURCES_URL).data['count'] == 1


def test_staff_can_create_resource(staff_client, category):
    response = staff_client.post(RESOURCES_URL, {
        'category_id': category.pk,
        'name': 'Green Room',
        'slug': 'green-room',
        'price_per_hour': '40.50',
        'capacity': 6,
    })
    assert response.status_code == 201
    assert response.data['category']['id'] == category.pk
    assert Resource.objects.get(slug='green-room').price_per_hour == Decimal('40.50')


def test_create_resource_with_unknown_category_fails(staff_client):
    response = staff_client.post(RESOURCES_URL, {
        'category_id': 999, 'name': 'X', 'slug': 'x', 'price_per_hour': '1.00',
    })
    assert response.status_code == 400
    assert 'category_id' in response.data


def test_regular_user_cannot_change_resource(user_client, resource):
    assert user_client.patch(resource_url(resource), {'name': 'Mine'}).status_code == 403
    assert user_client.delete(resource_url(resource)).status_code == 403


def test_staff_can_update_resource(staff_client, resource):
    response = staff_client.patch(resource_url(resource), {'capacity': 9})
    assert response.status_code == 200
    resource.refresh_from_db()
    assert resource.capacity == 9


def test_filter_resources_by_category_slug(api_client, resource):
    ResourceFactory(category=ResourceCategoryFactory(slug='desks'), name='Desk')
    response = api_client.get(RESOURCES_URL, {'category': 'desks'})
    assert names(response) == ['Desk']


def test_filter_resources_by_price_range(api_client):
    ResourceFactory(name='Cheap', price_per_hour=Decimal('5.00'))
    ResourceFactory(name='Middle', price_per_hour=Decimal('20.00'))
    ResourceFactory(name='Costly', price_per_hour=Decimal('90.00'))
    response = api_client.get(RESOURCES_URL, {'min_price': 10, 'max_price': 50})
    assert names(response) == ['Middle']


def test_invalid_filter_value_is_rejected(api_client):
    assert api_client.get(RESOURCES_URL, {'min_price': 'abc'}).status_code == 400


def test_search_resources_by_name(api_client):
    ResourceFactory(name='Photo Studio', description='')
    ResourceFactory(name='Desk', description='')
    assert names(api_client.get(RESOURCES_URL, {'search': 'photo'})) == ['Photo Studio']


def test_order_resources_by_price(api_client):
    ResourceFactory(name='B', price_per_hour=Decimal('20.00'))
    ResourceFactory(name='A', price_per_hour=Decimal('10.00'))
    assert names(api_client.get(RESOURCES_URL, {'ordering': 'price_per_hour'})) == ['A', 'B']


def test_resources_are_paginated_by_20(api_client):
    ResourceFactory.create_batch(25)

    first = api_client.get(RESOURCES_URL)
    assert first.data['count'] == 25
    assert len(first.data['results']) == 20
    assert first.data['next'] is not None

    second = api_client.get(RESOURCES_URL, {'page': 2})
    assert len(second.data['results']) == 5
    assert second.data['next'] is None
