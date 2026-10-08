from rest_framework import generics, serializers

from apps.users import rbac

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor_id",
            "action",
            "entity_type",
            "entity_id",
            "previous_value",
            "new_value",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields


class AuditLogListView(generics.ListAPIView):
    """Read-only, restricted to roles with `audit.view`. IP address is never exposed here."""

    serializer_class = AuditLogSerializer
    permission_classes = [rbac.require(rbac.AUDIT_VIEW)]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        queryset = AuditLog.objects.all()
        params = self.request.query_params
        if entity_type := params.get("entity_type"):
            queryset = queryset.filter(entity_type=entity_type)
        if entity_id := params.get("entity_id"):
            queryset = queryset.filter(entity_id=entity_id)
        if action := params.get("action"):
            queryset = queryset.filter(action=action)
        return queryset
