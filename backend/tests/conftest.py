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


# --- M2 domain fixtures ------------------------------------------------------------------

# Maracanaú center and points at known distances (computed with PostGIS geography).
MARACANAU = (-3.8767, -38.6256)  # (lat, lon)
FORTALEZA = (-3.7319, -38.5434)  # ~18.4 km from Maracanaú
NEAR = (-3.8800, -38.6280)  # ~0.4 km from Maracanaú center


@pytest.fixture
def make_merchant(db, make_user):
    from apps.merchants import services as merchant_services
    from apps.merchants.models import VerificationStatus

    def _make(owner=None, verified=False, trade_name="Mercantil Teste", cnpj=""):
        owner = owner or make_user()
        merchant = merchant_services.create_merchant(
            owner=owner, legal_name=f"{trade_name} LTDA", trade_name=trade_name, cnpj=cnpj
        )
        if verified:
            from apps.merchants.models import Merchant

            Merchant.objects.filter(pk=merchant.pk).update(status=VerificationStatus.VERIFIED)
            merchant.refresh_from_db()
        return merchant

    return _make


@pytest.fixture
def make_store(db, make_merchant):
    from apps.stores.models import Store, StoreSource
    from apps.stores.selectors import point_from

    def _make(merchant=None, coords=MARACANAU, name="Loja Teste", **extra):
        if merchant is None:
            merchant = make_merchant()
        return Store.objects.create(
            merchant=merchant,
            name=name,
            location=point_from(*coords),
            source=extra.pop("source", StoreSource.MERCHANT),
            **extra,
        )

    return _make


@pytest.fixture
def category(db):
    from apps.products.models import Category

    return Category.objects.get(slug="mercearia")  # seeded by migration, ttl 240h


@pytest.fixture
def make_variant(db, category):
    from apps.products.services import get_or_create_variant

    def _make(name="Arroz Tio João", brand="Tio João", quantity="5", unit="kg", **extra):
        from decimal import Decimal

        variant, _ = get_or_create_variant(
            name=name,
            brand_name=brand,
            quantity=Decimal(quantity),
            unit=unit,
            category=extra.pop("category", category),
            **extra,
        )
        return variant

    return _make
