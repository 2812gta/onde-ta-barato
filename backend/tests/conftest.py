import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.users.models import Role, User

PASSWORD = "S3nha-Forte-Longa!"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def _make(role: str = Role.CUSTOMER, email: str | None = None, **extra) -> User:
        counter["n"] += 1
        return User.objects.create_user(
            email=email or f"user{counter['n']}@example.com",
            password=PASSWORD,
            role=role,
            **extra,
        )

    return _make


@pytest.fixture
def login_as(api):
    def _login(user: User) -> APIClient:
        response = api.post("/api/v1/auth/login/", {"email": user.email, "password": PASSWORD})
        assert response.status_code == 200, response.content
        api.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return api

    return _login
