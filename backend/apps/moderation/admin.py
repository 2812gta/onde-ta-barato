from django.contrib import admin

from .models import PriceAppeal, PriceModeration, SignalReview


class ReadOnlyAdmin(admin.ModelAdmin):
    """Decisions are append-only and go through the API (reason, audit): the admin only reads."""

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False


@admin.register(PriceModeration)
class PriceModerationAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "action", "observation", "actor")
    list_filter = ("action",)


@admin.register(PriceAppeal)
class PriceAppealAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "moderation", "user")


@admin.register(SignalReview)
class SignalReviewAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "decision", "signal", "actor")
    list_filter = ("decision",)
