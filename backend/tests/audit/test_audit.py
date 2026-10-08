import pytest

from apps.audit import services
from apps.audit.models import AuditLog, ImmutableAuditError


@pytest.mark.django_db
class TestAuditLog:
    def test_record_stores_fields(self):
        entry = services.record(
            "price.changed",
            entity_type="price",
            entity_id=42,
            previous_value={"price": "10.00"},
            new_value={"price": "12.00"},
            metadata={"source": "test"},
        )
        entry.refresh_from_db()
        assert entry.entity_id == "42"
        assert entry.previous_value == {"price": "10.00"}
        assert entry.actor is None

    def test_secrets_are_scrubbed_recursively(self):
        entry = services.record(
            "x",
            entity_type="user",
            new_value={
                "password": "p",
                "nested": {"token": "t", "ok": 1},
                "items": [{"refresh": "r"}],
            },
            metadata={"Authorization": "Bearer abc"},
        )
        assert entry.new_value == {"nested": {"ok": 1}, "items": [{}]}
        assert entry.metadata == {}

    def test_entry_cannot_be_modified(self):
        entry = services.record("x", entity_type="user")
        entry.action = "tampered"
        with pytest.raises(ImmutableAuditError):
            entry.save()

    def test_entry_cannot_be_deleted(self):
        entry = services.record("x", entity_type="user")
        with pytest.raises(ImmutableAuditError):
            entry.delete()

    def test_queryset_update_and_delete_are_blocked(self):
        services.record("x", entity_type="user")
        with pytest.raises(ImmutableAuditError):
            AuditLog.objects.all().update(action="y")
        with pytest.raises(ImmutableAuditError):
            AuditLog.objects.all().delete()

    def test_ip_is_not_stored_by_default(self, rf):
        request = rf.get("/", REMOTE_ADDR="203.0.113.9")
        assert services.record("x", entity_type="user", request=request).ip_address is None

    def test_ip_is_stored_only_when_enabled(self, rf, settings):
        settings.AUDIT_STORE_IP = True
        request = rf.get("/", REMOTE_ADDR="203.0.113.9")
        assert services.record("x", entity_type="user", request=request).ip_address == "203.0.113.9"
