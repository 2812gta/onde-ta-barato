import io
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from PIL import Image

from apps.audit.models import AuditLog
from apps.contributions.models import (
    DRAFT_TTL,
    ContributionStatus,
    FraudKind,
    FraudSignal,
    UserContribution,
)
from apps.core import clock
from apps.prices.models import PriceConfirmation, PriceEvidence, PriceObservation
from tests.conftest import FORTALEZA, NEAR

URL = "/api/v1/contributions/"


def photo(color=(200, 30, 30), with_gps=True) -> SimpleUploadedFile:
    image = Image.new("RGB", (64, 48), color)
    buffer = io.BytesIO()
    if with_gps:
        exif = Image.Exif()
        exif[0x010F] = "SecretPhoneMaker"
        gps = exif.get_ifd(0x8825)
        gps[1], gps[2], gps[3], gps[4] = "S", (3.0, 52.0, 36.0), "W", (38.0, 32.0, 36.0)
        image.save(buffer, format="JPEG", exif=exif)
    else:
        image.save(buffer, format="JPEG")
    return SimpleUploadedFile("tag.jpg", buffer.getvalue(), content_type="image/jpeg")


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def world(make_user, make_merchant, make_store, make_variant):
    owner = make_user()
    merchant = make_merchant(owner=owner, trade_name="Mercantil")
    store = make_store(merchant=merchant, coords=NEAR, name="Perto")
    return {
        "owner": owner,
        "store": store,
        "variant": make_variant(),  # Arroz Tio João 5 kg, GTIN-less
        "consumer": make_user(),
    }


def create_draft(client, world, text="ARROZ TIO JOAO 5KG\nR$ 24,90", **extra):
    body = {"store_id": str(world["store"].pk), "photo": photo(), "ocr_text": text, **extra}
    return client.post(URL, body, format="multipart")


def confirm_body(world, price="24.90", **extra):
    return {"variant_id": str(world["variant"].pk), "price": price, **extra}


def confirm(client, draft_id, body):
    return client.post(f"{URL}{draft_id}/confirm/", body, format="json")


@pytest.mark.django_db
class TestDraft:
    def test_draft_reads_the_tag_and_suggests_the_product(self, world, login_as):
        client = login_as(world["consumer"])
        response = create_draft(client, world)
        assert response.status_code == 201, response.content
        body = response.json()
        assert body["status"] == "DRAFT"
        assert [p["value"] for p in body["reading"]["prices"]] == ["24.90"]
        assert body["reading"]["prices"][0]["origin"] == "FACT"
        (suggestion,) = body["suggested_variants"]
        assert suggestion["id"] == str(world["variant"].pk)
        assert (suggestion["basis"], suggestion["origin"]) == ("TEXT", "INFERENCE")
        assert body["reading"]["note"]

    def test_gtin_match_is_exact_and_a_fact(self, world, login_as, make_variant):
        with_code = make_variant(
            name="Feijão Carioca", brand="Camil", quantity="1", gtin="07891000100103"
        )
        client = login_as(world["consumer"])
        body = create_draft(client, world, text="qualquer coisa\n7891000100103").json()
        top = body["suggested_variants"][0]
        assert top["id"] == str(with_code.pk)
        assert (top["basis"], top["origin"]) == ("GTIN", "FACT")

    def test_creating_a_draft_records_no_price(self, world, login_as):
        create_draft(login_as(world["consumer"]), world)
        assert PriceObservation.objects.count() == 0

    def test_photo_is_stored_without_gps_or_camera_metadata(self, world, login_as, private_media):
        create_draft(login_as(world["consumer"]), world)
        contribution = UserContribution.objects.get()
        stored = (private_media / contribution.photo.name).read_bytes()
        assert b"SecretPhoneMaker" not in stored
        assert len(Image.open(io.BytesIO(stored)).getexif()) == 0

    def test_not_an_image_is_refused(self, world, login_as):
        client = login_as(world["consumer"])
        fake = SimpleUploadedFile("tag.jpg", b"not an image", content_type="image/jpeg")
        response = client.post(
            URL, {"store_id": str(world["store"].pk), "photo": fake}, format="multipart"
        )
        assert response.status_code == 400

    def test_inactive_store_is_refused(self, world, login_as):
        world["store"].status = "CLOSED"
        world["store"].save()
        assert create_draft(login_as(world["consumer"]), world).status_code == 400

    def test_requires_login(self, world, api):
        assert create_draft(api, world).status_code == 401

    def test_open_drafts_are_limited(self, world, login_as):
        client = login_as(world["consumer"])
        statuses = [create_draft(client, world).status_code for _ in range(6)]
        assert statuses == [201, 201, 201, 201, 201, 400]

    def test_future_capture_time_is_refused(self, world, login_as):
        future = (clock.now() + timedelta(hours=2)).isoformat()
        response = create_draft(login_as(world["consumer"]), world, captured_at=future)
        assert response.status_code == 400

    def test_users_only_see_their_own_contributions(self, world, login_as, make_user):
        draft = create_draft(login_as(world["consumer"]), world).json()
        other = login_as(make_user())
        assert other.get(f"{URL}{draft['id']}/").status_code == 404
        assert other.get(URL).json() == []


