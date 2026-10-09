from datetime import timedelta

import pytest

from apps.audit.models import AuditLog
from apps.contributions.models import (
    ContributionStatus,
    FraudKind,
    FraudSeverity,
    FraudSignal,
    UserContribution,
)
from apps.core import clock
from apps.moderation import selectors
from apps.moderation.models import PriceModeration
from apps.prices import services as price_services
from apps.prices.models import PriceEvidence, PriceObservation, PriceSource
from apps.prices.selectors import current_prices, price_history
from apps.users.models import Role
from tests.conftest import NEAR

REASON = "Preço incompatível com a foto enviada."


@pytest.fixture
def world(make_user, make_merchant, make_store, make_variant):
    owner = make_user()
    merchant = make_merchant(owner=owner, verified=True, trade_name="Mercantil")
    return {
        "owner": owner,
        "store": make_store(merchant=merchant, coords=NEAR, name="Perto"),
        "variant": make_variant(),
        "consumer": make_user(),
        "moderator": make_user(role=Role.MODERATOR),
    }


def user_price(world, price="24.90", user=None, hours_ago=0):
    result = price_services.report_user_price(
        store=world["store"],
        actor=user or world["consumer"],
        variant=world["variant"],
        price=price,
        collected_at=clock.now() - timedelta(hours=hours_ago),
    )
    return result.observation


def contribution_for(observation, **extra):
    return UserContribution.objects.create(
        user=observation.created_by,
        store=observation.store,
        status=ContributionStatus.CONFIRMED,
        photo_sha256="a" * 64,
        observation=observation,
        **extra,
    )


def signal_for(contribution, kind=FraudKind.PRICE_OUTLIER, severity=FraudSeverity.MEDIUM):
    return FraudSignal.objects.create(contribution=contribution, kind=kind, severity=severity)


def visible_prices(world):
    views = current_prices(variant=world["variant"], store_ids=[world["store"].pk])
    return [v.observation for v in views.get(world["store"].pk, [])]


def hide(client, observation, reason=REASON):
    return client.post(
        f"/api/v1/moderation/prices/{observation.pk}/hide/", {"reason": reason}, format="json"
    )


def decide(client, observation, action, reason=REASON):
    return client.post(
        f"/api/v1/moderation/prices/{observation.pk}/{action}/", {"reason": reason}, format="json"
    )


