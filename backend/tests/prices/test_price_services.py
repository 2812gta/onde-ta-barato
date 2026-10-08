import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from PIL import Image

from apps.audit.models import AuditLog
from apps.core.append_only import ImmutableRecordError
from apps.merchants import services as merchant_services
from apps.prices import evidence, services
from apps.prices.models import PriceObservation, PriceSource
from apps.stores.models import StoreStatus
from tests.conftest import FORTALEZA, MARACANAU, NEAR


@pytest.fixture
def setup(make_user, make_merchant, make_store, make_variant):
    owner = make_user()
    merchant = make_merchant(owner=owner)
    return {
        "owner": owner,
        "merchant": merchant,
        "store": make_store(merchant=merchant, coords=MARACANAU),
        "variant": make_variant(),
        "consumer": make_user(),
    }


def publish(s, price="24.90", actor=None, **kw):
    return services.publish_merchant_price(
        store=s["store"],
        actor=actor or s["owner"],
        variant=s["variant"],
        price=Decimal(price),
        **kw,
    )


def report(s, price="23.90", actor=None, **kw):
    return services.report_user_price(
        store=s["store"],
        actor=actor or s["consumer"],
        variant=s["variant"],
        price=Decimal(price),
        **kw,
    )


@pytest.mark.django_db
class TestMerchantPublishing:
    def test_publishes_with_source_author_and_audit(self, setup):
        result = publish(setup)
        obs = result.observation
        assert result.created
        assert (obs.source, obs.created_by, obs.price, obs.currency) == (
            PriceSource.MERCHANT,
            setup["owner"],
            Decimal("24.90"),
            "BRL",
        )
        assert obs.supersedes is None
        entry = AuditLog.objects.get(action="price.recorded")
        assert entry.new_value["price"] == "24.90"

    def test_operator_may_publish_but_stranger_may_not(self, setup, make_user):
        operator = make_user()
        merchant_services.add_member(
            merchant=setup["merchant"],
            actor=setup["owner"],
            email=operator.email,
            role="MERCHANT_OPERATOR",
        )
        assert publish(setup, actor=operator).created
        with pytest.raises(PermissionDenied):
            publish(setup, actor=setup["consumer"])

    def test_store_without_merchant_cannot_receive_merchant_prices(self, setup):
        setup["store"].merchant = None
        with pytest.raises(PermissionDenied):
            publish(setup)

    def test_another_merchants_staff_cannot_publish_here(self, setup, make_merchant):
        rival = make_merchant(trade_name="Concorrente").memberships.get().user
        with pytest.raises(PermissionDenied):
            publish(setup, actor=rival)

    def test_verified_merchant_gets_higher_confidence_snapshot(
        self, setup, make_merchant, make_store
    ):
        verified = make_merchant(verified=True, trade_name="Verificado")
        other_store = make_store(merchant=verified, name="Outra")
        owner = verified.memberships.get().user
        a = publish(setup).observation
        b = services.publish_merchant_price(
            store=other_store, actor=owner, variant=setup["variant"], price=Decimal("24.90")
        ).observation
        assert b.confidence_score > a.confidence_score


@pytest.mark.django_db
class TestHistory:
    def test_correction_creates_a_new_row_that_points_to_the_old_one(self, setup):
        first = publish(setup, "25.90").observation
        second = publish(setup, "27.90").observation
        assert second.supersedes_id == first.pk
        first.refresh_from_db()
        assert first.price == Decimal("25.90")  # untouched
        assert PriceObservation.objects.count() == 2
        entry = AuditLog.objects.filter(action="price.recorded").first()
        assert entry.previous_value == {"price": "25.90"}

    def test_spec_example_keeps_every_step(self, setup):
        now = timezone.now()
        for days_ago, price in [(35 - 30, "25.90"), (4, "27.90"), (3, "24.90"), (2, "23.90")]:
            publish(setup, price, collected_at=now - timedelta(days=days_ago, hours=7))
        history = list(
            PriceObservation.objects.order_by("collected_at").values_list("price", flat=True)
        )
        assert history == [Decimal(p) for p in ["25.90", "27.90", "24.90", "23.90"]]

    def test_chains_are_separate_per_payment_condition_and_source(self, setup):
        publish(setup, "25.00")
        pix = publish(setup, "23.00", payment_condition="PIX").observation
        user = report(setup, "24.00").observation
        assert pix.supersedes is None
        assert user.supersedes is None

    def test_same_price_inside_window_is_deduplicated(self, setup):
        first = publish(setup, "25.00")
        again = publish(setup, "25.00")
        assert (first.created, again.created) == (True, False)
        assert again.observation.pk == first.observation.pk
        assert PriceObservation.objects.count() == 1

    def test_same_price_after_window_is_a_new_observation(self, setup, settings):
        settings.PRICE_DEDUP_HOURS = 6
        publish(setup, "25.00", collected_at=timezone.now() - timedelta(hours=10))
        again = publish(setup, "25.00")
        assert again.created  # re-confirms the price is still valid today

    def test_changing_validity_or_promo_flag_is_not_a_duplicate(self, setup):
        publish(setup, "25.00")
        promo = publish(setup, "25.00", is_promotional=True)
        assert promo.created

    def test_observations_are_immutable(self, setup):
        obs = publish(setup).observation
        obs.price = Decimal("1.00")
        with pytest.raises(ImmutableRecordError):
            obs.save()
        with pytest.raises(ImmutableRecordError):
            obs.delete()
        with pytest.raises(ImmutableRecordError):
            PriceObservation.objects.all().update(price=Decimal("1.00"))
        with pytest.raises(ImmutableRecordError):
            PriceObservation.objects.all().delete()