@pytest.mark.django_db
class TestConfirm:
    def test_confirming_records_a_user_price_with_photo_evidence(self, world, login_as):
        client = login_as(world["consumer"])
        draft = create_draft(client, world).json()
        response = confirm(client, draft["id"], confirm_body(world))
        assert response.status_code == 201, response.content
        body = response.json()
        assert body["price"]["source"] == "USER"
        assert body["price"]["has_evidence"] is True
        assert body["contribution"]["status"] == "CONFIRMED"
        assert body["contribution"]["corrected"] is False
        observation = PriceObservation.objects.get()
        assert (observation.price, observation.created_by) == (Decimal("24.90"), world["consumer"])
        assert PriceEvidence.objects.get().observation == observation

    def test_changing_the_price_marks_it_as_corrected(self, world, login_as):
        client = login_as(world["consumer"])
        draft = create_draft(client, world).json()
        body = confirm(client, draft["id"], confirm_body(world, price="23.50")).json()
        assert body["contribution"]["corrected"] is True
        assert PriceObservation.objects.get().price == Decimal("23.50")

    def test_choosing_a_product_that_was_not_suggested_is_a_correction(
        self, world, login_as, make_variant
    ):
        other = make_variant(name="Feijão Carioca", brand="Camil", quantity="1")
        client = login_as(world["consumer"])
        draft = create_draft(client, world).json()
        body = confirm(client, draft["id"], {"variant_id": str(other.pk), "price": "24.90"}).json()
        assert body["contribution"]["corrected"] is True

    def test_photo_is_deleted_from_the_draft_after_confirmation(
        self, world, login_as, private_media
    ):
        client = login_as(world["consumer"])
        draft = create_draft(client, world).json()
        draft_file = private_media / UserContribution.objects.get().photo.name
        assert draft_file.exists()
        confirm(client, draft["id"], confirm_body(world))
        contribution = UserContribution.objects.get()
        assert not contribution.photo
        assert not draft_file.exists()
        assert contribution.photo_sha256  # only the hash remains
        assert (private_media / PriceEvidence.objects.get().file.name).exists()

    def test_a_draft_cannot_be_confirmed_twice(self, world, login_as):
        client = login_as(world["consumer"])
        draft = create_draft(client, world).json()
        assert confirm(client, draft["id"], confirm_body(world)).status_code == 201
        assert confirm(client, draft["id"], confirm_body(world)).status_code == 400
        assert PriceObservation.objects.count() == 1

    def test_someone_else_cannot_confirm_my_draft(self, world, login_as, make_user):
        draft = create_draft(login_as(world["consumer"]), world).json()
        response = confirm(login_as(make_user()), draft["id"], confirm_body(world))
        assert response.status_code == 403
        assert PriceObservation.objects.count() == 0

    def test_expired_draft_is_refused(self, world, login_as):
        client = login_as(world["consumer"])
        draft = create_draft(client, world).json()
        UserContribution.objects.update(created_at=clock.now() - DRAFT_TTL - timedelta(minutes=1))
        assert confirm(client, draft["id"], confirm_body(world)).status_code == 400

    def test_store_staff_cannot_pose_as_a_consumer(self, world, login_as):
        client = login_as(world["owner"])
        draft = create_draft(client, world).json()
        assert confirm(client, draft["id"], confirm_body(world)).status_code == 400
        assert PriceObservation.objects.count() == 0

    def test_same_price_from_another_user_becomes_a_confirmation_without_a_photo(
        self, world, login_as, make_user
    ):
        first = login_as(world["consumer"])
        confirm(first, create_draft(first, world).json()["id"], confirm_body(world))
        second_user = make_user()
        second = login_as(second_user)
        draft = create_draft(second, world).json()
        response = confirm(second, draft["id"], confirm_body(world))
        assert response.status_code == 201
        assert PriceObservation.objects.count() == 1
        assert PriceConfirmation.objects.get().user == second_user
        assert PriceEvidence.objects.count() == 1  # only the first photo was kept

    def test_location_is_checked_and_never_stored(self, world, login_as):
        client = login_as(world["consumer"])
        draft = create_draft(client, world).json()
        lat, lon = NEAR
        body = confirm(client, draft["id"], confirm_body(world, lat=lat, lon=lon)).json()
        assert body["price"]["location_verified"] is True
        assert "lat" not in str(body) and "lon" not in str(body)
        assert not FraudSignal.objects.filter(
            kind__in=[FraudKind.LOCATION_FAR, FraudKind.LOCATION_MISSING]
        ).exists()

    def test_half_a_coordinate_is_refused(self, world, login_as):
        client = login_as(world["consumer"])
        draft = create_draft(client, world).json()
        assert confirm(client, draft["id"], confirm_body(world, lat=-3.8)).status_code == 400

    def test_confirmation_is_audited(self, world, login_as):
        client = login_as(world["consumer"])
        confirm(client, create_draft(client, world).json()["id"], confirm_body(world))
        assert AuditLog.objects.filter(action="contribution.confirmed").count() == 1


