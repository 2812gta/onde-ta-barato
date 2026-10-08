"""seed_demo builds a fictional, repeatable data set that the real M3 endpoints can use."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.audit.models import AuditLog
from apps.core import clock
from apps.core.demo_seed import DEMO_EMAIL_DOMAIN, DEMO_PREFIX
from apps.merchants.models import Merchant, VerificationStatus
from apps.prices.models import PriceConfirmation, PriceObservation
from apps.products.models import ProductVariant
from apps.promotions.engine import validate_rule
from apps.promotions.models import Promotion
from apps.stores.models import Store
from apps.users.models import User

PASSWORD = "Demo-Senha-Longa-123!"


def run(*args: str) -> str:
    out = StringIO()
    call_command("seed_demo", *args, stdout=out)
    return out.getvalue()


def counts() -> dict[str, int]:
    return {
        "users": User.objects.count(),
        "merchants": Merchant.objects.count(),
        "stores": Store.objects.count(),
        "variants": ProductVariant.objects.count(),
        "prices": PriceObservation.objects.count(),
        "confirmations": PriceConfirmation.objects.count(),
        "promotions": Promotion.objects.count(),
        "audit": AuditLog.objects.count(),
    }


@pytest.mark.django_db
class TestSeedDemo:
    def test_creates_the_demo_world(self):
        run("--password", PASSWORD)
        c = counts()
        assert c["merchants"] == 3 and c["stores"] == 6
        assert c["variants"] == 16 and c["promotions"] == 5
        assert c["prices"] > 50 and c["confirmations"] == 5

    def test_is_idempotent(self):
        run("--password", PASSWORD)
        before = counts()
        output = run("--password", PASSWORD)
        assert counts() == before
        assert "created" not in output  # nothing new was written the second time

    def test_everything_is_visibly_fictional(self):
        run("--password", PASSWORD)
        assert all(
            s.name.startswith(DEMO_PREFIX) for s in Store.objects.all()
        ), "every demo store is labelled"
        assert all(m.trade_name.startswith(DEMO_PREFIX) for m in Merchant.objects.all())
        assert all(u.email.endswith("@" + DEMO_EMAIL_DOMAIN) for u in User.objects.all())
        assert not Merchant.objects.exclude(cnpj__isnull=True).exists()  # no CNPJ, real or fake

    def test_stores_are_in_fortaleza(self):
        run("--password", PASSWORD)
        for store in Store.objects.all():
            assert -4.0 < store.lat < -3.6 and -38.7 < store.lon < -38.4, store.name

    def test_goes_through_the_real_rules(self):
        run("--password", PASSWORD)
        by_name = {m.trade_name: m for m in Merchant.objects.all()}
        assert by_name[DEMO_PREFIX + "Rede Alfa"].status == VerificationStatus.VERIFIED
        assert by_name[DEMO_PREFIX + "Atacado Beta"].status == VerificationStatus.VERIFIED
        # The third merchant is left unverified on purpose: its data must weigh less.
        assert by_name[DEMO_PREFIX + "Mercadinho Gama"].status == VerificationStatus.PENDING
        for promotion in Promotion.objects.all():
            validate_rule(promotion.rule)
        assert AuditLog.objects.filter(action="price.recorded").exists()
        assert AuditLog.objects.filter(action="merchant.status_changed").count() == 4

    def test_has_the_scenarios_m3_needs_to_show(self):
        run("--password", PASSWORD)
        now = clock.now()
        assert PriceObservation.objects.filter(collected_at__lt=now - timedelta(days=7)).exists()
        assert PriceObservation.objects.filter(is_promotional=True).exists()
        assert PriceObservation.objects.filter(source="USER").exists()
        disputed = PriceConfirmation.objects.filter(agrees=False).count()
        assert disputed == 2
        sizes = ProductVariant.objects.filter(product__name="Café Torrado e Moído")
        assert sizes.count() == 2  # two sizes of one product: unit price has something to compare

    def test_users_get_the_given_password_and_it_is_not_repeated_on_rerun(self):
        output = run("--password", PASSWORD)
        assert PASSWORD in output
        assert User.objects.get(email=f"cliente1@{DEMO_EMAIL_DOMAIN}").check_password(PASSWORD)
        assert PASSWORD not in run("--password", PASSWORD)

    def test_random_password_when_none_is_given(self):
        output = run()
        password = next(
            line.split("Password: ")[1] for line in output.splitlines() if "Password: " in line
        )
        assert len(password) >= 12
        assert User.objects.get(email=f"cliente1@{DEMO_EMAIL_DOMAIN}").check_password(password)

    def test_refuses_to_run_with_production_settings(self, monkeypatch):
        monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.production")
        with pytest.raises(CommandError, match="never runs with production"):
            run()
        assert User.objects.count() == 0

    def test_basket_recommendation_works_on_demo_data(self, login_as, make_user):
        run("--password", PASSWORD)
        arroz = ProductVariant.objects.get(product__name="Arroz Branco", base_quantity=5000)
        feijao = ProductVariant.objects.get(product__name="Feijão Carioca")
        client = login_as(make_user())
        response = client.post(
            "/api/v1/recommendations/basket/",
            {
                "lat": -3.7385,
                "lon": -38.4965,
                "radius_km": 30,
                "items": [
                    {"variant_id": str(arroz.pk), "quantity": "1"},
                    {"variant_id": str(feijao.pk), "quantity": "2"},
                ],
            },
            format="json",
        )
        assert response.status_code == 200, response.content
        data = response.json()
        assert data["verdict"] == "RECOMMENDED" and data["best"]["stores"]
        assert data["searched"]["stores_with_prices"] >= 3
