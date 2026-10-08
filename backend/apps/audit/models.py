import uuid

from django.conf import settings
from django.db import models

from apps.core import clock
from apps.core.append_only import AppendOnlyModel, ImmutableRecordError

# Backwards-compatible name used by callers and tests.
ImmutableAuditError = ImmutableRecordError


class AuditLog(AppendOnlyModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=80, db_index=True)
    entity_type = models.CharField(max_length=80, db_index=True)
    entity_id = models.CharField(max_length=64, blank=True, db_index=True)
    previous_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=clock.now, editable=False, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["entity_type", "entity_id", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.action} {self.entity_type}:{self.entity_id}"