@pytest.mark.django_db
class TestValidation:
    @pytest.mark.parametrize("price", ["0", "0.00", "-1", "100000"])
    def test_out_of_range_prices(self, setup, price):
        with pytest.raises(ValidationError):
            publish(setup, price)

    def test_float_prices_are_rejected(self, setup):
        with pytest.raises(TypeError):
            services.publish_merchant_price(
                store=setup["store"], actor=setup["owner"], variant=setup["variant"], price=24.9
            )

    def test_price_is_rounded_half_up_to_cents(self, setup):
        assert publish(setup, "24.905").observation.price == Decimal("24.91")

    def test_future_and_ancient_collection_dates(self, setup):
        with pytest.raises(ValidationError):
            publish(setup, collected_at=timezone.now() + timedelta(hours=1))
        with pytest.raises(ValidationError):
            publish(setup, collected_at=timezone.now() - timedelta(days=31))

    def test_validity_must_follow_collection(self, setup):
        now = timezone.now()
        with pytest.raises(ValidationError):
            publish(setup, collected_at=now, valid_until=now - timedelta(days=1))

    def test_inactive_store_is_refused(self, setup):
        setup["store"].status = StoreStatus.INACTIVE
        with pytest.raises(ValidationError):
            publish(setup)

    def test_database_rejects_invalid_rows_even_when_bypassing_services(self, setup):
        from django.db import IntegrityError, transaction

        with pytest.raises(IntegrityError), transaction.atomic():
            PriceObservation.objects.create(
                product_variant=setup["variant"],
                store=setup["store"],
                price=Decimal("0"),
                source="USER",
                confidence_score=Decimal("0.5"),
                confidence_level="MEDIUM",
            )


@pytest.mark.django_db
class TestUserReports:
    def test_consumer_report_is_user_sourced(self, setup):
        obs = report(setup).observation
        assert obs.source == PriceSource.USER
        assert obs.created_by == setup["consumer"]

    def test_store_staff_cannot_pose_as_customers(self, setup):
        with pytest.raises(ValidationError):
            report(setup, actor=setup["owner"])

    def test_nearby_report_is_location_verified_and_coordinates_are_not_stored(self, setup):
        obs = report(setup, user_lat=NEAR[0], user_lon=NEAR[1]).observation
        assert obs.location_verified is True
        names = {f.name for f in PriceObservation._meta.get_fields()}
        assert not names & {"user_lat", "user_lon", "latitude", "longitude", "user_location"}

    def test_far_report_is_not_location_verified(self, setup):
        obs = report(setup, user_lat=FORTALEZA[0], user_lon=FORTALEZA[1]).observation
        assert obs.location_verified is False

    def test_report_without_location_is_accepted_but_unverified(self, setup):
        assert report(setup).observation.location_verified is False

    def test_location_verification_raises_confidence(self, setup, make_user):
        a = report(setup, actor=make_user()).observation
        b = report(
            setup, price="24.00", actor=make_user(), user_lat=NEAR[0], user_lon=NEAR[1]
        ).observation
        assert b.confidence_score > a.confidence_score

    def test_lat_without_lon_is_refused(self, setup):
        with pytest.raises(ValidationError):
            report(setup, user_lat=1.0)