@pytest.mark.django_db
class TestFraudSignalsAreNotVerdicts:
    def test_far_device_raises_a_signal_but_the_price_is_still_recorded(self, world, login_as):
        client = login_as(world["consumer"])
        draft = create_draft(client, world).json()
        lat, lon = FORTALEZA
        response = confirm(client, draft["id"], confirm_body(world, lat=lat, lon=lon))
        assert response.status_code == 201
        assert PriceObservation.objects.count() == 1
        assert FraudSignal.objects.get().kind == FraudKind.LOCATION_FAR

    def test_missing_location_is_a_low_signal(self, world, login_as):
        client = login_as(world["consumer"])
        confirm(client, create_draft(client, world).json()["id"], confirm_body(world))
        assert FraudSignal.objects.get().kind == FraudKind.LOCATION_MISSING

    def test_the_contributor_is_not_told_which_rules_fired(self, world, login_as):
        client = login_as(world["consumer"])
        body = confirm(client, create_draft(client, world).json()["id"], confirm_body(world)).json()
        assert "signal" not in str(body).lower() and "fraud" not in str(body).lower()

    def test_same_photo_used_by_another_user_is_flagged_high(self, world, login_as, make_user):
        same = photo(color=(1, 2, 3), with_gps=False).read()

        def upload(client, text):
            file = SimpleUploadedFile("tag.jpg", same, content_type="image/jpeg")
            body = {"store_id": str(world["store"].pk), "photo": file, "ocr_text": text}
            return client.post(URL, body, format="multipart").json()

        first = login_as(world["consumer"])
        confirm(first, upload(first, "R$ 24,90")["id"], confirm_body(world, price="24.90"))
        second = login_as(make_user())
        confirm(second, upload(second, "R$ 25,90")["id"], confirm_body(world, price="25.90"))
        signal = FraudSignal.objects.get(kind=FraudKind.DUPLICATE_PHOTO)
        assert signal.severity == "HIGH"

    def test_a_contribution_does_not_flag_itself_as_a_duplicate(self, world, login_as):
        client = login_as(world["consumer"])
        confirm(client, create_draft(client, world).json()["id"], confirm_body(world))
        assert not FraudSignal.objects.filter(kind=FraudKind.DUPLICATE_PHOTO).exists()

    def test_signals_are_append_only(self, world, login_as):
        from apps.core.append_only import ImmutableRecordError

        client = login_as(world["consumer"])
        confirm(client, create_draft(client, world).json()["id"], confirm_body(world))
        with pytest.raises(ImmutableRecordError):
            FraudSignal.objects.all().delete()


