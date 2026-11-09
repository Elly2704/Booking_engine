import pytest
from django.urls import reverse
from rest_framework_simplejwt.tokens import AccessToken

from tests.factories import UserFactory

pytestmark = pytest.mark.django_db

TOKEN_URL = reverse('api:token_obtain_pair')
REFRESH_URL = reverse('api:token_refresh')
VERIFY_URL = reverse('api:token_verify')
ME_URL = reverse('api:user-me')


@pytest.fixture
def tokens(api_client, user, password):
    response = api_client.post(TOKEN_URL, {'username': user.username, 'password': password})
    assert response.status_code == 200
    return response.data


def test_token_obtain_returns_access_and_refresh(tokens):
    assert {'access', 'refresh'} <= set(tokens)


def test_token_obtain_with_wrong_password_is_rejected(api_client, user):
    response = api_client.post(TOKEN_URL, {'username': user.username, 'password': 'wrong'})
    assert response.status_code == 401


def test_token_refresh_issues_a_working_access_token(api_client, tokens, user):
    response = api_client.post(REFRESH_URL, {'refresh': tokens['refresh']})
    assert response.status_code == 200
    assert AccessToken(response.data['access'])['user_id'] == str(user.pk)


def test_token_refresh_rejects_an_access_token(api_client, tokens):
    response = api_client.post(REFRESH_URL, {'refresh': tokens['access']})
    assert response.status_code == 401


def test_token_verify_accepts_a_valid_token(api_client, tokens):
    assert api_client.post(VERIFY_URL, {'token': tokens['access']}).status_code == 200


def test_token_verify_rejects_garbage(api_client):
    assert api_client.post(VERIFY_URL, {'token': 'not-a-token'}).status_code == 401


def test_bearer_token_authenticates_requests(api_client, tokens, user):
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')
    response = api_client.get(ME_URL)
    assert response.status_code == 200
    assert response.data['username'] == user.username


def test_invalid_bearer_token_is_rejected(api_client):
    api_client.credentials(HTTP_AUTHORIZATION='Bearer broken')
    assert api_client.get(ME_URL).status_code == 401


def test_me_requires_authentication(api_client):
    assert api_client.get(ME_URL).status_code == 401


def test_me_updates_profile_but_not_username(user_client, user):
    response = user_client.patch(ME_URL, {'phone': '+380000000000', 'username': 'hacked'})
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.phone == '+380000000000'
    assert user.username != 'hacked'


def test_regular_user_sees_only_themselves(user_client, user, other_user):
    response = user_client.get(reverse('api:user-list'))
    assert [row['id'] for row in response.data['results']] == [user.pk]


def test_regular_user_cannot_open_another_profile(user_client, other_user):
    response = user_client.get(reverse('api:user-detail', args=[other_user.pk]))
    assert response.status_code == 404


def test_staff_sees_all_users(staff_client, staff_user):
    UserFactory.create_batch(2)
    assert staff_client.get(reverse('api:user-list')).data['count'] == 3