@pytest.mark.django_db
class TestConfirmations:
    def test_independent_user_can_confirm_once(self, setup, make_user):
        obs = report(setup).observation
        other = make_user()
        services.confirm_price(observation=obs, actor=other, agrees=True)
        with pytest.raises(ValidationError):
            services.confirm_price(observation=obs, actor=other, agrees=False)

    def test_author_cannot_confirm_own_price(self, setup):
        obs = report(setup).observation
        with pytest.raises(ValidationError):
            services.confirm_price(observation=obs, actor=setup["consumer"], agrees=True)

    def test_store_staff_cannot_vote_on_their_own_store(self, setup):
        obs = report(setup).observation
        with pytest.raises(ValidationError):
            services.confirm_price(observation=obs, actor=setup["owner"], agrees=False)

    def test_expired_prices_cannot_be_confirmed(self, setup, make_user):
        obs = PriceObservation.objects.create(
            product_variant=setup["variant"],
            store=setup["store"],
            price=Decimal("20.00"),
            source="USER",
            collected_at=timezone.now() - timedelta(days=60),
            confidence_score=Decimal("0.4"),
            confidence_level="MEDIUM",
        )
        with pytest.raises(ValidationError):
            services.confirm_price(observation=obs, actor=make_user(), agrees=True)


def jpeg_with_gps() -> bytes:
    image = Image.new("RGB", (64, 48), (200, 30, 30))
    exif = Image.Exif()
    exif[0x010F] = "SecretPhoneMaker"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "S", (3.0, 52.0, 36.0), "W", (38.0, 32.0, 36.0)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


@pytest.mark.django_db
class TestEvidence:
    def test_gps_and_camera_metadata_are_stripped(self):
        original = jpeg_with_gps()
        assert b"SecretPhoneMaker" in original  # the fixture really carries metadata
        assert len(Image.open(io.BytesIO(original)).getexif()) > 0
        clean, digest = evidence.sanitize_image(original)
        reopened = Image.open(io.BytesIO(clean))
        assert len(reopened.getexif()) == 0
        assert b"SecretPhoneMaker" not in clean
        assert len(digest) == 64
        assert reopened.size == (64, 48)

    def test_trailing_garbage_is_dropped(self):
        clean, _ = evidence.sanitize_image(jpeg_with_gps() + b"<?php evil ?>")
        assert b"<?php" not in clean

    @pytest.mark.parametrize(
        "payload", [b"", b"not an image", b"%PDF-1.4 fake", b"GIF89a" + b"\0" * 20]
    )
    def test_non_images_are_refused(self, payload):
        with pytest.raises(ValidationError):
            evidence.sanitize_image(payload)

    def test_oversized_file_is_refused(self, monkeypatch):
        monkeypatch.setattr(evidence, "MAX_BYTES", 100)
        with pytest.raises(ValidationError):
            evidence.sanitize_image(jpeg_with_gps())

    def test_pixel_bomb_is_refused(self, monkeypatch):
        monkeypatch.setattr(evidence, "MAX_PIXELS", 100)
        with pytest.raises(ValidationError):
            evidence.sanitize_image(jpeg_with_gps())

    def test_author_attaches_photo_stored_privately(self, setup, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        obs = report(setup).observation
        stored = services.add_evidence(
            observation=obs, actor=setup["consumer"], kind="PHOTO", content=jpeg_with_gps()
        )
        assert stored.file.name.endswith(f"{stored.sha256}.jpg")
        assert (tmp_path / stored.file.name).exists()
        assert b"SecretPhoneMaker" not in (tmp_path / stored.file.name).read_bytes()
        assert AuditLog.objects.filter(action="price.evidence_added").exists()

    def test_only_the_author_can_attach(self, setup, make_user):
        obs = report(setup).observation
        with pytest.raises(PermissionDenied):
            services.add_evidence(
                observation=obs, actor=make_user(), kind="PHOTO", content=jpeg_with_gps()
            )

    def test_url_evidence_accepts_only_http_links(self, setup):
        obs = report(setup).observation
        ok = services.add_evidence(
            observation=obs,
            actor=setup["consumer"],
            kind="URL",
            source_url="https://exemplo.com/encarte",
        )
        assert ok.source_url.startswith("https://")
        for bad in ["javascript:alert(1)", "file:///etc/passwd", "ftp://x"]:
            with pytest.raises(ValidationError):
                services.add_evidence(
                    observation=obs, actor=setup["consumer"], kind="URL", source_url=bad
                )

    def test_evidence_is_append_only(self, setup):
        obs = report(setup).observation
        ev = services.add_evidence(
            observation=obs, actor=setup["consumer"], kind="URL", source_url="https://exemplo.com/x"
        )
        ev.source_url = "https://outro.com"
        with pytest.raises(ImmutableRecordError):
            ev.save()
