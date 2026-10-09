from django.contrib import admin

from .models import FraudSignal, UserContribution


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False


@admin.register(UserContribution)
class UserContributionAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "user", "store", "status", "corrected")
    list_filter = ("status", "corrected")


@admin.register(FraudSignal)
class FraudSignalAdmin(ReadOnlyAdmin):
    """Where moderators review signals: the reason to look, never a verdict."""

    list_display = ("created_at", "kind", "severity", "contribution")
    list_filter = ("kind", "severity")
