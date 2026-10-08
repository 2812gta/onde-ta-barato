from django.contrib import admin

from .models import PriceConfirmation, PriceEvidence, PriceObservation


class ReadOnlyAdmin(admin.ModelAdmin):
    """History is append-only: staff can inspect, never edit or delete."""

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        return False


@admin.register(PriceObservation)
class PriceObservationAdmin(ReadOnlyAdmin):
    list_display = (
        "product_variant",
        "store",
        "price",
        "source",
        "collected_at",
        "confidence_level",
    )
    list_filter = ("source", "payment_condition", "confidence_level")


@admin.register(PriceEvidence)
class PriceEvidenceAdmin(ReadOnlyAdmin):
    list_display = ("observation", "kind", "sha256", "created_at")


@admin.register(PriceConfirmation)
class PriceConfirmationAdmin(ReadOnlyAdmin):
    list_display = ("observation", "agrees", "created_at")