@pytest.mark.django_db
class TestCancelAndExpire:
    def test_cancel_deletes_the_photo_and_keeps_no_price(self, world, login_as, private_media):
        client = login_as(world["consumer"])
        draft = create_draft(client, world).json()
        stored = private_media / UserContribution.objects.get().photo.name
        response = client.post(f"{URL}{draft['id']}/cancel/")
        assert response.status_code == 200
        assert response.json()["status"] == "CANCELLED"
        assert not stored.exists()
        assert PriceObservation.objects.count() == 0
        assert confirm(client, draft["id"], confirm_body(world)).status_code == 400

    def test_cancel_frees_a_slot_for_a_new_draft(self, world, login_as):
        client = login_as(world["consumer"])
        ids = [create_draft(client, world).json()["id"] for _ in range(5)]
        assert create_draft(client, world).status_code == 400
        client.post(f"{URL}{ids[0]}/cancel/")
        assert create_draft(client, world).status_code == 201

    def test_someone_else_cannot_cancel_my_draft(self, world, login_as, make_user):
        draft = create_draft(login_as(world["consumer"]), world).json()
        response = login_as(make_user()).post(f"{URL}{draft['id']}/cancel/")
        assert response.status_code == 403

    def test_purge_command_expires_old_drafts_and_deletes_their_photos(
        self, world, login_as, private_media
    ):
        client = login_as(world["consumer"])
        old = create_draft(client, world).json()["id"]
        fresh = create_draft(client, world).json()["id"]
        UserContribution.objects.filter(pk=old).update(
            created_at=clock.now() - DRAFT_TTL - timedelta(minutes=1)
        )
        old_file = private_media / UserContribution.objects.get(pk=old).photo.name
        call_command("purge_stale_drafts")
        assert UserContribution.objects.get(pk=old).status == ContributionStatus.CANCELLED
        assert not old_file.exists()
        assert UserContribution.objects.get(pk=fresh).status == ContributionStatus.DRAFT


@pytest.mark.django_db
class TestAccountDeletion:
    def test_open_draft_photos_are_deleted_with_the_account(self, world, login_as, private_media):
        from tests.conftest import PASSWORD

        client = login_as(world["consumer"])
        create_draft(client, world)
        stored = private_media / UserContribution.objects.get().photo.name
        assert stored.exists()
        response = client.delete("/api/v1/me/", {"password": PASSWORD}, format="json")
        assert response.status_code == 204, response.content
        assert not stored.exists()
        assert UserContribution.objects.get().status == ContributionStatus.CANCELLED

    def test_export_lists_my_contributions(self, world, login_as):
        client = login_as(world["consumer"])
        confirm(client, create_draft(client, world).json()["id"], confirm_body(world))
        data = client.get("/api/v1/me/export/").json()
        assert [(c["store"], c["status"]) for c in data["contributions"]] == [
            ("Perto", "CONFIRMED")
        ]
        assert "photo" not in str(data["contributions"])