@pytest.mark.django_db
class TestHidingAPrice:
    def test_hidden_price_leaves_what_consumers_see_but_stays_in_the_records(self, world, login_as):
        observation = user_price(world)
        assert visible_prices(world) == [observation]

        response = hide(login_as(world["moderator"]), observation)

        assert response.status_code == 201, response.content
        assert response.json() == {"moderation": "HIDDEN"}
        assert visible_prices(world) == []
        assert list(price_history(variant=world["variant"], store_id=world["store"].pk)) == []
        # Nothing was edited or deleted.
        assert PriceObservation.objects.filter(pk=observation.pk).exists()
        assert PriceModeration.objects.get().reason == REASON

    def test_evidence_is_kept(self, world, login_as, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        observation = user_price(world)
        from tests.prices.test_price_services import jpeg_with_gps

        price_services.add_evidence(
            observation=observation, actor=world["consumer"], kind="PHOTO", content=jpeg_with_gps()
        )
        hide(login_as(world["moderator"]), observation)
        assert PriceEvidence.objects.filter(observation=observation).count() == 1

    def test_restoring_brings_it_back(self, world, login_as):
        observation = user_price(world)
        client = login_as(world["moderator"])
        hide(client, observation)
        response = decide(client, observation, "restore", "Foto conferida, preço correto.")
        assert response.status_code == 201
        assert response.json() == {"moderation": "VISIBLE"}
        assert visible_prices(world) == [observation]
        assert PriceModeration.objects.count() == 2  # history of decisions is kept

    def test_an_older_price_resurfaces_labelled_by_its_own_age(self, world, login_as):
        older = user_price(world, price="24.00", hours_ago=30)
        newer = user_price(world, price="9.00")
        assert visible_prices(world) == [newer]
        hide(login_as(world["moderator"]), newer)
        assert visible_prices(world) == [older]

    def test_a_reason_is_required(self, world, login_as):
        observation = user_price(world)
        client = login_as(world["moderator"])
        assert hide(client, observation, reason="curto").status_code == 400
        assert hide(client, observation, reason="   ").status_code == 400
        assert (
            client.post(
                f"/api/v1/moderation/prices/{observation.pk}/hide/", {}, format="json"
            ).status_code
            == 400
        )
        assert visible_prices(world) == [observation]

    def test_cannot_hide_twice_or_restore_what_is_visible(self, world, login_as):
        observation = user_price(world)
        client = login_as(world["moderator"])
        assert decide(client, observation, "restore").status_code == 400
        assert hide(client, observation).status_code == 201
        assert hide(client, observation).status_code == 400

    def test_merchant_prices_are_not_moderated_here(self, world, login_as):
        merchant_price = price_services.publish_merchant_price(
            store=world["store"], actor=world["owner"], variant=world["variant"], price="30.00"
        ).observation
        assert merchant_price.source == PriceSource.MERCHANT
        assert hide(login_as(world["moderator"]), merchant_price).status_code == 400
        assert merchant_price in visible_prices(world)

    def test_a_moderator_cannot_moderate_their_own_price(self, world, login_as):
        own = user_price(world, user=world["moderator"])
        assert hide(login_as(world["moderator"]), own).status_code == 403
        assert own in visible_prices(world)

    def test_every_decision_is_audited(self, world, login_as):
        observation = user_price(world)
        client = login_as(world["moderator"])
        hide(client, observation)
        decide(client, observation, "restore")
        actions = set(AuditLog.objects.values_list("action", flat=True))
        assert {"moderation.price_hide", "moderation.price_restore"} <= actions

    def test_unknown_price_is_404(self, world, login_as):
        import uuid

        response = login_as(world["moderator"]).post(
            f"/api/v1/moderation/prices/{uuid.uuid4()}/hide/", {"reason": REASON}, format="json"
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestWhoMayModerate:
    @pytest.mark.parametrize("role", [Role.CUSTOMER, Role.SUPPORT, Role.MERCHANT_OWNER])
    def test_only_moderators_and_above(self, world, login_as, make_user, role):
        observation = user_price(world)
        response = hide(login_as(make_user(role=role)), observation)
        assert response.status_code == 403
        assert visible_prices(world) == [observation]

    @pytest.mark.parametrize("role", [Role.MODERATOR, Role.ADMIN, Role.SUPERADMIN])
    def test_moderation_roles_may(self, world, login_as, make_user, role):
        observation = user_price(world)
        assert hide(login_as(make_user(role=role)), observation).status_code == 201

    def test_a_merchant_cannot_hide_a_price_at_their_own_store(self, world, login_as):
        observation = user_price(world)
        assert hide(login_as(world["owner"]), observation).status_code == 403

    def test_anonymous_is_refused(self, world, api):
        assert hide(api, user_price(world)).status_code == 401


@pytest.mark.django_db
class TestAppeal:
    def hidden(self, world, login_as):
        observation = user_price(world)
        contribution = contribution_for(observation)
        hide(login_as(world["moderator"]), observation)
        return observation, contribution

    def test_contributor_sees_that_it_was_hidden_and_why(self, world, login_as):
        _, contribution = self.hidden(world, login_as)
        rows = login_as(world["consumer"]).get("/api/v1/contributions/").json()
        assert rows[0]["moderation"] == {
            "state": "HIDDEN",
            "reason": REASON,
            "can_appeal": True,
        }

    def test_a_visible_price_reports_no_problem(self, world, login_as):
        observation = user_price(world)
        contribution_for(observation)
        row = login_as(world["consumer"]).get("/api/v1/contributions/").json()[0]
        assert row["moderation"] == {"state": "VISIBLE", "reason": "", "can_appeal": False}

    def test_contributor_can_appeal_once(self, world, login_as):
        _, contribution = self.hidden(world, login_as)
        client = login_as(world["consumer"])
        url = f"/api/v1/contributions/{contribution.pk}/appeal/"
        first = client.post(url, {"message": "Eu estava na loja e a etiqueta mostrava esse valor."})
        assert first.status_code == 201, first.content
        assert first.json()["moderation"]["state"] == "APPEAL_PENDING"
        assert first.json()["moderation"]["can_appeal"] is False
        again = client.post(url, {"message": "Insistindo no mesmo ponto, por favor revejam."})
        assert again.status_code == 400

    def test_appeal_needs_a_real_message(self, world, login_as):
        _, contribution = self.hidden(world, login_as)
        response = login_as(world["consumer"]).post(
            f"/api/v1/contributions/{contribution.pk}/appeal/", {"message": "não"}
        )
        assert response.status_code == 400

    def test_only_the_contributor_can_appeal(self, world, login_as, make_user):
        _, contribution = self.hidden(world, login_as)
        stranger = login_as(make_user())
        response = stranger.post(
            f"/api/v1/contributions/{contribution.pk}/appeal/",
            {"message": "Quero recorrer pelo outro usuário."},
        )
        assert response.status_code == 404  # someone else's contribution is not even revealed

    def test_cannot_appeal_a_price_that_is_not_hidden(self, world, login_as):
        observation = user_price(world)
        contribution = contribution_for(observation)
        response = login_as(world["consumer"]).post(
            f"/api/v1/contributions/{contribution.pk}/appeal/",
            {"message": "Recorrendo sem ter sido ocultado."},
        )
        assert response.status_code == 400

    def test_upholding_is_final_for_the_contributor(self, world, login_as):
        observation, contribution = self.hidden(world, login_as)
        client = login_as(world["consumer"])
        client.post(
            f"/api/v1/contributions/{contribution.pk}/appeal/",
            {"message": "Eu estava na loja e a etiqueta mostrava esse valor."},
        )
        moderator = login_as(world["moderator"])
        upheld = decide(moderator, observation, "uphold", "Foto não mostra o valor informado.")
        assert upheld.status_code == 201
        assert upheld.json() == {"moderation": "UPHELD"}
        assert visible_prices(world) == []
        again = login_as(world["consumer"]).post(
            f"/api/v1/contributions/{contribution.pk}/appeal/",
            {"message": "Quero recorrer novamente da mesma decisão."},
        )
        assert again.status_code == 400
        row = login_as(world["consumer"]).get("/api/v1/contributions/").json()[0]
        assert row["moderation"]["state"] == "UPHELD"
        assert row["moderation"]["reason"] == "Foto não mostra o valor informado."

    def test_uphold_needs_a_pending_appeal(self, world, login_as):
        observation, _ = self.hidden(world, login_as)
        response = decide(login_as(world["moderator"]), observation, "uphold")
        assert response.status_code == 400

    def test_restoring_after_an_appeal_clears_it(self, world, login_as):
        observation, contribution = self.hidden(world, login_as)
        login_as(world["consumer"]).post(
            f"/api/v1/contributions/{contribution.pk}/appeal/",
            {"message": "Eu estava na loja e a etiqueta mostrava esse valor."},
        )
        decide(
            login_as(world["moderator"]), observation, "restore", "Recurso aceito, preço correto."
        )
        assert visible_prices(world) == [observation]
        assert selectors.pending_appeals() == []


@pytest.mark.django_db
class TestQueue:
    def test_signals_come_most_serious_first_and_reviewed_ones_leave(self, world, login_as):
        low = contribution_for(user_price(world, price="24.90"))
        signal_for(low, FraudKind.LOCATION_MISSING, FraudSeverity.LOW)
        high_user = world["consumer"]
        high = contribution_for(user_price(world, price="25.90", user=high_user))
        signal_for(high, FraudKind.DUPLICATE_PHOTO, FraudSeverity.HIGH)
        client = login_as(world["moderator"])

        queue = client.get("/api/v1/moderation/queue/").json()

        assert [s["severity"] for s in queue["signals"]] == ["HIGH", "LOW"]
        top = queue["signals"][0]
        assert top["kind"] == "DUPLICATE_PHOTO"
        assert top["price"]["price"] == "25.90"
        assert top["price"]["moderation"] == "VISIBLE"

        review = client.post(
            f"/api/v1/moderation/signals/{top['id']}/review/",
            {"decision": "DISMISSED", "note": "Foto parecida, mas de outra loja."},
            format="json",
        )
        assert review.status_code == 201
        after = client.get("/api/v1/moderation/queue/").json()
        assert [s["severity"] for s in after["signals"]] == ["LOW"]

    def test_the_queue_never_exposes_who_the_contributor_is(self, world, login_as):
        contribution_for(user_price(world))
        signal_for(UserContribution.objects.get())
        body = login_as(world["moderator"]).get("/api/v1/moderation/queue/").text
        assert world["consumer"].email not in body
        assert "@" not in body

    def test_pending_appeals_are_listed_until_answered(self, world, login_as):
        observation = user_price(world)
        contribution = contribution_for(observation)
        hide(login_as(world["moderator"]), observation)
        login_as(world["consumer"]).post(
            f"/api/v1/contributions/{contribution.pk}/appeal/",
            {"message": "Eu estava na loja e a etiqueta mostrava esse valor."},
        )
        moderator = login_as(world["moderator"])
        appeals = moderator.get("/api/v1/moderation/queue/").json()["appeals"]
        assert len(appeals) == 1
        assert appeals[0]["hidden_because"] == REASON
        decide(moderator, observation, "uphold", "Foto não mostra o valor informado.")
        assert moderator.get("/api/v1/moderation/queue/").json()["appeals"] == []

    def test_customers_cannot_see_the_queue(self, world, login_as):
        assert login_as(world["consumer"]).get("/api/v1/moderation/queue/").status_code == 403


@pytest.mark.django_db
class TestReviewingASignal:
    def setup_signal(self, world):
        return signal_for(contribution_for(user_price(world)))

    def test_reviewing_does_not_hide_anything(self, world, login_as):
        signal = self.setup_signal(world)
        response = login_as(world["moderator"]).post(
            f"/api/v1/moderation/signals/{signal.pk}/review/",
            {"decision": "CONFIRMED", "note": "Parece fraude, acompanhar."},
            format="json",
        )
        assert response.status_code == 201
        assert (
            len(visible_prices(world)) == 1
        )  # a decision about the signal is not a decision on the price

    def test_a_signal_is_reviewed_once(self, world, login_as):
        signal = self.setup_signal(world)
        client = login_as(world["moderator"])
        body = {"decision": "DISMISSED"}
        url = f"/api/v1/moderation/signals/{signal.pk}/review/"
        assert client.post(url, body, format="json").status_code == 201
        assert client.post(url, body, format="json").status_code == 400

    def test_invalid_decision_is_refused(self, world, login_as):
        signal = self.setup_signal(world)
        response = login_as(world["moderator"]).post(
            f"/api/v1/moderation/signals/{signal.pk}/review/", {"decision": "BAN"}, format="json"
        )
        assert response.status_code == 400

    def test_cannot_review_signals_on_ones_own_contribution(self, world, login_as):
        own = contribution_for(user_price(world, user=world["moderator"]))
        signal = signal_for(own)
        response = login_as(world["moderator"]).post(
            f"/api/v1/moderation/signals/{signal.pk}/review/",
            {"decision": "DISMISSED"},
            format="json",
        )
        assert response.status_code == 403

    def test_customers_cannot_review(self, world, login_as):
        signal = self.setup_signal(world)
        response = login_as(world["consumer"]).post(
            f"/api/v1/moderation/signals/{signal.pk}/review/",
            {"decision": "DISMISSED"},
            format="json",
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestHiddenPricesAreNeverUsedForDecisions:
    def test_recommendations_and_cart_read_prices_through_the_same_filter(self, world):
        """Every consumer-facing price read goes through current_prices, which drops hidden."""
        import inspect

        from apps.recommendations import selectors as rec_selectors
        from apps.recommendations import services as rec_services
        from apps.shopping_cart import pricing

        for module in (rec_selectors, rec_services, pricing):
            source = inspect.getsource(module)
            assert "current_prices" in source
            assert "PriceObservation.objects" not in source

    def test_moderation_is_not_reachable_from_money(self):
        """Moderation decisions depend on people and reasons, never on commercial concepts."""
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "apps" / "moderation"
        text = "".join(p.read_text(encoding="utf-8").lower() for p in root.glob("*.py"))
        for word in ("subscription", "sponsor", "advertis", "campaign", "premium", "paid_plan"):
            assert word not in text
