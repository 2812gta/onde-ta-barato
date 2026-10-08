from typing import Any

from django.conf import settings
from django.http import HttpRequest

from .models import AuditLog

_SENSITIVE_KEYS = {
    "password",
    "new_password",
    "token",
    "access",
    "refresh",
    "secret",
    "authorization",
}


def scrub(value: Any) -> Any:
    """Drop secrets from values before they reach the audit trail."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if str(k).lower() not in _SENSITIVE_KEYS}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def client_ip(request: HttpRequest | None) -> str | None:
    if request is None or not settings.AUDIT_STORE_IP:
        return None
    return request.META.get("REMOTE_ADDR") or None


def record(
    action: str,
    *,
    actor: Any = None,
    entity_type: str,
    entity_id: Any = "",
    previous_value: Any = None,
    new_value: Any = None,
    request: HttpRequest | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Append an audit entry. Never pass personal data that is not strictly needed."""
    authenticated = actor is not None and getattr(actor, "is_authenticated", False)
    return AuditLog.objects.create(
        actor=actor if authenticated else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        previous_value=scrub(previous_value),
        new_value=scrub(new_value),
        ip_address=client_ip(request),
        metadata=scrub(metadata or {}),
    )
